"""Global round, admission boundary, payouts, replay and price-source regressions."""
import hashlib
import hmac
import json
import math
from pathlib import Path
import secrets
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from main import Game, GameError


class SharedCrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1800000000.0
        self.game = Game(Path(self.tmp.name) / 'game.db', demo=True, clock=lambda: self.now)
        with self.game.db(True) as db:
            for uid in range(1, 13):
                self.game.upsert_user(db, {'id': uid, 'first_name': 'Player ' + str(uid)}, True)
                db.execute('UPDATE users SET stars=150000,grams=2500000 WHERE id=?',(uid,))
                for gift_id in ('rose','toybear','scaredcat'):
                    self.game.add_gift(db,uid,gift_id)
        self.state()

    def tearDown(self):
        self.tmp.cleanup()

    def state(self, uid=1):
        return self.game.read(uid, '/api/crash/room')['state']

    def act(self, path, body, uid=1, key=None):
        return self.game.mutate(uid, path, body, key or secrets.token_hex(12))

    def room(self, point=300):
        with self.game.db(True) as db:
            r = self.game.advance_crash(db)
            if point is not None:
                db.execute('UPDATE crash_rooms SET crash=? WHERE id=?', (point, r['id']))
            else:
                while True:
                    seed = secrets.token_hex(32)
                    value = self.game.crash_point(seed, r['message'])
                    if 300 <= value <= 500:
                        break
                db.execute('UPDATE crash_rooms SET seed=?,crash=? WHERE id=?', (seed, value, r['id']))
            return dict(db.execute('SELECT * FROM crash_rooms WHERE id=?', (r['id'],)).fetchone())

    def bet(self, room, uid=1, auto=0, stake=25, currency='stars', key=None):
        return self.act('/api/crash/bet', {'round_id': room['id'], 'stake': stake, 'currency': currency, 'auto': auto}, uid, key)

    def test_every_player_sees_the_same_round_and_actual_bets(self):
        r = self.room()
        self.bet(r, 1, stake=25)
        self.bet(r, 2, stake=.2, currency='grams')
        one, two = self.state(1), self.state(2)
        self.assertEqual(one['crash']['id'], two['crash']['id'])
        self.assertEqual(one['crash']['bets'], two['crash']['bets'])
        self.assertEqual([(b['user']['first_name'], b['stake'], b['currency']) for b in one['crash']['bets']],
                         [('Player 1', 25, 'stars'), ('Player 2', .2, 'grams')])
        self.assertEqual(one['crash']['mine']['user']['id'], 1)
        self.assertEqual(two['crash']['mine']['user']['id'], 2)
        self.assertNotIn('balance', one['crash']['bets'][0]['user'])
        self.assertNotIn(r['seed'], json.dumps(one))

    def test_concurrent_players_join_one_room(self):
        r = self.room()
        with ThreadPoolExecutor(max_workers=12) as pool:
            replies = list(pool.map(lambda uid: self.bet(r, uid), range(1, 13)))
        self.assertEqual({x['bet']['round_id'] for x in replies}, {r['id']})
        self.assertEqual(self.state()['crash']['players_count'], 12)
        with self.game.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM crash_rooms WHERE status!='crashed'").fetchone()[0], 1)

    def test_concurrent_bet_replay_debits_once(self):
        r, key = self.room(), secrets.token_hex(12)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.bet(r, key=key), range(8)))
        self.assertTrue(all(x == results[0] for x in results))
        self.assertEqual(self.state()['balance']['stars'], 1475)
        self.assertEqual(self.state()['crash']['players_count'], 1)

    def test_different_keys_cannot_create_second_bet(self):
        r = self.room()
        def wager(_):
            try:
                self.bet(r)
                return True
            except GameError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(wager, range(8))), 1)
        self.assertEqual(self.state()['balance']['stars'], 1475)

    def test_stale_round_insufficient_funds_and_invalid_amount_do_not_charge(self):
        r = self.room()
        with self.assertRaises(GameError):
            self.bet({'id': 'stale'})
        for amount in [9, -1, 'nan', 'Infinity', 10.001]:
            with self.assertRaises(GameError):
                self.bet(r, stake=amount)
        self.assertEqual(self.state()['balance']['stars'], 1500)
        with self.game.db(True) as db:
            db.execute('UPDATE users SET stars=0 WHERE id=1')
        with self.assertRaisesRegex(GameError, 'Недостаточно'):
            self.bet(r)
        self.assertEqual(self.state()['crash']['players_count'], 0)

    def test_bets_are_closed_at_launch_and_during_flight(self):
        r = self.room()
        self.now = r['starts_at']
        with self.assertRaisesRegex(GameError, 'завершён'):
            self.bet(r)
        self.assertEqual(self.state()['balance']['stars'], 1500)

    def test_cashout_before_launch_or_for_another_players_bet_is_rejected(self):
        r = self.room()
        bet = self.bet(r)['bet']
        with self.assertRaisesRegex(GameError, 'ещё не начался'):
            self.act('/api/crash/collect', {'bet_id': bet['id']})
        self.now = r['starts_at'] + 1
        with self.assertRaises(GameError):
            self.act('/api/crash/collect', {'bet_id': bet['id']}, uid=2)
        self.assertEqual(self.state()['balance']['stars'], 1475)

    def test_cashout_is_exact_and_does_not_reveal_shared_seed(self):
        r = self.room(None)
        commitment = self.state()['crash']['commitment']
        bet = self.bet(r)['bet']
        self.now = r['starts_at'] + 8 * math.log(1.25)
        reply = self.act('/api/crash/collect', {'bet_id': bet['id']})
        self.assertEqual(reply['bet']['cashout'], 1.25)
        self.assertEqual(reply['bet']['payout'], 31.25)
        self.assertEqual(reply['state']['balance']['stars'], 1506.25)
        self.assertNotIn(r['seed'], json.dumps(reply))
        self.assertEqual(reply['state']['crash']['commitment'], commitment)
        self.assertNotIn('proof', reply['state']['crash'])
        self.assertNotIn('proof', next(e for e in reply['state']['history'] if e['kind'] == 'crash')['details'])
        self.now = r['starts_at'] + 8 * math.log(r['crash'] / 100) + .2
        proof = self.state()['crash']['proof']
        digest = hmac.new(proof['server_seed'].encode(), proof['message'].encode(), hashlib.sha256).hexdigest()
        self.assertEqual(digest, proof['digest'])
        self.assertEqual(hashlib.sha256(proof['server_seed'].encode()).hexdigest(), commitment)
        self.assertEqual(self.game.crash_point(proof['server_seed'], proof['message']) / 100, proof['crash'])

    def test_simultaneous_cashouts_credit_only_once_even_with_different_keys(self):
        r = self.room()
        bet = self.bet(r)['bet']
        self.now = r['starts_at'] + 8 * math.log(1.5)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.act('/api/crash/collect', {'bet_id': bet['id']}), range(8)))
        self.assertTrue(all(x['bet']['payout'] == 37.5 for x in results))
        self.assertEqual(self.state()['balance']['stars'], 1512.5)
        self.assertEqual(sum(e['kind'] == 'crash' for e in self.state()['history']), 1)

    def collectible(self, uid=1):
        source = next(i for i in self.state(uid)['inventory'] if i['gift_id'] == 'scaredcat')
        return self.act('/api/inventory/upgrade', {'item_id': source['id']}, uid)['gift']

    def test_nft_wager_escrows_instance_and_awards_one_ordinary_gift(self):
        item = self.collectible()
        start = self.state()['balance']['stars']
        room = self.room(300)
        body = {'round_id': room['id'], 'currency': 'nft', 'item_id': item['id'], 'auto': 0}
        reply = self.act('/api/crash/bet', body, key='nft-bet-once')
        bet = reply['bet']
        self.assertEqual(reply, self.act('/api/crash/bet', body, key='nft-bet-once'))
        self.assertEqual(reply['state']['balance']['stars'], start)
        self.assertEqual(bet['stake'], item['value_stars'])
        self.assertEqual(bet['stake_item']['number'], item['number'])
        self.assertEqual(bet['stake_item']['collection_id'], item['collection_id'])
        self.assertTrue(bet['stake_item']['virtual'])
        self.assertNotIn(item['id'], [i['id'] for i in reply['state']['inventory']])
        self.assertEqual(self.state(2)['crash']['bets'][0]['stake_item']['attributes'], item['attributes'])
        with self.game.db() as db:
            self.assertEqual(db.execute('SELECT status FROM inventory WHERE id=?', (item['id'],)).fetchone()[0], 'in_crash')
        with self.assertRaises(GameError):
            self.act('/api/inventory/sell', {'item_ids': [item['id']]})
        with self.assertRaises(GameError):
            self.act('/api/crash/bet', body, uid=2)
        self.now = room['starts_at'] + 8 * math.log(1.25)
        with ThreadPoolExecutor(max_workers=6) as pool:
            cashouts = list(pool.map(lambda _: self.act('/api/crash/collect', {'bet_id': bet['id']}), range(6)))
        self.assertEqual(len({x['bet']['reward_item']['id'] for x in cashouts}),1)
        reward=cashouts[0]['bet']['reward_item']
        self.assertFalse(self.game.gifts[reward['gift_id']].get('collectible'))
        self.assertLessEqual(reward['value'],bet['stake']*1.25)
        self.assertEqual(self.state()['balance']['stars'], start)
        self.assertIn(reward['id'],[i['id'] for i in self.state()['inventory']])
        self.assertEqual(sum(e['kind'] == 'crash' for e in self.state()['history']), 1)
        with self.game.db() as db:
            self.assertEqual(db.execute('SELECT status FROM inventory WHERE id=?', (item['id'],)).fetchone()[0], 'used')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM crash_bets WHERE stake_item_id=?', (item['id'],)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM inventory WHERE id=?',(reward['id'],)).fetchone()[0],1)

    def test_ordinary_gift_wager_loses_without_balance_debit(self):
        room = self.room(150)
        ordinary = next(i for i in self.state()['inventory'] if i['gift_id'] == 'rose')
        balance = self.state()['balance']['stars']
        bet = self.act('/api/crash/bet', {'round_id': room['id'], 'currency': 'nft', 'item_id': ordinary['id']})['bet']
        self.assertIsNone(bet['stake_item']['number'])
        self.assertEqual(bet['stake'], self.game.gifts['rose']['price'])
        self.now = room['starts_at'] + 8 * math.log(1.5)
        state = self.state()
        self.assertEqual(state['balance']['stars'], balance)
        self.assertEqual(state['crash']['mine']['status'], 'lost')
        self.assertNotIn(ordinary['id'], [i['id'] for i in state['inventory']])
        self.assertEqual(self.act('/api/crash/collect', {'bet_id': bet['id']})['bet']['payout'], 0)

    def test_gram_gift_wager_awards_ordinary_gram_gift(self):
        with self.game.db(True) as db:
            item=self.game.add_gift(db,1,'heart','grams')
        room=self.room(300)
        bet=self.act('/api/crash/bet',{'round_id':room['id'],'currency':'nft','item_id':item['id']})['bet']
        self.assertEqual(bet['currency'],'grams')
        self.assertEqual(bet['stake'],item['value'])
        start=self.state()['balance']['grams']
        self.now=room['starts_at']+8*math.log(2)
        result=self.act('/api/crash/collect',{'bet_id':bet['id']})
        reward=result['bet']['reward_item']
        self.assertFalse(self.game.gifts[reward['gift_id']].get('collectible'))
        self.assertEqual(result['state']['balance']['grams'],start)
        received=next(i for i in result['state']['inventory'] if i['id']==reward['id'])
        self.assertEqual(received['acquisition_currency'],'grams')

    def test_two_players_can_stake_distinct_collection_numbers_concurrently(self):
        items = {uid: self.collectible(uid) for uid in (1, 2)}
        room = self.room(300)
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda uid: self.act('/api/crash/bet',
                {'round_id': room['id'], 'currency': 'nft', 'item_id': items[uid]['id']}, uid), (1, 2)))
        self.assertEqual(len(replies), 2)
        self.assertEqual(len({(r['bet']['stake_item']['collection_id'], r['bet']['stake_item']['number']) for r in replies}), 2)
        self.assertEqual(self.state()['crash']['players_count'], 2)

    def test_existing_crash_database_gets_nft_wager_migration(self):
        path = Path(self.tmp.name) / 'legacy.db'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE crash_bets(id TEXT PRIMARY KEY, round_id TEXT, user_id INTEGER, stake INTEGER, currency TEXT, auto INTEGER, status TEXT, cashout INTEGER, payout INTEGER, created REAL, settled REAL, UNIQUE(round_id,user_id))')
        migrated = Game(path, demo=True, clock=lambda: self.now)
        with migrated.db() as db:
            self.assertIn('stake_item_id', {x[1] for x in db.execute('PRAGMA table_info(crash_bets)')})
            self.assertTrue(any(x[1] == 'idx_crash_stake_item' for x in db.execute('PRAGMA index_list(crash_bets)')))

    def test_late_cashout_at_crash_boundary_loses(self):
        r = self.room(150)
        bet = self.bet(r)['bet']
        self.now = r['starts_at'] + 8 * math.log(1.5)
        reply = self.act('/api/crash/collect', {'bet_id': bet['id']})
        self.assertEqual(reply['bet']['status'], 'lost')
        self.assertEqual(reply['bet']['payout'], 0)
        self.assertEqual(reply['state']['balance']['stars'], 1475)
        self.assertEqual(reply['state']['crash']['phase'], 'crashed')

    def test_offline_autocashout_runs_before_loss_and_old_results_survive_rollover(self):
        r = self.room(150)
        self.bet(r, 1, auto=1.2)
        self.bet(r, 2, auto=1.5)
        self.now = r['starts_at'] + 40
        state = self.state(1)
        self.assertNotEqual(state['crash']['id'], r['id'])
        previous = state['crash']['last_round']
        self.assertEqual(previous['id'], r['id'])
        won = next(b for b in previous['bets'] if b['user']['id'] == 1)
        lost = next(b for b in previous['bets'] if b['user']['id'] == 2)
        self.assertEqual((won['cashout'], won['payout']), (1.2, 30))
        self.assertEqual(lost['status'], 'lost')
        self.assertEqual(state['balance']['stars'], 1505)
        self.assertEqual(self.state(2)['balance']['stars'], 1475)
        self.assertIn('proof', next(e for e in state['history'] if e['kind'] == 'crash')['details'])

    def test_gram_auto_payout_and_restart_keep_exact_balance(self):
        r = self.room()
        self.bet(r, auto=1.25, stake=.2, currency='grams')
        self.now = r['starts_at'] + 3
        self.game = Game(self.game.database, demo=True, clock=lambda: self.now)
        state = self.state()
        self.assertEqual(state['balance']['grams'], 2.55)
        self.assertEqual(state['crash']['mine']['payout'], .25)
        self.assertEqual(self.state()['balance']['grams'], 2.55)

    def test_empty_instant_crash_has_no_invented_players(self):
        r = self.room(100)
        self.now = r['starts_at']
        state = self.state()['crash']
        self.assertEqual(state['phase'], 'crashed')
        self.assertEqual(state['bets'], [])
        self.assertEqual(state['players_count'], 0)
        self.assertEqual(state['multiplier'], 1)

    def test_case_weight_boundaries_only_award_ordinary_gifts(self):
        with self.game.db(True) as db:
            db.execute('UPDATE users SET stars=1000000000000 WHERE id=1')
        for case in self.game.cases.values():
            cursor = 0
            for entry in case['loot']:
                cursor += entry['weight']
                with patch.object(self.game, 'fair_roll', return_value=(cursor - 1, {})):
                    result = self.act('/api/cases/open', {'case_id': case['id']})
                if entry.get('type')=='currency':
                    self.assertIsNone(result['gift'])
                    self.assertEqual(result['reward']['currency'],'stars')
                    self.assertEqual(result['reward']['amount'],entry['amount_stars'])
                else:
                    gift=result['gift'];self.assertEqual(gift['gift_id'],entry['gift_id'])
                    self.assertFalse(self.game.gifts[gift['gift_id']]['collectible'])
                    self.assertIsNone(gift['number'])

    def test_collectible_case_and_direct_shop_buy_are_rejected_without_debit(self):
        self.game.cases['love']['loot'] = [{'gift_id': 'scaredcat-nft', 'weight': 10000}]
        with self.assertRaises(GameError):
            self.act('/api/cases/open', {'case_id': 'love'})
        with self.assertRaisesRegex(GameError, 'через улучшение'):
            self.act('/api/shop/buy', {'gift_id': 'scaredcat-nft'})
        self.assertEqual(self.state()['balance']['stars'], 1500)

    def test_probability_upgrade_rejects_collectible_target_without_consuming_source(self):
        source = next(i for i in self.state()['inventory'] if i['gift_id'] == 'rose')
        with self.assertRaisesRegex(GameError,'только обычный'):
            self.act('/api/upgrades/play', {'item_id': source['id'], 'target_id': 'scaredcat-nft'})
        self.assertIn(source['id'],[i['id'] for i in self.state()['inventory']])

    def test_collectible_can_upgrade_only_to_a_more_expensive_ordinary_gift(self):
        source = self.collectible()
        with self.assertRaisesRegex(GameError, 'только обычный'):
            self.act('/api/upgrades/play', {'item_id':source['id'],'target_id':'scaredcat-nft'})
        self.assertIn(source['id'],[i['id'] for i in self.state()['inventory']])
        result = self.act('/api/upgrades/play', {'item_id':source['id'],'target_id':'preciouspeach'})
        self.assertNotIn(source['id'],[i['id'] for i in result['state']['inventory']])
        if result['win']:
            self.assertFalse(self.game.gifts[result['gift']['gift_id']]['collectible'])

    def test_prices_use_confirmed_telegram_fields_and_fallback_is_labelled(self):
        raw = json.loads((Path(__file__).resolve().parents[1] / 'tools/data/gifts_api_response.json').read_text())
        records = {str(r['id']): r for r in raw['star_gifts_full']['gifts']}
        for g in self.game.gifts.values():
            if not g['collectible']:
                self.assertEqual(g['telegram_stars'], records[g['telegram_gift_id']]['stars'])
                self.assertIn(g['price_kind'],('verified_ordinary_bid','game_estimate_from_collectible_floor','game_estimate_from_collectible_estimate','game_estimate_without_bid','user_set_game_price'))
                if g['price_kind'] in ('game_estimate_from_collectible_floor','game_estimate_from_collectible_estimate'):
                    upgraded=self.game.gifts[g['upgrade_to']]
                    self.assertEqual(g['price']+self.game.catalog['upgrade_cost'], upgraded['price'])
            elif g['price_kind'] == 'telegram_resale_floor':
                base = next(x for x in self.game.gifts.values() if x.get('upgrade_to') == g['id'])
                self.assertEqual(g['price'], records[base['telegram_gift_id']]['resell_min_stars'])
            else:
                self.assertIn(g['price_kind'], ('virtual_estimate','user_set_game_price'))
                if g['price_kind'] == 'user_set_game_price':
                    base = next(x for x in self.game.gifts.values() if x.get('upgrade_to') == g['id'])
                    self.assertEqual(g['price'], base['price'] + self.game.catalog['upgrade_cost'])
        self.assertEqual(self.game.gifts['scaredcat']['price'],20000)
        self.assertEqual(self.game.gifts['scaredcat-nft']['price'],20025)
        self.assertGreater(self.game.gifts['toybear']['price'],500)
        self.assertEqual(self.game.gifts['rocket']['name'], 'Birthday Cake')
        self.assertEqual(self.game.gifts['cake']['name'], 'Rocket')


if __name__ == '__main__':
    unittest.main()

import hashlib
import hmac
import json
import math
import secrets
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Game, GameError, handler_for, validate_init_data


class GameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1_800_000_000.0
        self.game = Game(Path(self.tmp.name) / 'game.sqlite3', demo=True, admin_ids={1}, clock=lambda: self.now)
        with self.game.db(write=True) as db:
            self.game.upsert_user(db, {'id': 1, 'first_name': 'Admin'}, seed_inventory=True)
            self.game.upsert_user(db, {'id': 2, 'first_name': 'Player'}, seed_inventory=True)
            for uid in (1,2):
                db.execute('UPDATE users SET stars=150000,grams=2500000 WHERE id=?',(uid,))
                for gift_id in ('rose','toybear','scaredcat'):
                    self.game.add_gift(db,uid,gift_id)

    def tearDown(self):
        self.tmp.cleanup()

    def act(self, path, body, uid=2, key=None):
        return self.game.mutate(uid, path, body, key or secrets.token_hex(12))

    def state(self, uid=2):
        return self.game.read(uid, '/api/me')['state']

    def test_new_account_starts_empty(self):
        with self.game.db(write=True) as db:
            self.game.upsert_user(db, {'id': 99, 'first_name': 'New'}, seed_inventory=True)
        new = self.state(99)
        self.assertEqual(new['balance']['stars'], 0)
        self.assertEqual(new['balance']['grams'], 0)
        self.assertEqual(new['inventory'], [])

    def test_live_case_feed_contains_only_real_openings_and_player_avatar(self):
        self.assertEqual(self.game.read(2,'/api/cases/live')['items'],[])
        with self.game.db(write=True) as db:
            self.game.upsert_user(db,{'id':2,'first_name':'Игрок <2>','photo_url':'https://example.com/avatar.jpg'})
            self.game.log(db,2,'buy','Покупка подарка',-1)
        case=self.game.cases['love'];original=case['loot']
        try:
            case['loot']=[{'gift_id':'heart','weight':10000}]
            self.act('/api/cases/open',{'case_id':'love'},uid=2)
            case['loot']=[{'type':'currency','amount_stars':20,'weight':10000}]
            self.act('/api/cases/open',{'case_id':'love'},uid=1)
        finally:
            case['loot']=original
        items=self.game.read(2,'/api/cases/live')['items']
        self.assertEqual(len(items),2)
        self.assertEqual(items[0]['user']['first_name'],'Admin')
        self.assertEqual(items[0]['prize'],{'type':'currency','currency':'stars','amount':20})
        self.assertEqual(items[1]['user'],{'first_name':'Игрок <2>','photo_url':'https://example.com/avatar.jpg'})
        self.assertEqual(items[1]['prize'],{'type':'gift','gift_id':'heart'})
        self.assertEqual(items[1]['case_name'],case['name'])
        self.assertNotIn('proof',str(items))

    def test_gram_case_gift_keeps_currency_and_black_backdrop_raises_value(self):
        case=self.game.cases['love']
        original=case['loot']
        case['loot']=[{'gift_id':'heart','weight':10000}]
        try:
            result=self.act('/api/cases/open',{'case_id':'love','currency':'grams'})
        finally:
            case['loot']=original
        item=result['gift']
        self.assertEqual(item['acquisition_currency'],'grams')
        self.assertEqual(item['value'],self.game.price_units(self.game.gifts['heart']['price'],'grams')/1000000)
        with self.game.db(True) as db:
            db.execute('UPDATE inventory SET gift_id=?,collection_id=?,number=?,attributes=? WHERE id=?',
                       ('scaredcat-nft','scared_cat',999999,json.dumps({'backdrop':'49'}),item['id']))
        premium=next(i for i in self.state()['inventory'] if i['id']==item['id'])
        self.assertEqual(premium['value_stars'],(self.game.gifts['scaredcat-nft']['price']*125+99)//100)
        self.assertEqual(premium['acquisition_currency'],'grams')
        self.assertEqual(premium['value'],self.game.price_units(premium['value_stars'],'grams')/1000000)

    def test_gram_shop_purchase_keeps_gram_price(self):
        start=self.state()['balance']['grams']
        bought=self.act('/api/shop/buy',{'gift_id':'heart','currency':'grams'})
        self.assertEqual(bought['gift']['acquisition_currency'],'grams')
        self.assertEqual(bought['state']['balance']['grams'],start-bought['gift']['value'])

    def test_cheap_case_cannot_award_expensive_gift(self):
        for c in self.game.cases.values():
            for l in c['loot']:
                price=l['amount_stars'] if l.get('type')=='currency' else self.game.gifts[l['gift_id']]['price']
                self.assertLessEqual(price,c['price']*8)
                if c['price']<=35:self.assertLessEqual(price,100)

    def test_case_debits_once_with_idempotency(self):
        start = self.state()['balance']['stars']
        key = secrets.token_hex(16)
        a = self.act('/api/cases/open', {'case_id': 'love'}, key=key)
        b = self.act('/api/cases/open', {'case_id': 'love'}, key=key)
        self.assertEqual(a, b)
        self.assertEqual(self.state()['balance']['stars'], start - self.game.cases['love']['price'] + (a['reward']['amount'] if a['reward'] else 0))
        self.assertEqual(self.state()['stats']['cases'], 1)

    def test_idempotency_key_cannot_change_action(self):
        key = secrets.token_hex(16)
        self.act('/api/cases/open', {'case_id': 'love'}, key=key)
        with self.assertRaises(GameError):
            self.act('/api/cases/open', {'case_id': 'sweet'}, key=key)

    def test_currency_case_reward_uses_purchase_currency_and_replays_once(self):
        case=self.game.cases['love'];original=case['loot']
        case['loot']=[{'type':'currency','amount_stars':15,'weight':10000}]
        try:
            before=self.state()['balance']
            a=self.act('/api/cases/open',{'case_id':'love','currency':'grams'},key='currency-case-123')
            b=self.act('/api/cases/open',{'case_id':'love','currency':'grams'},key='currency-case-123')
            self.assertEqual(a,b)
            self.assertIsNone(a['gift'])
            self.assertEqual(a['reward']['currency'],'grams')
            expected=self.game.price_units(15,'grams')/1_000_000
            self.assertEqual(a['reward']['amount'],expected)
            self.assertAlmostEqual(a['state']['balance']['grams'],before['grams']-self.game.price_units(case['price'],'grams')/1_000_000+expected)
            self.assertEqual(a['state']['stats']['cases'],1)
        finally:case['loot']=original

    def test_fair_roll_matches_published_commitment_and_distribution(self):
        commitment = self.state()['fairness']['commitment']
        r = self.act('/api/cases/open', {'case_id': 'love'})
        p = r['proof']
        self.assertEqual(p['commitment'], commitment)
        digest = hmac.new(p['server_seed'].encode(), p['message'].encode(), hashlib.sha256).hexdigest()
        self.assertEqual(digest, p['digest'])
        self.assertEqual(int(digest, 16) % 10000, p['roll'])

    def test_cosmetic_upgrade_exact_cost_and_same_inventory_id(self):
        source = next(i for i in self.state()['inventory'] if i['gift_id'] == 'scaredcat')
        r = self.act('/api/inventory/upgrade', {'item_id': source['id']})
        self.assertEqual(r['state']['balance']['stars'], 1475)
        self.assertEqual(r['gift']['id'], source['id'])
        self.assertEqual(r['gift']['gift_id'], 'scaredcat-nft')
        self.assertTrue(r['gift']['virtual'])
        with self.assertRaises(GameError):
            self.act('/api/inventory/upgrade', {'item_id': source['id']})

    def test_cannot_sell_someone_elses_inventory(self):
        source = self.state(1)['inventory'][0]
        with self.assertRaises(GameError):
            self.act('/api/inventory/sell', {'item_ids': [source['id']]})

    def test_concurrent_sell_credits_only_once(self):
        source = self.state()['inventory'][0]
        price = self.game.gifts[source['gift_id']]['price']
        def run(_):
            try:
                self.act('/api/inventory/sell', {'item_ids': [source['id']]})
                return True
            except GameError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(run, range(2))), 1)
        self.assertEqual(self.state()['balance']['stars'], 1500 + price)

    def test_risky_upgrade_consumes_source_and_uses_server_price(self):
        source = next(i for i in self.state()['inventory'] if i['gift_id'] == 'rose')
        r = self.act('/api/upgrades/play', {'item_id': source['id'], 'target_id': 'toybear', 'chance': 100})
        self.assertAlmostEqual(r['chance'],min(95,math.floor(self.game.gifts['rose']['price']*9000/self.game.gifts['toybear']['price'])/100))
        self.assertNotIn(source['id'], [i['id'] for i in r['state']['inventory']])
        self.assertEqual(r['state']['stats']['upgrades'], 1)

    def test_unconfigured_admin_command_is_not_a_password(self):
        with self.assertRaises(GameError) as e:
            self.act('/api/promo/redeem', {'code': '/ClezzyKryt'})
        self.assertEqual(e.exception.status, 403)
        self.assertTrue(self.act('/api/promo/redeem', {'code': '/ClezzyKryt'}, uid=1)['open_admin'])
        with self.assertRaises(GameError):
            self.act('/api/admin/grant', {'user_id': 2, 'kind': 'stars', 'amount': 1000, 'reason': 'test'})

    def test_admin_code_grants_persistent_server_side_access_without_id_list(self):
        self.assertFalse(self.state(2)['admin'])
        self.game.admin_access_code = 'CLEZZYKRYT'
        with self.assertRaises(GameError):
            self.act('/api/promo/redeem', {'code': '/incorrect'}, uid=2)
        result = self.act('/api/promo/redeem', {'code': '/ClezzyKryt'}, uid=2)
        self.assertTrue(result['open_admin'])
        self.assertTrue(result['state']['admin'])
        restarted = Game(self.game.database, demo=True, admin_ids=set(), clock=lambda: self.now)
        restarted.admin_access_code = 'CLEZZYKRYT'
        with restarted.db() as db:
            self.assertTrue(restarted.is_admin(db, 2))
        self.assertEqual(restarted.read(2, '/api/admin/users')['audit'][0]['action'], 'access')
        restarted.admin_access_code = 'NEWLONGPRIVATECODE'
        with restarted.db() as db:
            self.assertFalse(restarted.is_admin(db, 2))

    def test_admin_grant_is_audited(self):
        self.act('/api/admin/grant', {'user_id': 2, 'kind': 'gift', 'gift_id': 'plushpepe-nft', 'quantity': 2, 'reason': 'Testing'}, uid=1)
        self.assertEqual(sum(i['gift_id'] == 'plushpepe-nft' for i in self.state()['inventory']), 2)
        audit = self.game.read(1, '/api/admin/users')['audit']
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]['admin_id'], 1)

    def test_promo_can_only_be_redeemed_once(self):
        self.act('/api/promo/redeem', {'code': 'CLEZZY50'})
        with self.assertRaises(GameError):
            self.act('/api/promo/redeem', {'code': 'CLEZZY50'})
        self.assertEqual(self.state()['balance']['stars'], 1550)

    def test_referral_margin_is_credited(self):
        self.act('/api/referrals/create', {'code': 'MYCODE'}, uid=1)
        self.act('/api/promo/redeem', {'code': 'MYCODE'})
        self.act('/api/cases/open', {'case_id': 'love'})
        s = self.state(1)
        self.assertEqual(s['referral']['invited'], 1)
        self.assertGreater(s['referral']['earned'], 0)

    def safe_crash_seed(self):
        while True:
            seed = secrets.token_hex(32)
            message = '2:0:crash:clezzy'
            digest = hmac.new(seed.encode(), message.encode(), hashlib.sha256).hexdigest()
            u = int(digest[:13], 16) / 2**52
            crash = min(10000, max(100, math.floor(97 / max(u, 1 / 2**52))))
            if 300 < crash < 1000:
                with self.game.db(write=True) as db:
                    db.execute('UPDATE users SET server_seed=?,nonce=0 WHERE id=2', (seed,))
                return crash

    def test_crash_hides_seed_until_round_finishes(self):
        self.safe_crash_seed()
        commitment = self.state()['fairness']['commitment']
        r = self.act('/api/crash/start', {'stake': 25, 'auto': 0})
        self.assertNotIn('proof', r['round'])
        self.assertEqual(r['round']['commitment'], commitment)
        self.now += 1
        c = self.act('/api/crash/cashout', {'round_id': r['round']['id']})
        self.assertEqual(c['round']['status'], 'cashed_out')
        self.assertIn('proof', c['round'])

    def test_auto_cashout_survives_absent_browser(self):
        self.safe_crash_seed()
        self.act('/api/crash/start', {'stake': 25, 'auto': 2})
        self.now += 120  # user returns after crash; eligible auto must still win
        s = self.state()
        self.assertEqual(s['round']['status'], 'cashed_out')
        self.assertEqual(s['round']['payout'], 50)
        self.assertEqual(s['balance']['stars'], 1525)

    def test_late_cashout_cannot_win(self):
        self.safe_crash_seed()
        r = self.act('/api/crash/start', {'stake': 25, 'auto': 0})
        self.now += 120
        c = self.act('/api/crash/cashout', {'round_id': r['round']['id']})
        self.assertEqual(c['round']['status'], 'crashed')
        self.assertEqual(c['round']['payout'], 0)

    def test_no_negative_balance_on_failure(self):
        with self.assertRaises(GameError):
            self.act('/api/cases/open', {'case_id': 'pepe'})
        self.assertEqual(self.state()['balance']['stars'], 1500)

    def test_http_auth_and_assets(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.game))
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with urlopen(base + '/api/health') as r:
                self.assertTrue(json.load(r)['ok'])
            with urlopen(Request(base + '/api/auth', data=b'{}', headers={'Content-Type': 'application/json'})) as r:
                token = json.load(r)['token']
            with urlopen(Request(base + '/api/me', headers={'Authorization': 'Bearer ' + token})) as r:
                self.assertEqual(json.load(r)['state']['balance']['stars'], 0)
            with urlopen(base + '/assets/gifts/scaredcat-nft.json') as r:
                self.assertIn('layers', json.load(r))
            model = self.game.catalog['collections'][0]['models'][0]
            with urlopen(base + '/' + model['image'].removeprefix('./')) as r:
                self.assertEqual(r.headers.get_content_type(), 'image/webp')
                self.assertEqual(r.read(4), b'RIFF')
            with urlopen(base + '/' + model['animation'].removeprefix('./').replace('.tgs', '.asset.js')) as r:
                self.assertEqual(r.status, 200)
                self.assertTrue(r.read())
            with self.assertRaises(HTTPError) as e:
                urlopen(base + '/asset-packs/pack-000.zip')
            self.assertEqual(e.exception.code, 404)
            with self.assertRaises(HTTPError) as e:
                urlopen(base + '/%2e%2e/main.py')
            self.assertEqual(e.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()


class TelegramAuthTests(unittest.TestCase):
    def sign(self, data):
        check = '\n'.join(f'{k}={data[k]}' for k in sorted(data))
        key = hmac.new(b'WebAppData', b'123:TEST', hashlib.sha256).digest()
        return urlencode({**data, 'hash': hmac.new(key, check.encode(), hashlib.sha256).hexdigest()})

    def test_valid_and_forged_signed_identity(self):
        data = {'user': json.dumps({'id': 123, 'first_name': 'Test'}), 'auth_date': '1800000000', 'signature': 'signed_field'}
        raw = self.sign(data)
        self.assertEqual(validate_init_data(raw, '123:TEST', now=1800000001)['id'], 123)
        with self.assertRaises(GameError):
            validate_init_data(raw.replace('Test', 'Fake'), '123:TEST', now=1800000001)

    def test_stale_or_duplicate_identity_rejected(self):
        data = {'user': json.dumps({'id': 123}), 'auth_date': '1800000000'}
        raw = self.sign(data)
        with self.assertRaises(GameError):
            validate_init_data(raw, '123:TEST', now=1800004000)
        with self.assertRaises(GameError):
            validate_init_data(raw + '&auth_date=1800000000', '123:TEST', now=1800000001)


if __name__ == '__main__':
    unittest.main()

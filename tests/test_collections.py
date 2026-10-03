"""Ownership, edition allocation and atomic retry regression tests."""
import json,secrets,sqlite3,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from main import Game,GameError
class CollectionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.game=Game(Path(self.tmp.name)/'test.db',demo=True)
  with self.game.db(write=True) as db:
   for uid in range(1,25):
    self.game.upsert_user(db,{'id':uid,'first_name':'Player'},seed_inventory=True)
    db.execute('UPDATE users SET stars=150000,grams=2500000 WHERE id=?',(uid,))
    for gift_id in ('rose','toybear','scaredcat'):self.game.add_gift(db,uid,gift_id)
 def tearDown(self):self.tmp.cleanup()
 def state(self,uid=1):return self.game.read(uid,'/api/me')['state']
 def cat(self,uid=1):return next(i for i in self.state(uid)['inventory'] if i['gift_id']=='scaredcat')
 def upgrade(self,uid=1,key=None):return self.game.mutate(uid,'/api/inventory/upgrade',{'item_id':self.cat(uid)['id']},key or secrets.token_hex(12))
 def test_concurrent_players_get_unique_editions_and_valid_attributes(self):
  with ThreadPoolExecutor(max_workers=12) as pool:items=[r['gift'] for r in pool.map(self.upgrade,range(1,25))]
  self.assertEqual(len({(i['collection_id'],i['number']) for i in items}),24)
  c=self.game.collections[items[0]['collection_id']]
  for item in items:
   self.assertLessEqual(item['number'],c['number_max']);self.assertGreaterEqual(item['number'],1)
   for k,group in [('model','models'),('backdrop','backdrops'),('symbol','symbols')]:self.assertIn(item['attributes'][k],{x['id'] for x in c[group] if x['weight']>0})
  self.assertGreater(len({i['attributes']['model'] for i in items}),1)
 def test_concurrent_replay_debits_and_allocates_once(self):
  source=self.cat();key=secrets.token_hex(12)
  def run(_):return self.game.mutate(1,'/api/inventory/upgrade',{'item_id':source['id']},key)
  with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(run,range(8)))
  self.assertTrue(all(r==results[0] for r in results));self.assertEqual(self.state()['balance']['stars'],1475);self.assertEqual(self.state()['stats']['upgrades'],1)
  with self.game.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM inventory WHERE collection_id IS NOT NULL').fetchone()[0],1)
 def test_exhaustion_rolls_back_cost_and_source(self):
  self.game.collections['scared_cat']['number_max']=2
  self.upgrade(1);self.upgrade(2);source=self.cat(3);before=self.state(3)
  with self.assertRaisesRegex(GameError,'закончились'):self.upgrade(3)
  self.assertEqual(self.state(3)['balance'],before['balance']);self.assertEqual(self.cat(3),source)
 def test_insufficient_balance_does_not_reserve_edition(self):
  with self.game.db(write=True) as db:db.execute('UPDATE users SET stars=0 WHERE id=1')
  with self.assertRaisesRegex(GameError,'Недостаточно'):self.upgrade()
  self.assertEqual(self.cat()['gift_id'],'scaredcat')
  with self.game.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM inventory WHERE collection_id IS NOT NULL').fetchone()[0],0)
 def test_database_blocks_duplicate_and_sold_editions_stay_reserved(self):
  gift=self.upgrade()['gift'];cid=gift['collection_id']
  with self.assertRaises(sqlite3.IntegrityError):
   with self.game.db(write=True) as db:db.execute('INSERT INTO inventory(user_id,gift_id,number,acquired,collection_id) VALUES(?,?,?,?,?)',(2,gift['gift_id'],gift['number'],0,cid))
  self.game.mutate(1,'/api/inventory/sell',{'item_ids':[gift['id']]},secrets.token_hex(12))
  self.game.collections[cid]['number_max']=1
  with self.game.db(write=True) as db:db.execute('UPDATE inventory SET number=1 WHERE id=?',(gift['id'],))
  with self.assertRaisesRegex(GameError,'закончились'):self.upgrade(2)
 def test_transfer_preserves_item_and_replay(self):
  gift=self.upgrade()['gift'];key=secrets.token_hex(12);body={'item_id':gift['id'],'recipient_id':2}
  a=self.game.mutate(1,'/api/inventory/transfer',body,key);b=self.game.mutate(1,'/api/inventory/transfer',body,key)
  self.assertEqual(a,b);self.assertEqual(a['gift'],gift);self.assertNotIn(gift,self.state(1)['inventory']);self.assertIn(gift,self.state(2)['inventory'])
 def test_every_positive_model_can_be_selected_and_zero_weights_excluded(self):
  for c in self.game.collections.values():
   cursor=0
   for m in c['models']:
    if m['weight']<=0 or m.get('crafted'):continue
    with patch('main.secrets.randbelow',return_value=cursor):self.assertEqual(self.game.weighted_attribute(c['models'])['id'],m['id'])
    cursor+=m['weight']
  with patch('main.secrets.randbelow',return_value=0):self.assertEqual(self.game.weighted_attribute([{'id':'zero','weight':0},{'id':'crafted','weight':1,'crafted':True},{'id':'valid','weight':1}])['id'],'valid')
 def test_legacy_migration_assigns_valid_number_once(self):
  source=self.cat()['id']
  with self.game.db(write=True) as db:db.execute('UPDATE inventory SET gift_id=?,number=10000+id WHERE id=?',('scaredcat-nft',source))
  game=Game(self.game.database,demo=True);item=next(i for i in game.read(1,'/api/me')['state']['inventory'] if i['gift_id']=='scaredcat-nft')
  again=Game(self.game.database,demo=True).read(1,'/api/me')['state'];self.assertIn(item,again['inventory']);self.assertTrue(item['attributes']);self.assertEqual(item['collection_id'],'scared_cat')
if __name__=='__main__':unittest.main()

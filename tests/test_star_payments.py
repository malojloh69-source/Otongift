import os,sys,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import Game,GameError

class PaymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        with patch.dict(os.environ,{'BOT_TOKEN':'test-only-token','ENABLE_STAR_PAYMENTS':'true'}):
            self.game=Game(Path(self.tmp.name)/'data.sqlite3',demo=False)
        with self.game.db(True) as db:self.game.upsert_user(db,{'id':51,'first_name':'Покупатель'})
    def tearDown(self):self.tmp.cleanup()
    def order(self,xtr=2):
        with patch('main.telegram_api',return_value='https://t.me/$invoice') as send:
            order=self.game.create_star_invoice(51,xtr,'payment-key-123')
            self.assertEqual(send.call_args.args[2]['currency'],'XTR')
            self.assertNotIn('provider_token',send.call_args.args[2])
            self.assertEqual(send.call_args.args[2]['prices'][0]['amount'],xtr)
        with self.game.db() as db:payload=db.execute('SELECT payload FROM star_orders WHERE id=?',(order['order_id'],)).fetchone()[0]
        return order,payload
    def receipt(self,payload,amount=2,charge='charge-123'):
        return {'message':{'from':{'id':51},'successful_payment':{'invoice_payload':payload,'currency':'XTR','total_amount':amount,'telegram_payment_charge_id':charge}}}
    def test_invoice_does_not_credit_before_bot_receipt(self):
        order,payload=self.order()
        self.assertEqual(self.game.payment_status(51,order['order_id'])['status'],'pending')
        self.assertEqual(self.game.read(51,'/api/me')['state']['balance']['stars'],0)
        with self.assertRaises(GameError):self.game.payment_status(52,order['order_id'])
        with patch('main.telegram_api') as send:
            self.game.handle_payment_update({'pre_checkout_query':{'id':'pre','from':{'id':51},'invoice_payload':payload,'currency':'XTR','total_amount':2}})
            self.assertTrue(send.call_args.args[2]['ok'])
            self.game.handle_payment_update({'pre_checkout_query':{'id':'pre-duplicate','from':{'id':51},'invoice_payload':payload,'currency':'XTR','total_amount':2}})
            self.assertFalse(send.call_args.args[2]['ok'])
            self.game.handle_payment_update({'pre_checkout_query':{'id':'pre2','from':{'id':51},'invoice_payload':payload,'currency':'XTR','total_amount':3}})
            self.assertFalse(send.call_args.args[2]['ok'])
    def test_receipt_is_atomic_and_idempotent_under_parallel_retry(self):
        order,payload=self.order();update=self.receipt(payload)
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(self.game.handle_payment_update,[update]*4))
        self.assertEqual(self.game.payment_status(51,order['order_id'])['status'],'paid')
        self.assertEqual(self.game.read(51,'/api/me')['state']['balance']['stars'],200)
        self.assertEqual(self.game.create_star_invoice(51,2,'payment-key-123')['status'],'paid')
    def test_wrong_receipt_and_refund_debt(self):
        order,payload=self.order();self.game.handle_payment_update(self.receipt(payload,amount=1))
        self.assertEqual(self.game.read(51,'/api/me')['state']['balance']['stars'],0)
        self.game.handle_payment_update(self.receipt(payload))
        with self.game.db(True) as db:db.execute('UPDATE users SET stars=1000 WHERE id=51')
        refund={'message':{'refunded_payment':{'telegram_payment_charge_id':'charge-123'}}}
        self.game.handle_payment_update(refund);self.game.handle_payment_update(refund)
        state=self.game.read(51,'/api/me')['state']
        self.assertEqual(state['balance']['stars'],0)
        self.assertEqual(state['balance']['payment_debt_stars'],190)
        self.assertEqual(self.game.payment_status(51,order['order_id'])['status'],'refunded')
        with self.assertRaises(GameError):self.game.mutate(51,'/api/cases/open',{'case_id':'love'},'case-after-debt')
    def test_disabled_mode_never_accepts_receipt(self):
        self.game.payments_enabled=False
        with self.assertRaises(GameError):self.game.create_star_invoice(51,1,'payment-key-123')
        self.game.handle_payment_update(self.receipt('fake'))
        self.assertEqual(self.game.read(51,'/api/me')['state']['balance']['stars'],0)

    def test_gram_invoice_credits_only_after_receipt_and_refund_reverses_it(self):
        with patch('main.telegram_api',return_value='https://t.me/$gram') as send:
            order=self.game.create_star_invoice(51,2,'gram-payment-123','grams')
            self.assertEqual(send.call_args.args[2]['currency'],'XTR')
            self.assertIn('GRAM',send.call_args.args[2]['description'])
        self.assertEqual(order['credit'],1.6)
        self.assertEqual(self.game.read(51,'/api/me')['state']['balance']['grams'],0)
        with self.assertRaises(GameError):self.game.create_star_invoice(51,2,'gram-payment-123','stars')
        with self.game.db() as db:payload=db.execute('SELECT payload FROM star_orders WHERE id=?',(order['order_id'],)).fetchone()[0]
        update=self.receipt(payload,charge='gram-charge-123')
        self.game.handle_payment_update(update);self.game.handle_payment_update(update)
        self.assertEqual(self.game.read(51,'/api/me')['state']['balance']['grams'],1.6)
        self.game.handle_payment_update({'message':{'refunded_payment':{'telegram_payment_charge_id':'gram-charge-123'}}})
        self.assertEqual(self.game.read(51,'/api/me')['state']['balance']['grams'],0)
        self.assertEqual(self.game.payment_status(51,order['order_id'])['status'],'refunded')

if __name__=='__main__':unittest.main()

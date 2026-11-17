"""Synthetic date-only annotations never rewrite entries or replay trades."""
import os,unittest
from pathlib import Path
from datetime import date
from uuid import uuid4
import psycopg
from psycopg.conninfo import conninfo_to_dict
import test_combined_deployment_sql as baseline

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('APP_TEST_DATABASE'),'Isolated PostgreSQL required')
class PurchaseDayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options=conninfo_to_dict(os.environ['APP_TEST_DATABASE'])
        if not options.get('host','').startswith('/tmp/'):raise ValueError('Isolated database required')
        cls.db=psycopg.connect(**options)
        if cls.db.execute("SELECT to_regnamespace('auth')").fetchone()[0]:raise ValueError('Fresh database required')
        baseline.baseline(cls.db)
        for name in ['001_staging','019_saved_portfolio_claims','023_confirmed_purchase_days']:
            path=ROOT/'migrations/supabase'/f'{name}.sql'
            if not path.exists():path=next((ROOT/'migrations/supabase').glob('001*.sql'))
            cls.db.execute(path.read_text())
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):cls.db.rollback();cls.db.close()
    def setUp(self):self.db.execute('SAVEPOINT case_start')
    def tearDown(self):self.db.execute('RESET ROLE;ROLLBACK TO SAVEPOINT case_start;RELEASE SAVEPOINT case_start')
    def buy(self):
        uid=str(uuid4())
        self.db.execute("SELECT set_config('request.jwt.claim.sub',%s,true),set_config('request.jwt.claim.role','authenticated',true)",(baseline.OWNER,))
        self.db.execute("SELECT public.record_trade(%s,'buy','Alpha',1,12)",(uid,))
        return uid
    def annotate(self,uid,day='2026-09-20',owner=baseline.OWNER):
        return self.db.execute('SELECT portfolio_private.annotate_purchase_day(%s,%s,%s)',(owner,uid,day)).fetchone()[0]

    def test_confirmed_sunday_is_date_only_and_original_values_and_entry_timestamp_survive(self):
        uid=self.buy()
        original=self.db.execute('SELECT to_jsonb(a) FROM public.achats a WHERE id=%s',(uid,)).fetchone()[0]
        holdings=self.db.execute('SELECT to_jsonb(h) FROM public.portefeuille h WHERE user_id=%s',(baseline.OWNER,)).fetchall()
        self.assertEqual(self.annotate(uid),'ANNOTATED')
        after=self.db.execute('SELECT to_jsonb(a) FROM public.achats a WHERE id=%s',(uid,)).fetchone()[0]
        self.assertEqual(after['purchase_day'],'2026-09-20');self.assertEqual(after['purchase_day_basis'],'USER_CONFIRMED')
        for field in ['id','user_id','number','prix_achat','c_name','date']:self.assertEqual(after[field],original[field])
        self.assertEqual(self.db.execute('SELECT to_jsonb(h) FROM public.portefeuille h WHERE user_id=%s',(baseline.OWNER,)).fetchall(),holdings)
        self.assertEqual(self.db.execute('SELECT original_record,execution_time_status FROM portfolio_private.purchase_day_annotations').fetchone(),(original,'UNKNOWN'))

    def test_exact_retry_is_idempotent_and_different_day_is_rejected(self):
        uid=self.buy();self.annotate(uid)
        self.assertEqual(self.annotate(uid),'EXISTING')
        with self.assertRaises(psycopg.Error),self.db.transaction():self.annotate(uid,'2026-09-27')
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_private.purchase_day_annotations').fetchone()[0],1)

    def test_wrong_owner_future_day_and_missing_trade_are_rejected(self):
        uid=self.buy()
        for kwargs in [{'owner':baseline.OTHER},{'day':'2099-01-01'}]:
            with self.assertRaises(psycopg.Error),self.db.transaction():self.annotate(uid,**kwargs)
        with self.assertRaises(psycopg.Error),self.db.transaction():self.annotate(str(uuid4()))

    def test_ordinary_roles_cannot_supply_operator_dates_or_read_audit(self):
        uid=self.buy()
        for role in ['anon','authenticated','service_role']:
            with self.assertRaises(psycopg.Error),self.db.transaction():
                self.db.execute('SET LOCAL ROLE '+role);self.annotate(uid)
            self.db.execute('RESET ROLE')
            self.assertFalse(self.db.execute("SELECT has_table_privilege(%s,'portfolio_private.purchase_day_annotations','SELECT')",(role,)).fetchone()[0])

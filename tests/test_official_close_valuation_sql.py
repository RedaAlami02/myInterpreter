"""Synthetic official-close contract acceptance. Never asserts a real source exists."""
import copy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import unittest

import psycopg
from psycopg.conninfo import conninfo_to_dict

import test_combined_deployment_sql as baseline

ROOT=Path(__file__).resolve().parents[1]
OWNER=baseline.OWNER
OTHER=baseline.OTHER
NOW='2026-10-26 17:30'  # Local wall time, resolved using installed timezone rules.
PROVIDER='feed_0123456789abcdef'


@unittest.skipUnless(os.environ.get('APP_TEST_DATABASE'),'Isolated database not configured')
class OfficialCloseValuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options=conninfo_to_dict(os.environ['APP_TEST_DATABASE'])
        if not cls.options.get('host','').startswith('/tmp/'):raise RuntimeError('Only /tmp PostgreSQL permitted')
        cls.db=psycopg.connect(**cls.options)
        if cls.db.execute("SELECT to_regnamespace('auth')").fetchone()[0] is not None:raise RuntimeError('Fresh synthetic database required')
        baseline.baseline(cls.db)
        cls.db.execute('ALTER TABLE auth.users ADD COLUMN email text,ADD COLUMN email_confirmed_at timestamptz')
        cls.db.execute("UPDATE auth.users SET email='fixture@example.invalid',email_confirmed_at=clock_timestamp() WHERE id=%s",(OWNER,))
        for name in ['001_staging','009_private_object_archive','019_saved_portfolio_claims','021_official_close_valuation']:
            path=ROOT/f'migrations/supabase/{name}.sql'
            if not path.exists():path=next((ROOT/'migrations/supabase').glob('001*.sql'))
            cls.db.execute(path.read_text())
        cls.db.execute('INSERT INTO app_archive.providers(namespace) VALUES(%s)',(PROVIDER,))
        cls.db.execute("INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,completeness,compressed_bytes,object_path,state,verified_at) VALUES(%s,%s,'quotes','2026-10-26T15:00Z','2026-10-26T15:10Z','COMPLETE',100,%s,'STORED',clock_timestamp())",('b'*64,PROVIDER,'sha256/bb/'+'b'*64+'.json.gz'))
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):cls.db.rollback();cls.db.close()
    def setUp(self):self.db.execute("SAVEPOINT valuation_case;SET LOCAL statement_timeout='5s'")
    def tearDown(self):self.db.execute('RESET ROLE;ROLLBACK TO SAVEPOINT valuation_case;RELEASE SAVEPOINT valuation_case')

    def document(self,price='25'):
        return {'contract':'reviewed-official-closes/v1','price_basis':'OFFICIAL_CLOSE',
            'source_execution':'CURRENT_ACQUISITION','provider_namespace':PROVIDER,'source_policy_sha256':'a'*64,
            'archive_sha256':'b'*64,'session_day':'2026-10-26','is_trading_session':True,
            'session_close_at':'2026-10-26T15:00:00Z','published_at':'2026-10-26T15:05:00Z','captured_at':'2026-10-26T15:10:00Z',
            'rows':[{'company_id':'company-fixture','c_name':'Alpha','symbol':'AAA','price_decimal':price,
                     'observation_id':'c'*64,'raw_sha256':'d'*64}]}

    def register(self,doc=None):
        doc=self.document() if doc is None else doc
        self.db.execute('UPDATE portfolio_private.official_close_control SET provider_namespace=%s,source_policy_sha256=%s',(PROVIDER,'a'*64))
        text=json.dumps(doc,sort_keys=True,separators=(',',':'));pin=hashlib.sha256(text.encode()).hexdigest()
        return self.db.execute('SELECT portfolio_private.register_reviewed_official_closes(%s,%s)',(text,pin)).fetchone()[0]

    def enabled(self,doc=None):
        pin=self.register(doc)
        # Synthetic fixture authority exists before the synthetic execution.
        self.db.execute("UPDATE portfolio_private.official_close_batches SET reviewed_at='2026-10-26T15:15Z' WHERE sha256=%s",(pin,))
        self.db.execute('UPDATE portfolio_private.official_close_control SET enabled=true,active_batch_sha256=%s',(pin,))
        return pin

    def value(self,owner=OWNER,now=NOW):
        return self.db.execute("SELECT portfolio_private.record_official_valuation(%s,%s::timestamp AT TIME ZONE 'Africa/Casablanca')",(owner,now)).fetchone()[0]

    def rejected(self,doc):
        with self.assertRaises(psycopg.Error),self.db.transaction():self.register(doc)

    def test_default_off_no_prices_latest_shadow_or_legacy_fallback(self):
        self.assertEqual(self.value()['status'],'DISABLED')
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_private.official_valuation_receipts').fetchone()[0],0)

    def test_public_rpc_derives_authenticated_identity_and_stays_disabled(self):
        self.db.execute("SELECT set_config('request.jwt.claim.sub',%s,true),set_config('request.jwt.claim.role','authenticated',true)",(OWNER,))
        self.db.execute('SET LOCAL ROLE authenticated')
        self.assertEqual(self.db.execute('SELECT public.record_daily_valuation()').fetchone()[0]['status'],'DISABLED')
        self.assertEqual(self.db.execute('SELECT public.record_official_close_valuation()').fetchone()[0]['status'],'DISABLED')
        self.db.execute('RESET ROLE')
        with self.assertRaises(psycopg.errors.InsufficientPrivilege),self.db.transaction():
            self.db.execute('SET LOCAL ROLE anon');self.db.execute('SELECT public.record_daily_valuation()')
        with self.assertRaises(psycopg.errors.InsufficientPrivilege),self.db.transaction():
            self.db.execute('SET LOCAL ROLE anon');self.db.execute('SELECT public.record_official_close_valuation()')

    def test_future_approval_or_unstored_archive_cannot_be_consumed(self):
        self.enabled()
        with self.db.transaction(force_rollback=True):
            self.db.execute("UPDATE portfolio_private.official_close_batches SET reviewed_at='2099-01-01T00:00Z'")
            self.assertEqual(self.value()['status'],'PRICE_UNAVAILABLE')
        self.db.execute("UPDATE app_archive.objects SET state='RESERVED',verified_at=NULL")
        self.assertEqual(self.value()['status'],'PRICE_UNAVAILABLE')

    def test_source_policy_has_to_be_pinned_before_registration(self):
        doc=json.dumps(self.document());pin=hashlib.sha256(doc.encode()).hexdigest()
        with self.assertRaises(psycopg.errors.InsufficientPrivilege),self.db.transaction():
            self.db.execute('SELECT portfolio_private.register_reviewed_official_closes(%s,%s)',(doc,pin))

    def test_complete_approved_official_input_preserves_exact_consumed_prices_and_holdings(self):
        pin=self.enabled()
        self.db.execute('UPDATE public.latest_prices SET pa=999')
        result=self.value()
        self.assertEqual((result['status'],result['value']),('CREATED',30))
        row=self.db.execute('SELECT batch_sha256,holdings,consumed_prices,value,holdings_basis FROM portfolio_private.official_valuation_receipts WHERE user_id=%s',(OWNER,)).fetchone()
        self.assertEqual(row[0],pin);self.assertEqual(row[1][0]['quantity'],2)
        self.assertEqual(row[2][0]['price_decimal'],'25');self.assertEqual(row[3],30)
        self.assertEqual(row[4],'AT_EXECUTION')
        self.assertEqual(self.value(OTHER)['value'],75)

    def test_existing_records_never_recomputed_or_recertified(self):
        self.db.execute("INSERT INTO public.benefits(user_id,date,value) VALUES(%s,'2026-10-26',-7.5)",(OWNER,))
        self.assertEqual(self.value(),{'status':'EXISTING','date':'2026-10-26','value':-7.5,'basis':'PREEXISTING_UNVERIFIED'})
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_private.official_valuation_receipts').fetchone()[0],0)

    def test_first_official_snapshot_is_date_idempotent_after_trade_and_price_changes(self):
        self.enabled();first=self.value()
        self.db.execute('UPDATE public.portefeuille SET quantity=50 WHERE user_id=%s',(OWNER,))
        self.db.execute('UPDATE public.latest_prices SET pa=1')
        self.assertEqual(self.value(),{**first,'status':'EXISTING'})

    def test_shadow_reference_historical_and_unapproved_price_types_are_rejected(self):
        for key,value in [('price_basis','INTRADAY'),('price_basis','INSTRUMENT_REFERENCE'),
                          ('source_execution','RECORDED_REPLAY'),('contract','app-price-rows/v1'),
                          ('source_policy_sha256','e'*64),('portfolio_valuation_eligible',False)]:
            doc=self.document();doc[key]=value;self.rejected(doc)

    def test_missing_conflicting_or_misidentified_rows_never_create_partial_totals(self):
        self.enabled()
        self.db.execute("INSERT INTO public.portefeuille(user_id,c_name,quantity,total_cost) VALUES(%s,'Missing',1,10)",(OWNER,))
        self.assertEqual(self.value()['status'],'PRICE_UNAVAILABLE')
        self.assertEqual(self.db.execute("SELECT count(*) FROM public.benefits WHERE date='2026-10-26'").fetchone()[0],0)
        doc=self.document();doc['rows'].append(copy.deepcopy(doc['rows'][0]));self.rejected(doc)
        doc=self.document();doc['rows'][0]['company_id']='other';self.rejected(doc)

    def test_future_stale_wrong_day_naive_or_non_session_evidence_is_rejected(self):
        for key,value in [('captured_at','2099-10-26T15:10:00Z'),('captured_at','2026-10-26T15:10:00'),
                          ('published_at','2026-10-26T16:00:00Z'),('session_day','2026-10-25'),
                          ('is_trading_session',False)]:
            doc=self.document();doc[key]=value;self.rejected(doc)
        self.enabled()
        self.assertEqual(self.value(now='2026-10-27 17:30')['status'],'PRICE_UNAVAILABLE')

    def test_legacy_seventeen_to_nineteen_execution_window_is_preserved(self):
        self.enabled()
        for now in ['2026-10-26 16:30','2026-10-26 19:00','2026-10-25 17:30']:
            self.assertEqual(self.value(now=now)['status'],'OUTSIDE_WINDOW')

    def test_numeric_half_up_negative_rounding(self):
        self.enabled(self.document('9.4975'))
        self.assertEqual(self.value()['value'],-1.01)
        self.assertEqual(self.db.execute('SELECT value FROM portfolio_private.official_valuation_receipts').fetchone()[0],Decimal('-1.01'))

    def test_invalid_price_values_are_not_repaired(self):
        for price in ['0','-1','NaN','Infinity','1000000000001','1.000000001',True,25]:
            self.rejected(self.document(price))

    def test_unknown_source_clocks_stay_null_without_fabricating_them(self):
        document=self.document();document['published_at']=document['session_close_at']=None
        self.enabled(document)
        self.assertEqual(self.value()['status'],'CREATED')
        recorded=self.db.execute('SELECT document FROM portfolio_private.official_close_batches').fetchone()[0]
        self.assertIsNone(recorded['published_at']);self.assertIsNone(recorded['session_close_at'])
        document=self.document();document['captured_at']=None;self.rejected(document)

    def test_known_publication_day_cannot_precede_the_official_session(self):
        document=self.document();document['session_close_at']=None
        document['published_at']='2026-10-25T15:05:00Z';self.rejected(document)

    def test_ambiguous_company_to_symbol_mapping_is_not_valued(self):
        self.enabled()
        self.db.execute("INSERT INTO public.format(id,name,symbol) VALUES('another-class','Alpha','BBB')")
        self.assertEqual(self.value()['status'],'PRICE_UNAVAILABLE')
        self.rejected(self.document('25.01'))

    def test_private_tables_and_registration_not_exposed_to_app_roles(self):
        for role in ['anon','authenticated','service_role']:
            for table in ['official_close_control','official_close_batches','official_valuation_receipts']:
                self.assertFalse(self.db.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')",(role,'portfolio_private.'+table)).fetchone()[0])
            with self.assertRaises(psycopg.errors.InsufficientPrivilege),self.db.transaction():
                self.db.execute('SET LOCAL ROLE '+role);self.value()
            self.db.execute('RESET ROLE')

    def test_late_receipt_failure_rolls_back_the_benefit_insert(self):
        self.enabled()
        self.db.execute("CREATE FUNCTION portfolio_private.fail_test_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic receipt failure'; END $$;CREATE TRIGGER synthetic_receipt_failure BEFORE INSERT ON portfolio_private.official_valuation_receipts FOR EACH ROW EXECUTE FUNCTION portfolio_private.fail_test_receipt()")
        with self.assertRaises(psycopg.Error),self.db.transaction():self.value()
        self.assertEqual(self.db.execute("SELECT count(*) FROM public.benefits WHERE date='2026-10-26'").fetchone()[0],0)

    def test_trade_lock_and_control_lock_are_held_until_transaction_end(self):
        self.enabled();self.value()
        with psycopg.connect(**self.options) as other:
            self.assertFalse(other.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,73))',(OWNER,)).fetchone()[0])
            other.execute("SET LOCAL lock_timeout='50ms'")
            with self.assertRaises(psycopg.errors.LockNotAvailable),other.transaction():
                other.execute('UPDATE portfolio_private.official_close_control SET enabled=false')

    def test_repeatable_read_stale_holdings_snapshot_is_refused(self):
        with psycopg.connect(**self.options) as other:
            other.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            other.execute('SELECT count(*) FROM public.portefeuille')
            with self.assertRaises(psycopg.errors.InvalidParameterValue),other.transaction():
                other.execute("SELECT portfolio_private.record_official_valuation(%s,%s::timestamp AT TIME ZONE 'Africa/Casablanca')",(OWNER,NOW))

    def test_database_capacity_guard_precedes_financial_insert(self):
        self.enabled()
        self.db.execute('UPDATE portfolio_private.official_close_control SET max_database_bytes=1')
        with self.assertRaises(psycopg.errors.ProgramLimitExceeded),self.db.transaction():self.value()
        self.assertEqual(self.db.execute("SELECT count(*) FROM public.benefits WHERE date='2026-10-26'").fetchone()[0],0)

    def test_five_hundred_holdings_supported_and_five_hundred_one_rejected(self):
        self.db.execute('DELETE FROM public.portefeuille WHERE user_id=%s',(OWNER,))
        self.db.execute("INSERT INTO public.company(id,name) SELECT 'many-'||i,'Holding '||i FROM generate_series(0,500) i")
        self.db.execute("INSERT INTO public.format(id,name,symbol) SELECT 'many-'||i,'Holding '||i,'S'||i FROM generate_series(0,500) i")
        self.db.execute("INSERT INTO public.portefeuille(user_id,c_name,quantity,total_cost) SELECT %s,'Holding '||i,1,1 FROM generate_series(0,499) i",(OWNER,))
        document=self.document()
        document['rows']=[{'company_id':'many-'+str(i),'c_name':'Holding '+str(i),'symbol':'S'+str(i),
            'price_decimal':'2','observation_id':hashlib.sha256(str(i).encode()).hexdigest(),'raw_sha256':'d'*64} for i in range(500)]
        self.enabled(document)
        with self.db.transaction(force_rollback=True):
            self.assertEqual(self.value()['value'],500)
        self.db.execute("INSERT INTO public.portefeuille(user_id,c_name,quantity,total_cost) VALUES(%s,'Holding 500',1,1)",(OWNER,))
        with self.assertRaises(psycopg.errors.ProgramLimitExceeded),self.db.transaction():self.value()

    def test_one_observation_cannot_be_assigned_to_two_companies(self):
        self.db.execute("INSERT INTO public.company(id,name) VALUES('second','Second')")
        self.db.execute("INSERT INTO public.format(id,name,symbol) VALUES('second','Second','BBB')")
        document=self.document();second=copy.deepcopy(document['rows'][0])
        second.update(company_id='second',c_name='Second',symbol='BBB')
        document['rows'].append(second);self.rejected(document)

    def test_pending_saved_portfolio_recovery_blocks_direct_valuation(self):
        self.enabled()
        self.db.execute("INSERT INTO portfolio_private.recovery_bindings(email,legacy_owner,source_datasets,source_rows,plan_sha256) VALUES('fixture@example.invalid','one','[{},{},{},{}]','[{}]',repeat('a',64))")
        self.assertEqual(self.value()['status'],'RECOVERY_REQUIRED')

    def test_tracked_empty_portfolio_zero_and_never_tracked_empty_returns_empty(self):
        self.enabled();self.db.execute('DELETE FROM public.portefeuille')
        self.assertEqual(self.value()['value'],0)
        self.assertEqual(self.value(OTHER)['status'],'EMPTY')


if __name__=='__main__':unittest.main()

"""Official close automation on synthetic accounts only, rollback per case."""
import hashlib,json
from pathlib import Path
import test_recurring_acquisition_sql as recurring
import test_manual_trial_sql as legacy

ROOT=Path(__file__).resolve().parents[1]


class AutomatedOfficialCloseTests(recurring.RecurringAcquisitionSQLTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db.execute('ALTER TABLE auth.users ADD COLUMN email text,ADD COLUMN email_confirmed_at timestamptz')
        for name in ['001_staging.sql','019_saved_portfolio_claims.sql','021_official_close_valuation.sql','028_automated_official_closes.sql']:
            path=ROOT/'migrations/supabase'/name
            if not path.exists():path=next((ROOT/'migrations/supabase').glob('001*.sql'))
            cls.db.execute(path.read_text())
        cls.db.commit()

    def official(self):
        self.recurring()
        self.db.execute("UPDATE app_recurring.policies SET contract='recurring-official-close/v1',acquisition_window='OFFICIAL_CLOSE',capabilities=ARRAY['archive']")
        now=self.freeze_recurring_clock(18)
        self.db.execute("ALTER TABLE portfolio_private.official_close_batches ALTER COLUMN reviewed_at SET DEFAULT ('2026-11-03 18:04'::timestamp AT TIME ZONE 'Africa/Casablanca')")
        # Freeze only the new automation function and existing valuation helpers
        # inside this rollback-only fixture; production has no clock override.
        moment="('2026-11-03 18:05'::timestamp AT TIME ZONE 'Africa/Casablanca')"
        for signature in ['public.publish_official_close_batch_v1(text,text,text,text,text,text)',
            'portfolio_private.register_reviewed_official_closes(text,text)',
            'portfolio_private.record_official_valuation(uuid,timestamptz)']:
            definition=self.db.execute('SELECT pg_get_functiondef(%s::regprocedure)',(signature,)).fetchone()[0]
            self.db.execute(definition.replace('clock_timestamp()',moment))
        run=self.run_id();digest='6'*64
        self.db.execute("INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,completeness,compressed_bytes,object_path,state,verified_at) VALUES(%s,%s,'quotes',%s,%s,'COMPLETE',100,%s,'STORED',clock_timestamp())",(digest,legacy.PROVIDER,now.replace(minute=0),now,'sha256/66/'+digest+'.json.gz'))
        self.db.execute('INSERT INTO app_recurring.objects VALUES(%s,%s)',(digest,run))
        self.identities=json.dumps([{'company_id':'company-fixture','c_name':'Alpha','symbol':'AAA','isin':'MA0000000001'}],sort_keys=True,separators=(',',':'))
        self.db.execute("UPDATE portfolio_private.official_automation_control SET enabled=true,parser_sha256=repeat('a',64),identity_sha256=%s",(hashlib.sha256(self.identities.encode()).hexdigest(),))
        self.db.execute('UPDATE portfolio_private.official_close_control SET provider_namespace=%s,source_policy_sha256=repeat(\'a\',64)',(legacy.PROVIDER,))
        doc={'contract':'reviewed-official-closes/v1','price_basis':'OFFICIAL_CLOSE','source_execution':'CURRENT_ACQUISITION',
             'provider_namespace':legacy.PROVIDER,'source_policy_sha256':'a'*64,'archive_sha256':digest,
             'session_day':'2026-11-03','is_trading_session':True,'captured_at':now.isoformat(),'session_close_at':None,'published_at':None,
             'rows':[{'company_id':'company-fixture','c_name':'Alpha','symbol':'AAA','price_decimal':'25','observation_id':'c'*64,'raw_sha256':'d'*64}]}
        self.document=json.dumps(doc,sort_keys=True,separators=(',',':'))
        self.pin=hashlib.sha256(self.document.encode()).hexdigest()
        # Explicit owner-reviewed seed, then explicit master activation. Data
        # publication itself must never switch the master on.
        self.db.execute('SELECT portfolio_private.register_reviewed_official_closes(%s,%s)',(self.document,self.pin))
        self.db.execute('UPDATE portfolio_private.official_close_control SET enabled=true,active_batch_sha256=%s',(self.pin,))

    def publish_official(self,parser='a'*64,identities=None):
        proof=json.dumps({'contract':'official-close-attestation/v1','document_sha256':self.pin,
            'raw_sha256':'d'*64,'parser_sha256':parser,'identity_sha256':hashlib.sha256(self.identities.encode()).hexdigest(),
            'source_policy_sha256':'a'*64,'worker_commit':'e'*40,'verified_at':self.db.execute("SELECT ('2026-11-03 18:05'::timestamp AT TIME ZONE 'Africa/Casablanca')").fetchone()[0].isoformat()})
        return self.db.execute('SELECT public.publish_official_close_batch_v1(%s,%s,%s,%s,%s,%s)',(self.document,self.pin,parser,self.identities if identities is None else identities,proof,'f'*64)).fetchone()[0]

    def test_approved_master_without_first_batch_cannot_write_a_valuation(self):
        self.official()
        self.db.execute('UPDATE portfolio_private.official_close_control SET active_batch_sha256=NULL')
        moment=self.db.execute("SELECT ('2026-11-03 18:05'::timestamp AT TIME ZONE 'Africa/Casablanca')").fetchone()[0]
        result=self.db.execute('SELECT portfolio_private.record_official_valuation(%s,%s)',('11111111-1111-4111-8111-111111111111',moment)).fetchone()[0]
        self.assertEqual(result['status'],'PRICE_UNAVAILABLE')
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_private.official_valuation_receipts').fetchone()[0],0)
        result=self.publish_official()
        self.assertEqual(result['valuations_created'],2)

    def test_automatic_owners_are_internal_and_daily_retry_is_idempotent(self):
        self.official();result=self.publish_official()
        self.assertEqual(result['valuations_created'],2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM public.benefits WHERE date='2026-11-03'").fetchone()[0],2)
        self.assertEqual(self.publish_official()['valuations_existing'],2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_private.official_valuation_receipts').fetchone()[0],2)
        self.assertNotIn('user_id',json.dumps(result));self.assertNotIn('value',json.dumps(result))

    def test_wrong_parser_or_identity_pin_never_writes_financial_records(self):
        self.official()
        for parser,identities in [('b'*64,None),('a'*64,'[]')]:
            with self.assertRaises(Exception),self.db.transaction():self.publish_official(parser,identities)
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_private.official_valuation_receipts').fetchone()[0],0)

    def test_missing_holding_price_skips_only_that_owner(self):
        self.official()
        self.db.execute("INSERT INTO public.portefeuille(user_id,c_name,quantity,total_cost) VALUES(%s,'Unavailable company',1,10)",('22222222-2222-4222-8222-222222222222',))
        result=self.publish_official()
        self.assertEqual(result['valuations_created'],1);self.assertEqual(result['valuations_unavailable'],1)

    def test_regular_quotes_do_not_gain_an_official_close_window(self):
        self.recurring();now=self.freeze_recurring_clock(18)
        with self.assertRaises(Exception),self.db.transaction():self.db.execute("SELECT app_recurring.check_new_object(%s,'quotes',%s,%s,100)",(legacy.PROVIDER,now.replace(minute=0),now))
        self.db.execute("UPDATE app_recurring.policies SET contract='recurring-official-close/v1',acquisition_window='OFFICIAL_CLOSE',capabilities=ARRAY['archive']")
        self.db.execute("SELECT app_recurring.check_new_object(%s,'quotes',%s,%s,100)",(legacy.PROVIDER,now.replace(minute=0),now))

    def test_official_master_kill_switch_cannot_be_reenabled_by_a_report(self):
        self.official()
        self.db.execute('UPDATE portfolio_private.official_close_control SET enabled=false')
        with self.assertRaises(Exception),self.db.transaction():self.publish_official()
        self.assertFalse(self.db.execute('SELECT enabled FROM portfolio_private.official_close_control').fetchone()[0])
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_private.official_valuation_receipts').fetchone()[0],0)

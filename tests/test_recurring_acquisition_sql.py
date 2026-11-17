"""Additive recurring route on isolated synthetic PostgreSQL; never live data."""
from pathlib import Path
import test_price_company_context_sql as previous
import test_manual_trial_sql as legacy

ROOT = Path(__file__).resolve().parents[1]


class RecurringAcquisitionSQLTests(previous.PriceCompanyContextSQLTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manual_before = cls.db.execute("SELECT oid,pg_get_functiondef(oid),proacl::text FROM pg_proc WHERE pronamespace IN (SELECT oid FROM pg_namespace WHERE nspname IN ('app_trial','app_trial_legacy'))").fetchall()
        for name in ['022_positive_acquisition_admission.sql','026_recurring_acquisition.sql','027_recurring_publication.sql']:
            cls.db.execute((ROOT/'migrations/supabase'/name).read_text())
        cls.db.commit()

    def recurring(self, enabled=True, capabilities=None):
        self.enabled()
        self.db.execute("INSERT INTO app_recurring.policies(provider,policy_sha256,enabled,capabilities,kinds,max_objects_per_day,max_bytes_per_day,valid_until) VALUES(%s,repeat('a',64),%s,%s,ARRAY['quotes'],32,67108864,clock_timestamp()+interval '1 day')",(legacy.PROVIDER,enabled,capabilities or ['archive','shadow_feed','projections']))

    def run_id(self, capability='archive'):
        return self.db.execute("SELECT (app_recurring.require_lease(%s,%s)).id",(legacy.PROVIDER,capability)).fetchone()[0]

    def synthetic_bound_object(self):
        first=self.run_id();digest='9'*64
        self.db.execute("INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,completeness,compressed_bytes,object_path) VALUES(%s,%s,'quotes',clock_timestamp()-interval '1 minute',clock_timestamp(),'COMPLETE',100,%s)",(digest,legacy.PROVIDER,'sha256/99/'+digest+'.json.gz'))
        self.db.execute('INSERT INTO app_recurring.objects VALUES(%s,%s)',(digest,first))
        return first,digest

    def test_recurring_runs_do_not_create_or_modify_manual_leases(self):
        self.recurring();first=self.run_id();self.assertEqual(first,self.run_id())
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_trial.leases').fetchone()[0],0)
        for oid,body,acl in self.manual_before:
            self.assertEqual(self.db.execute('SELECT pg_get_functiondef(%s),proacl::text FROM pg_proc WHERE oid=%s',(oid,oid)).fetchone(),(body,acl))

    def test_disabled_policy_or_missing_capability_denies(self):
        self.recurring(enabled=False)
        with self.assertRaises(Exception),self.db.transaction():self.run_id()
        self.db.execute("UPDATE app_recurring.policies SET enabled=true,capabilities=ARRAY['archive']")
        with self.assertRaises(Exception),self.db.transaction():self.run_id('projections')

    def test_retry_after_run_expiry_keeps_original_binding(self):
        self.recurring();first,digest=self.synthetic_bound_object()
        self.db.execute("UPDATE app_recurring.runs SET created_at=statement_timestamp()-interval '20 minutes',expires_at=statement_timestamp()-interval '5 minutes' WHERE id=%s",(first,))
        next_run=self.db.execute("SELECT (app_recurring.bound_lease(%s,'archive')).id",(digest,)).fetchone()[0]
        self.assertNotEqual(first,next_run)
        self.assertEqual(self.db.execute('SELECT run_id FROM app_recurring.objects WHERE digest=%s',(digest,)).fetchone()[0],first)

    def test_policy_rotation_and_explicit_run_revocation_deny_retry(self):
        self.recurring();first,digest=self.synthetic_bound_object()
        self.db.execute("UPDATE app_recurring.policies SET policy_sha256=repeat('b',64)")
        with self.assertRaises(Exception),self.db.transaction():self.db.execute("SELECT app_recurring.bound_lease(%s,'archive')",(digest,))
        self.db.execute("UPDATE app_recurring.policies SET policy_sha256=repeat('a',64)")
        self.db.execute('UPDATE app_recurring.runs SET revoked_at=clock_timestamp() WHERE id=%s',(first,))
        with self.assertRaises(Exception),self.db.transaction():self.db.execute("SELECT app_recurring.bound_lease(%s,'archive')",(digest,))

    def test_legacy_objects_cannot_be_adopted(self):
        self.recurring()
        self.issue(seconds=600);self.stored('1'*64,'quotes')
        with self.assertRaises(Exception),self.db.transaction():self.db.execute("SELECT app_recurring.bound_lease(%s,'archive')",('1'*64,))

    def test_namespace_and_anonymous_execution_denied(self):
        self.recurring()
        with self.assertRaises(Exception),self.db.transaction():self.db.execute("SELECT app_recurring.require_lease('feed_ffffffffffffffff','archive')")
        for role in ['anon','authenticated','service_role']:
            self.assertFalse(self.db.execute("SELECT has_schema_privilege(%s,'app_recurring','USAGE')",(role,)).fetchone()[0])
        for role in ['anon','authenticated']:
            self.assertFalse(self.db.execute("SELECT has_function_privilege(%s,'public.finalize_market_archive_recurring_v1(text)','EXECUTE')",(role,)).fetchone()[0])

    def test_recovery_window_is_bounded(self):
        self.recurring();first,digest=self.synthetic_bound_object()
        self.db.execute("UPDATE app_recurring.runs SET created_at=statement_timestamp()-interval '49 hours',expires_at=statement_timestamp()-interval '48 hours 45 minutes' WHERE id=%s",(first,))
        with self.assertRaises(Exception),self.db.transaction():self.db.execute("SELECT app_recurring.bound_lease(%s,'archive')",(digest,))

    def test_complete_recurring_archive_publication_reference_read_and_app_rows(self):
        import hashlib,json
        from datetime import timedelta
        import app_feed,price_refresh
        self.recurring();active=self.run_id();real=self.db
        # Synthetic pre-I/O admission. No source request or real data is involved;
        # schedule chronology is checked separately by direct rejection tests.
        class FixtureConnection:
            def execute(inner,query,params=None):
                if query.startswith('SELECT public.reserve_market_archive('):
                    real.execute("INSERT INTO app_recurring.admissions(provider,kind,slot,run_id,admitted_at) SELECT %s,'quotes',%s,id,created_at FROM app_recurring.runs WHERE id=%s ON CONFLICT DO NOTHING",(legacy.PROVIDER,params[2],active))
                    query=query.replace('public.reserve_market_archive(', 'public.reserve_market_archive_recurring_v1(')
                if query.startswith('SELECT public.finalize_market_archive('):
                    query=query.replace('public.finalize_market_archive(', 'public.finalize_market_archive_recurring_v1(')
                return real.execute(query,params)
        self.db=FixtureConnection()
        try: quote=self.v2()
        finally:self.db=real
        text=app_feed.canonical(quote)
        self.db.execute('SELECT public.publish_shadow_market_candidate_recurring_v1(%s,%s)',(text,hashlib.sha256(text.encode()).hexdigest()))
        companies={row[0]['id']:{**row[0],'$updatedAt':(self.now-timedelta(days=1)).isoformat()} for row in self.db.execute('SELECT to_jsonb(co) FROM public.company co')}
        doc=price_refresh.publication(self.fixture_blob,quote['archive_sha256'],self.cfg,self.identities,companies,quote,as_of=self.now,field_bindings={})
        self.db.execute('UPDATE app_feed.application_control SET enabled=true,fields_sha256=%s',(app_feed.fingerprint({}),))
        self.db.execute('SELECT public.publish_shadow_application_rows_recurring_v1(%s,%s)',(app_feed.canonical(doc),app_feed.fingerprint(doc)))
        self.db.execute("SELECT set_config('request.jwt.claim.sub','00000000-0000-4000-8000-000000000001',true)")
        self.db.execute('SET LOCAL ROLE authenticated')
        result=self.db.execute('SELECT public.read_shadow_application_feed_recurring_v1()').fetchone()[0]
        self.db.execute('RESET ROLE')
        self.assertEqual(result['status'],'AVAILABLE')
        reference=next(r for r in result['rows'] if r['reference_price'] is not None)
        self.assertIsNone(reference['price_decimal'])
        self.assertEqual(reference['application_fields']['pa'],21.25)
        self.assertFalse(reference['portfolio_valuation_eligible'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_trial.leases').fetchone()[0],0)

    def test_current_run_cannot_claim_earlier_slot_or_offhours_capture(self):
        self.recurring()
        for slot,completed in [('2026-11-02T15:45Z','2026-11-02T20:00Z'),('2026-11-02T08:00Z','2026-11-02T10:00Z')]:
            with self.assertRaises(Exception),self.db.transaction():
                self.db.execute("SELECT app_recurring.check_new_object(%s,'quotes',%s,%s,100)",(legacy.PROVIDER,slot,completed))

    def test_retry_first_reservation_after_run_expiry_uses_persisted_admission(self):
        self.recurring();first=self.run_id()
        stamp=self.db.execute('SELECT clock_timestamp()').fetchone()[0]
        slot=stamp.replace(minute=stamp.minute//15*15,second=0,microsecond=0)
        self.db.execute("INSERT INTO app_recurring.admissions(provider,kind,slot,run_id,admitted_at) SELECT %s,'quotes',%s,id,created_at FROM app_recurring.runs WHERE id=%s",(legacy.PROVIDER,slot,first))
        # Expire by moving only the synthetic run's start/end around an earlier
        # captured moment, preserving a real pre-I/O admission before that moment.
        self.db.execute("UPDATE app_recurring.runs SET created_at=statement_timestamp()-interval '20 minutes',expires_at=statement_timestamp()-interval '5 minutes' WHERE id=%s",(first,))
        self.db.execute("UPDATE app_recurring.admissions SET admitted_at=clock_timestamp()-interval '19 minutes' WHERE run_id=%s",(first,))
        captured=self.db.execute("SELECT clock_timestamp()-interval '10 minutes'").fetchone()[0]
        slot = captured.replace(minute=captured.minute//15*15,second=0,microsecond=0)
        # Original ticket slot is retained exactly; it is not rebound to now.
        self.db.execute("UPDATE app_recurring.admissions SET slot=%s WHERE run_id=%s",(slot,first))
        result=self.db.execute("SELECT public.reserve_market_archive_recurring_v1(%s,%s,'quotes',%s,%s,'INCOMPLETE',100)",('8'*64,legacy.PROVIDER,slot,captured)).fetchone()[0]
        self.assertEqual(result['state'],'RESERVED')
        self.assertEqual(self.db.execute('SELECT run_id FROM app_recurring.objects WHERE digest=%s',('8'*64,)).fetchone()[0],first)

    def test_provider_projection_pins_do_not_mutate_legacy_singleton(self):
        self.recurring()
        other='feed_ffffffffffffffff'
        self.db.execute('INSERT INTO app_archive.providers VALUES(%s,true)',(other,))
        self.db.execute("INSERT INTO app_recurring.policies SELECT %s,contract,repeat('b',64),enabled,capabilities,ARRAY['fundamentals'],max_objects_per_day,max_bytes_per_day,recovery_hours,valid_until FROM app_recurring.policies WHERE provider=%s",(other,legacy.PROVIDER))
        self.db.execute("INSERT INTO app_recurring.projection_pins VALUES(%s,repeat('a',64),repeat('c',64),NULL),(%s,repeat('b',64),NULL,repeat('d',64))",(legacy.PROVIDER,other))
        before=self.db.execute('SELECT to_jsonb(c) FROM app_projection.control c').fetchone()[0]
        for provider,column,wanted in [(legacy.PROVIDER,'dividend_index_sha256','c'*64),(other,'fundamental_index_sha256','d'*64)]:
            value=self.db.execute('SELECT to_jsonb(c) FROM app_recurring.projection_control(%s) c',(provider,)).fetchone()[0]
            self.assertEqual(value['provider_namespace'],provider);self.assertEqual(value[column],wanted)
        self.assertEqual(self.db.execute('SELECT to_jsonb(c) FROM app_projection.control c').fetchone()[0],before)

    def test_subject_retry_keeps_one_original_completion_after_renewal(self):
        self.recurring()
        self.db.execute("UPDATE app_recurring.policies SET kinds=ARRAY['fundamentals']")
        first=self.run_id();digest='7'*64
        self.db.execute("INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,completeness,compressed_bytes,object_path) VALUES(%s,%s,'fundamentals',date_trunc('hour',clock_timestamp()),clock_timestamp(),'COMPLETE',100,%s)",(digest,legacy.PROVIDER,'sha256/77/'+digest+'.json.gz'))
        self.db.execute('INSERT INTO app_recurring.objects VALUES(%s,%s)',(digest,first))
        self.db.execute("INSERT INTO app_archive.subjects VALUES(%s,'symbol:AAA')",(digest,))
        self.db.execute("INSERT INTO storage.objects VALUES('private-market-evidence',%s,'{\"size\":100}')",('sha256/77/'+digest+'.json.gz',))
        self.db.execute("SELECT public.finalize_subject_market_archive_recurring_v1(%s,'symbol:AAA')",(digest,))
        self.db.execute("UPDATE app_recurring.runs SET created_at=statement_timestamp()-interval '20 minutes',expires_at=statement_timestamp()-interval '5 minutes' WHERE id=%s",(first,))
        self.db.execute("SELECT public.finalize_subject_market_archive_recurring_v1(%s,'symbol:AAA')",(digest,))
        self.assertEqual(self.db.execute('SELECT count(*),min(run_id::text) FROM app_recurring.subject_slots').fetchone(),(1,str(first)))

    def freeze_recurring_clock(self, hour):
        # Replace clocks only in rollback-only synthetic function copies. The
        # installed production definitions never expose a caller-settable clock.
        moment=f"('2026-11-03 {hour:02}:05:00'::timestamp AT TIME ZONE 'Africa/Casablanca')"
        definitions=self.db.execute("SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE p.prokind='f' AND (n.nspname='app_recurring' OR (n.nspname='public' AND p.proname LIKE '%%_recurring_v1'))").fetchall()
        for (definition,) in definitions:
            if 'clock_timestamp()' in definition:
                self.db.execute(definition.replace('clock_timestamp()',moment))
        self.db.execute("UPDATE app_recurring.policies SET valid_until='2026-11-05T23:00:00Z'")
        return self.db.execute('SELECT '+moment).fetchone()[0]

    def test_successful_quote_admission_persists_pre_io_ticket(self):
        self.price_prepare();self.db.execute('DELETE FROM app_trial.leases')
        self.db.execute("INSERT INTO app_recurring.policies(provider,policy_sha256,enabled,capabilities,kinds,max_objects_per_day,max_bytes_per_day,valid_until) VALUES(%s,repeat('a',64),true,ARRAY['archive','shadow_feed','projections'],ARRAY['quotes'],32,67108864,clock_timestamp()+interval '1 day')",(legacy.PROVIDER,))
        now=self.freeze_recurring_clock(10);slot=now.replace(minute=0,second=0,microsecond=0)
        admitted=self.db.execute('SELECT public.market_archive_acquisition_admission_recurring_v1(%s,\'quotes\',%s,true,true)',(legacy.PROVIDER,slot)).fetchone()[0]
        self.assertTrue(admitted)
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_recurring.admissions').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_trial.leases').fetchone()[0],0)

    def test_successful_fundamental_admission_uses_provider_pin_and_persists_ticket(self):
        self.recurring();self.db.execute("UPDATE app_recurring.policies SET kinds=ARRAY['fundamentals']")
        self.db.execute("UPDATE app_projection.control SET enabled=true,provider_namespace=%s,dividend_index_sha256=repeat('c',64),fundamental_index_sha256=repeat('b',64)",(legacy.PROVIDER,))
        self.db.execute("INSERT INTO app_recurring.projection_pins VALUES(%s,repeat('a',64),NULL,repeat('b',64))",(legacy.PROVIDER,))
        now=self.freeze_recurring_clock(18)
        admitted=self.db.execute("SELECT public.market_archive_subject_admission_recurring_v1(%s,'symbol:AAA',true)",(legacy.PROVIDER,)).fetchone()[0]
        self.assertTrue(admitted)
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_recurring.admissions').fetchone()[0],1)

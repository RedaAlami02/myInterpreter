"""Company-scoped acquisition on fresh synthetic PostgreSQL only; no source I/O."""
from pathlib import Path

import test_application_rows_sql as previous
import test_manual_trial_sql as legacy


class SubjectArchiveSQLTests(previous.ApplicationRowsSQLTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finalize_before = cls.db.execute("SELECT oid,proacl::text FROM pg_proc WHERE oid='public.finalize_market_archive(text)'::regprocedure").fetchone()
        cls.db.execute((Path(__file__).resolve().parents[1] / 'migrations/supabase/017_subject_archive_slots.sql').read_text())
        cls.db.commit()

    def subject_reserve(self, digest, symbol='AAA', complete='COMPLETE'):
        stamp = self.db.execute('SELECT clock_timestamp()').fetchone()[0]
        self.slot = stamp.replace(minute=0, second=0, microsecond=0)
        return self.db.execute('SELECT public.reserve_subject_market_archive(%s,%s,%s,%s,%s,%s,%s,%s)',
            (digest, legacy.PROVIDER, 'fundamentals', self.slot, stamp, complete, 100, 'symbol:' + symbol)).fetchone()[0]

    def subject_stored(self, digest, symbol='AAA', complete='COMPLETE'):
        self.subject_reserve(digest, symbol, complete)
        self.db.execute("INSERT INTO storage.objects VALUES('private-market-evidence',%s,'{\"size\":100}')",
            ('sha256/' + digest[:2] + '/' + digest + '.json.gz',))
        self.db.execute('SELECT public.finalize_subject_market_archive(%s,%s)', (digest, 'symbol:' + symbol))

    def subject_complete(self, symbol='AAA'):
        return self.db.execute('SELECT public.market_archive_subject_complete(%s,%s,%s,%s)',
            (legacy.PROVIDER, 'fundamentals', self.slot, 'symbol:' + symbol)).fetchone()[0]

    def denied(self, statement, parameters=()):
        with self.assertRaises(Exception):
            with self.db.transaction():
                self.db.execute(statement, parameters)

    def test_two_companies_same_hour_complete_independently_without_legacy_pollution(self):
        self.enabled()
        self.issue(kinds=['fundamentals'], objects=3)
        self.subject_stored('a' * 64)
        self.assertTrue(self.subject_complete())
        self.assertFalse(self.subject_complete('BBB'))
        self.subject_stored('b' * 64, 'BBB')
        self.assertTrue(self.subject_complete('BBB'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_archive.slots').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_archive.subject_slots').fetchone()[0], 2)

    def test_new_trial_same_company_same_hour_retains_both_digest_bindings(self):
        self.enabled()
        trial = self.issue(kinds=['fundamentals'])
        self.subject_stored('a' * 64)
        self.db.execute('SELECT app_trial.revoke(%s)', (trial,))
        self.issue(kinds=['fundamentals'])
        self.assertFalse(self.subject_complete())
        self.subject_stored('b' * 64)
        self.assertTrue(self.subject_complete())
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_archive.subject_slots').fetchone()[0], 2)

    def test_subject_cannot_be_reassigned_or_finalized_through_legacy_wrapper(self):
        self.enabled()
        self.issue(kinds=['fundamentals'], objects=3)
        self.subject_reserve('a' * 64)
        self.denied('SELECT public.finalize_subject_market_archive(%s,%s)', ('a' * 64, 'symbol:BBB'))
        self.denied('SELECT public.finalize_market_archive(%s)', ('a' * 64,))
        with self.assertRaises(Exception):
            with self.db.transaction():
                self.subject_reserve('a' * 64, 'BBB')
        self.assertEqual(self.db.execute('SELECT state FROM app_archive.objects').fetchone()[0], 'RESERVED')

    def test_existing_unscoped_archive_cannot_be_adopted(self):
        self.enabled()
        self.issue(kinds=['fundamentals'], objects=3)
        self.stored('a' * 64, 'fundamentals')
        with self.assertRaises(Exception):
            with self.db.transaction():
                self.subject_reserve('a' * 64)
        self.slot = self.db.execute('SELECT slot FROM app_archive.objects').fetchone()[0]
        self.assertFalse(self.subject_complete())

    def test_incomplete_object_is_preserved_without_completion(self):
        self.enabled()
        self.issue(kinds=['fundamentals'])
        self.subject_stored('a' * 64, complete='INCOMPLETE')
        self.assertFalse(self.subject_complete())
        self.assertEqual(self.db.execute('SELECT state FROM app_archive.objects').fetchone()[0], 'STORED')

    def test_subject_retry_preserves_bytes_and_verification_timestamp(self):
        self.enabled()
        self.issue(kinds=['fundamentals'])
        self.subject_stored('a' * 64)
        before = self.db.execute('SELECT to_jsonb(a) FROM app_archive.objects a').fetchone()[0]
        self.db.execute('SELECT public.finalize_subject_market_archive(%s,%s)', ('a' * 64, 'symbol:AAA'))
        self.assertEqual(self.db.execute('SELECT to_jsonb(a) FROM app_archive.objects a').fetchone()[0], before)
        self.db.execute("DELETE FROM storage.objects")
        self.denied('SELECT public.market_archive_subject_complete(%s,%s,%s,%s)',
            (legacy.PROVIDER, 'fundamentals', self.slot, 'symbol:AAA'))

    def test_revoked_trial_and_budget_are_enforced(self):
        self.enabled()
        trial = self.issue(kinds=['fundamentals'])
        self.subject_stored('a' * 64)
        with self.assertRaises(Exception):
            with self.db.transaction():
                self.subject_reserve('b' * 64, 'BBB')
        self.db.execute('SELECT app_trial.revoke(%s)', (trial,))
        self.assertFalse(self.subject_complete())
        self.denied('SELECT public.finalize_subject_market_archive(%s,%s)', ('a' * 64, 'symbol:AAA'))

    def test_new_tables_and_rpc_are_private_and_legacy_oid_acl_preserved(self):
        self.assertEqual(self.db.execute("SELECT oid,proacl::text FROM pg_proc WHERE oid='public.finalize_market_archive(text)'::regprocedure").fetchone(), self.finalize_before)
        for role in ('anon', 'authenticated', 'service_role'):
            for table in ('subjects', 'subject_slots'):
                self.assertFalse(self.db.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')",
                    (role, 'app_archive.' + table)).fetchone()[0])
            for signature in ('finalize_subject_market_archive(text,text)', 'market_archive_subject_admission(text,text,boolean)',
                              'market_archive_subject_complete(text,text,timestamptz,text)',
                              'reserve_subject_market_archive(text,text,text,timestamptz,timestamptz,text,bigint,text)'):
                self.assertEqual(self.db.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\')',
                    (role, 'public.' + signature)).fetchone()[0], role == 'service_role')

    def admission(self, projection=False):
        return self.db.execute('SELECT public.market_archive_subject_admission(%s,%s,%s)',
            (legacy.PROVIDER, 'symbol:AAA', projection)).fetchone()[0]

    def test_positive_admission_requires_live_controls_time_scope_and_full_capture_budget(self):
        self.assertFalse(self.admission())
        trial = self.issue(kinds=['fundamentals'], seconds=900, objects=3)
        self.assertFalse(self.admission())
        self.enabled()
        self.assertTrue(self.admission())
        self.assertFalse(self.admission(projection=True))
        self.subject_stored('a' * 64)
        # Existing manual leases cap total bytes at8MiB. Conservatively require
        # another full8MiB before another source request, never guess response size.
        self.assertFalse(self.admission())
        self.db.execute('SELECT app_trial.revoke(%s)', (trial,))
        self.assertFalse(self.admission())

    def test_admission_rejects_short_windows_wrong_kind_and_public_bucket(self):
        self.enabled()
        trial = self.issue(kinds=['quotes'], seconds=900)
        self.assertFalse(self.admission())
        self.db.execute('SELECT app_trial.revoke(%s)', (trial,))
        trial = self.issue(kinds=['fundamentals'], seconds=60)
        self.assertFalse(self.admission())
        self.db.execute('SELECT app_trial.revoke(%s)', (trial,))
        self.issue(kinds=['fundamentals'], seconds=900)
        self.db.execute('UPDATE storage.buckets SET public=true')
        self.assertFalse(self.admission())

    def test_projection_admission_requires_projection_capability_and_exact_provider_control(self):
        self.enabled()
        self.issue(kinds=['fundamentals'], seconds=900, capabilities=['archive','projections'])
        self.assertFalse(self.admission(projection=True))
        self.db.execute("UPDATE app_projection.control SET enabled=true,provider_namespace=%s,dividend_index_sha256=repeat('a',64),fundamental_index_sha256=repeat('b',64)", (legacy.PROVIDER,))
        self.assertTrue(self.admission(projection=True))
        self.db.execute('UPDATE app_projection.control SET provider_namespace=%s', ('feed_ffffffffffffffff',))
        self.assertFalse(self.admission(projection=True))

    def test_admission_checks_database_storage_unknown_sizes_and_outstanding_reservations(self):
        self.enabled()
        self.issue(kinds=['fundamentals'], seconds=900)
        self.assertTrue(self.admission())
        self.db.execute('UPDATE app_archive.control SET max_database_bytes=1')
        self.assertFalse(self.admission())
        self.db.execute('UPDATE app_archive.control SET max_database_bytes=350000000,max_storage_bytes=8388608')
        self.assertTrue(self.admission())
        self.db.execute("INSERT INTO storage.objects VALUES('other','unknown','{}')")
        self.assertFalse(self.admission())
        self.db.execute("UPDATE storage.objects SET metadata='{\"size\":1}'")
        self.assertFalse(self.admission())
        self.db.execute('DELETE FROM storage.objects')
        self.assertTrue(self.admission())
        self.db.execute("SELECT app_trial_legacy.reserve_market_archive(repeat('b',64),%s,'fundamentals',clock_timestamp(),clock_timestamp(),'COMPLETE',100)", (legacy.PROVIDER,))
        self.assertFalse(self.admission())

    def test_service_subject_rpc_executes_without_direct_private_table_grants(self):
        self.enabled()
        self.issue(kinds=['fundamentals'], seconds=900)
        self.db.execute('SET LOCAL ROLE service_role')
        self.assertTrue(self.admission())
        reservation = self.subject_reserve('a' * 64)
        self.db.execute('RESET ROLE')
        self.db.execute("INSERT INTO storage.objects VALUES('private-market-evidence',%s,'{\"size\":100}')", (reservation['object_path'],))
        self.db.execute('SET LOCAL ROLE service_role')
        self.db.execute('SELECT public.finalize_subject_market_archive(%s,%s)', ('a' * 64, 'symbol:AAA'))
        self.assertTrue(self.subject_complete())

"""Synthetic manual-window acceptance; explicitly configured /tmp socket only."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

import test_combined_deployment_sql as baseline
import test_projection_sql as projection
import test_shadow_market_feed_sql as feed

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = 'feed_0123456789abcdef'
SIGNATURES = (
    'reserve_market_archive(text,text,text,timestamptz,timestamptz,text,bigint)',
    'finalize_market_archive(text)', 'market_archive_slot_complete(text,text,timestamptz)',
    'publish_shadow_market_candidate(text,text)', 'read_shadow_market_feed()',
    'publish_dividend_projection(text,text)', 'publish_fundamental_projection(text,text)',
)


@unittest.skipUnless(os.environ.get('APP_TEST_DATABASE'), 'Isolated database not configured')
class ManualTrialSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = conninfo_to_dict(os.environ['APP_TEST_DATABASE'])
        if not cls.options.get('host', '').startswith('/tmp/'):
            raise RuntimeError('Only an isolated /tmp Unix socket is permitted')
        cls.db = psycopg.connect(**cls.options)
        if cls.db.execute("SELECT to_regnamespace('auth')").fetchone()[0] is not None:
            cls.db.close()
            raise RuntimeError('Fresh synthetic database required')
        baseline.baseline(cls.db)
        cls.before = baseline.snapshot(cls.db)
        for name in ('009_private_object_archive', '010_shadow_market_feed', '013_projection_publication'):
            cls.db.execute((ROOT / f'migrations/supabase/{name}.sql').read_text())
        cls.legacy = {s: cls.db.execute(
            'SELECT oid,prosrc,proacl::text FROM pg_proc WHERE oid=to_regprocedure(%s)',
            ('public.' + s,)).fetchone() for s in SIGNATURES}
        cls.db.execute((ROOT / 'migrations/supabase/014_manual_trial_leases.sql').read_text())
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.rollback()
        cls.db.close()

    def setUp(self):
        self.db.execute('SAVEPOINT trial_case')
        self.db.execute('SET LOCAL statement_timeout=5000')

    def tearDown(self):
        self.db.execute('RESET ROLE; ROLLBACK TO SAVEPOINT trial_case; RELEASE SAVEPOINT trial_case')

    def issue(self, capabilities=None, kinds=None, seconds=60, objects=1, size=8388608, plan='a' * 64):
        return self.db.execute('SELECT app_trial.issue(%s,%s,%s,%s,%s,%s,%s)',
            (PROVIDER, plan, capabilities or ['archive', 'shadow_feed'], kinds or ['quotes'],
             seconds, objects, size)).fetchone()[0]

    def enabled(self):
        self.db.execute('UPDATE app_archive.control SET enabled=true')
        self.db.execute('INSERT INTO app_archive.providers VALUES(%s,true)', (PROVIDER,))
        self.db.execute("INSERT INTO storage.buckets VALUES('private-market-evidence',false)")

    def reserve(self, digest='1' * 64, kind='quotes', size=100, stamp=None):
        stamp = stamp or self.db.execute('SELECT clock_timestamp()').fetchone()[0]
        return self.db.execute("SELECT public.reserve_market_archive(%s,%s,%s,%s,%s,'COMPLETE',%s)",
            (digest, PROVIDER, kind, stamp.replace(minute=0, second=0, microsecond=0), stamp, size)).fetchone()[0]

    def stored(self, digest, kind):
        self.reserve(digest, kind)
        self.db.execute("INSERT INTO storage.objects VALUES('private-market-evidence',%s,'{\"size\":100}')",
            ('sha256/' + digest[:2] + '/' + digest + '.json.gz',))
        self.db.execute('SELECT public.finalize_market_archive(%s)', (digest,))

    def prepared(self, **kwargs):
        self.cfg = feed.config()
        self.cfg['recipe']['expected_index_identities'] = ['MASI']
        self.cfg['recipe']['views']['indices']['constants']['source_identity'] = 'MASI'
        self.identities = feed.mapping()
        for stock, company_id, name, symbol in zip(self.identities['stocks'],
                ['company-fixture', 'b'], ['Alpha', 'Company B'], ['AAA', 'B']):
            stock.update(company_id=company_id, asset_key='company:' + company_id, c_name=name, symbol=symbol)
        self.identities['indices'] = [dict(source_identity='MASI', company_id=None,
            asset_key='index:MASI', c_name='MASI', symbol='MASI')]
        self.db.execute("INSERT INTO public.company(id,name) VALUES('b','Company B'); INSERT INTO public.format VALUES('fb','Company B','B')")
        self.db.execute('UPDATE app_feed.control SET enabled=true,provider_namespace=%s,mapping_sha256=%s,recipe_sha256=%s',
            (PROVIDER, feed.app_feed.fingerprint(self.identities), feed.app_feed.fingerprint(self.cfg['recipe'])))
        self.now = self.db.execute('SELECT clock_timestamp()').fetchone()[0]
        return feed.ShadowFeedSQLTests.prepared(self, **kwargs)

    def publish(self, value):
        return feed.ShadowFeedSQLTests.publish(self, value)

    def read(self):
        return feed.ShadowFeedSQLTests.read(self)

    def test_install_preserves_original_values_and_legacy_bodies_oids(self):
        self.assertEqual(baseline.snapshot(self.db), self.before)
        for signature, old in self.legacy.items():
            moved = self.db.execute('SELECT oid,prosrc FROM pg_proc WHERE oid=to_regprocedure(%s)',
                ('app_trial_legacy.' + signature,)).fetchone()
            self.assertEqual(moved, old[:2])
        for schema in ('app_archive', 'app_feed', 'app_projection'):
            self.assertFalse(self.db.execute(f'SELECT enabled FROM {schema}.control').fetchone()[0])

    def test_private_tables_and_all_legacy_functions_deny_app_roles(self):
        for role in ('anon', 'authenticated', 'service_role'):
            self.assertEqual(self.db.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('app_trial','app_trial_legacy') AND has_function_privilege(%s,p.oid,'EXECUTE')", (role,)).fetchone()[0], 0)
            self.assertEqual(self.db.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='app_trial' AND c.relkind='r' AND has_table_privilege(%s,c.oid,'SELECT,INSERT,UPDATE,DELETE')", (role,)).fetchone()[0], 0)

    def test_exact_public_role_boundary(self):
        for signature in SIGNATURES:
            for role in ('anon', 'authenticated', 'service_role'):
                expected = (role == 'authenticated') if signature.startswith('read_') else (role == 'service_role')
                self.assertEqual(self.db.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\')',
                    (role, 'public.' + signature)).fetchone()[0], expected)

    def test_lease_without_global_control_cannot_reserve(self):
        self.issue()
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.reserve()

    def test_enabled_global_control_without_lease_cannot_reserve(self):
        self.enabled()
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.reserve()

    def test_owner_issue_is_bounded_and_rejects_missing_archive_capability(self):
        for seconds, caps in ((0, ['archive']), (901, ['archive']), (None, ['archive']), (60, ['shadow_feed'])):
            with self.assertRaises(psycopg.Error), self.db.transaction():
                self.issue(seconds=seconds, capabilities=caps)

    def test_service_cannot_issue_revoke_or_directly_call_legacy(self):
        self.db.execute('SET LOCAL ROLE service_role')
        for query in ("SELECT app_trial.issue('feed_0123456789abcdef',repeat('a',64),ARRAY['archive'],ARRAY['quotes'])",
                      'SELECT app_trial.revoke(gen_random_uuid())', "SELECT app_trial_legacy.finalize_market_archive(repeat('a',64))"):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
                self.db.execute(query)

    def test_no_implicit_conflicting_plan_replacement(self):
        self.issue()
        with self.assertRaises(psycopg.errors.UniqueViolation), self.db.transaction():
            self.issue(plan='b' * 64)

    def test_exact_reservation_retry_uses_one_budget_unit(self):
        self.enabled()
        trial = self.issue()
        stamp = self.db.execute('SELECT clock_timestamp()').fetchone()[0]
        self.assertEqual(self.reserve(stamp=stamp), self.reserve(stamp=stamp))
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_trial.objects WHERE trial_id=%s', (trial,)).fetchone()[0], 1)

    def test_service_can_reserve_finalize_and_confirm_bound_slot(self):
        self.enabled()
        self.issue()
        stamp = self.db.execute('SELECT clock_timestamp()').fetchone()[0]
        self.db.execute('SET LOCAL ROLE service_role')
        reservation = self.reserve(stamp=stamp)
        self.db.execute('RESET ROLE')
        self.db.execute("INSERT INTO storage.objects VALUES('private-market-evidence',%s,'{\"size\":100}')",
            (reservation['object_path'],))
        self.db.execute('SET LOCAL ROLE service_role')
        self.assertEqual(self.db.execute('SELECT public.finalize_market_archive(%s)', ('1' * 64,)).fetchone()[0], '1' * 64)
        self.assertTrue(self.db.execute("SELECT public.market_archive_slot_complete(%s,'quotes',%s)",
            (PROVIDER, stamp.replace(minute=0, second=0, microsecond=0))).fetchone()[0])

    def test_service_can_publish_shadow_for_authenticated_preview(self):
        self.enabled()
        self.issue()
        value = self.prepared()
        self.db.execute('SET LOCAL ROLE service_role')
        self.assertEqual(self.publish(value), hashlib.sha256(feed.app_feed.canonical(value).encode()).hexdigest())
        self.db.execute('RESET ROLE')
        self.assertEqual(self.read()['status'], 'AVAILABLE')

    def test_wrong_kind_old_capture_and_object_or_byte_budget_rejected(self):
        self.enabled()
        self.issue(size=100)
        for kwargs in (dict(kind='depth'), dict(stamp=datetime(2000, 1, 1, tzinfo=timezone.utc)), dict(size=101)):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
                self.reserve(**kwargs)
        self.reserve()
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.reserve('2' * 64)

    def test_legacy_unbound_reservation_cannot_be_adopted(self):
        self.enabled()
        self.issue()
        stamp = self.db.execute('SELECT clock_timestamp()').fetchone()[0]
        self.db.execute("SELECT app_trial_legacy.reserve_market_archive(%s,%s,'quotes',%s,%s,'COMPLETE',100)",
            ('1' * 64, PROVIDER, stamp, stamp))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.reserve()

    def test_expiry_uses_wall_clock_and_rolls_back_mutation(self):
        self.enabled()
        self.issue(seconds=1)
        self.db.execute("""CREATE FUNCTION app_trial.test_delay() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN PERFORM pg_sleep(1.1); RETURN NEW; END $$;
            CREATE TRIGGER delay_reservation BEFORE INSERT ON app_archive.objects
            FOR EACH ROW EXECUTE FUNCTION app_trial.test_delay();""")
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.reserve()
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_archive.objects').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_trial.objects').fetchone()[0], 0)

    def test_revoke_prevents_finalization_and_slot_success(self):
        self.enabled()
        trial = self.issue()
        self.reserve()
        self.db.execute('SELECT app_trial.revoke(%s)', (trial,))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.db.execute('SELECT public.finalize_market_archive(%s)', ('1' * 64,))
        self.assertFalse(self.db.execute("SELECT public.market_archive_slot_complete(%s,'quotes',clock_timestamp())", (PROVIDER,)).fetchone()[0])

    def test_new_trial_cannot_finalize_or_publish_old_trial_evidence(self):
        self.enabled()
        trial = self.issue()
        value = self.prepared()
        self.db.execute('SELECT app_trial.revoke(%s)', (trial,))
        self.issue(plan='b' * 64)
        for action in (lambda: self.db.execute('SELECT public.finalize_market_archive(%s)', (value['archive_sha256'],)),
                       lambda: self.publish(value)):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
                action()

    def test_active_preview_keeps_values_order_and_caps_original_trial_deadline(self):
        self.enabled()
        trial = self.issue()
        value = self.prepared()
        self.publish(value)
        result = self.read()
        legacy = self.db.execute('SELECT app_trial_legacy.read_shadow_market_feed()').fetchone()[0]
        deadline = self.db.execute('SELECT expires_at FROM app_trial.leases WHERE id=%s', (trial,)).fetchone()[0]
        self.assertEqual(result['status'], 'AVAILABLE')
        self.assertEqual([r['asset_key'] for r in result['rows']], [r['asset_key'] for r in legacy['rows']])
        self.assertTrue(any(r['price_decimal'] is not None for r in result['rows']))
        for actual, original in zip(result['rows'], legacy['rows']):
            if original['expires_at'] is not None:
                self.assertLessEqual(datetime.fromisoformat(actual['expires_at']), deadline)
            self.assertEqual({k: v for k, v in actual.items() if k != 'expires_at'},
                             {k: v for k, v in original.items() if k != 'expires_at'})

    def test_revoked_preview_not_reactivated_by_new_plan(self):
        self.enabled()
        trial = self.issue()
        self.publish(self.prepared())
        self.db.execute('SELECT app_trial.revoke(%s)', (trial,))
        self.assertEqual(self.read()['status'], 'DISABLED')
        self.issue(plan='b' * 64)
        result = self.read()
        self.assertEqual((result['status'], result['rows']), ('DISABLED', []))

    def test_preview_authentication_is_checked_even_when_disabled(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.db.execute('SELECT public.read_shadow_market_feed()')

    def test_archive_only_trial_cannot_publish_shadow_candidate(self):
        self.enabled()
        self.issue(capabilities=['archive'])
        value = self.prepared()
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.publish(value)

    def test_disabling_shadow_control_stops_publication_with_active_trial(self):
        self.enabled()
        self.issue()
        value = self.prepared()
        self.db.execute('UPDATE app_feed.control SET enabled=false')
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.publish(value)
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_feed.latest').fetchone()[0], 0)

    def test_namespace_conflict_cannot_borrow_bound_evidence(self):
        self.enabled()
        self.issue()
        value = self.prepared()
        value['provider_namespace'] = 'feed_fedcba9876543210'
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.publish(value)

    def test_projection_calls_require_trial_capability(self):
        self.enabled()
        self.issue(capabilities=['archive'], kinds=['dividends', 'fundamentals'], objects=2)
        for kind, digest, document in (('dividends', projection.DIVIDEND_DIGEST, projection.dividend_document()),
                ('fundamentals', projection.FUNDAMENTAL_DIGEST, projection.fundamental_document())):
            self.stored(digest, kind)
            text = json.dumps(document)
            function = 'publish_dividend_projection' if kind == 'dividends' else 'publish_fundamental_projection'
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
                self.db.execute(f'SELECT public.{function}(%s,%s)', (text, hashlib.sha256(text.encode()).hexdigest()))

    def test_positive_projection_receipts_unchanged_in_isolated_database(self):
        self.enabled()
        self.issue(capabilities=['archive', 'projections'], kinds=['dividends', 'fundamentals'], objects=2)
        self.db.execute('UPDATE app_projection.control SET enabled=true,provider_namespace=%s,dividend_index_sha256=%s,fundamental_index_sha256=%s',
            (PROVIDER, projection.DIVIDEND_INDEX, projection.FUNDAMENTAL_INDEX))
        for kind, digest, document, expected in (('dividends', projection.DIVIDEND_DIGEST, projection.dividend_document(), 'PUBLISHED'),
                ('fundamentals', projection.FUNDAMENTAL_DIGEST, projection.fundamental_document(), 'UPDATED')):
            self.stored(digest, kind)
            text = json.dumps(document)
            function = 'publish_dividend_projection' if kind == 'dividends' else 'publish_fundamental_projection'
            result = self.db.execute(f'SELECT public.{function}(%s,%s)', (text, hashlib.sha256(text.encode()).hexdigest())).fetchone()[0]
            self.assertEqual(result['status'], expected)

    def test_parallel_revoke_is_busy_until_inflight_transaction_ends(self):
        with psycopg.connect(**self.options) as first, psycopg.connect(**self.options) as second:
            first.execute('SET LOCAL statement_timeout=2000; SELECT app_trial.lock_gate()')
            second.execute('SET LOCAL statement_timeout=2000')
            with self.assertRaises(psycopg.errors.LockNotAvailable), second.transaction():
                second.execute('SELECT app_trial.revoke(%s)', (uuid4(),))
            first.rollback()
            with self.assertRaises(psycopg.errors.InvalidParameterValue), second.transaction():
                second.execute('SELECT app_trial.revoke(%s)', (uuid4(),))

    def test_repeatable_read_snapshot_cannot_bypass_revocation_visibility(self):
        with psycopg.connect(**self.options) as other:
            other.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            with self.assertRaises(psycopg.errors.InvalidTransactionState), other.transaction():
                other.execute('SELECT app_trial.lock_gate()')

    def test_unbounded_outer_statement_is_rejected_before_admission(self):
        with psycopg.connect(**self.options) as other:
            other.execute('SET LOCAL statement_timeout=0')
            with self.assertRaises(psycopg.errors.ObjectNotInPrerequisiteState), other.transaction():
                other.execute('SELECT app_trial.lock_gate()')

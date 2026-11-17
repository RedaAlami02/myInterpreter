"""Read-only catalog/clock probes with an injected database; no external I/O."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import check_deployment_readiness as module

NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
CONFIG = {'SUPABASE_PROJECT_URL': 'https://abcdefghijklmnopqrst.supabase.co',
          'SUPABASE_DATABASE_URL': 'postgresql://postgres:fixture-password@db.abcdefghijklmnopqrst.supabase.co/postgres'}


class Database:
    def __init__(self, *, installed=False, size=332_000_000, clock_shift=0, unknown=0,
                 public=0, controls=None, readonly='on', tls=True):
        self.installed = installed
        self.size = size
        self.clock_shift = clock_shift
        self.unknown = unknown
        self.public = public
        self.controls = controls if controls is not None else [(False,)]
        self.readonly = readonly
        self.pgconn = SimpleNamespace(ssl_in_use=tls)
        self.calls = []
        self.rows = []
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, args=None):
        text = statement if isinstance(statement, str) else statement.as_string()
        text = ' '.join(text.split())
        self.calls.append(text)
        if not text.startswith('SET') and not self.calls[0].endswith('READ ONLY'):
            raise AssertionError('Query before read-only transaction')
        if text.startswith('SET'):
            self.rows = []
        elif text.startswith('SELECT pg_database_size'):
            self.rows = [(self.size, self.readonly)]
        elif 'FROM storage.objects' in text:
            self.rows = [(0, self.unknown, 0)]
        elif 'FROM storage.buckets' in text:
            self.rows = [(int(self.installed), self.public, int(self.installed), int(self.installed))]
        elif 'to_regnamespace' in text or 'to_regprocedure' in text or 'to_regclass' in text:
            self.rows = [(self.installed,)]
        elif text.startswith('SELECT enabled FROM'):
            self.rows = self.controls
        elif 'FROM unnest' in text:
            self.rows = [(stamp, stamp.astimezone(ZoneInfo(module.ZONE)).replace(tzinfo=None)
                          + timedelta(hours=self.clock_shift)) for stamp in args[1]]
        else:
            raise AssertionError('Unexpected SQL operation')
        return self

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows

    def rollback(self):
        self.rolled_back = True


class DeploymentReadinessTests(unittest.TestCase):
    def test_clock_samples_are_aware_unique_and_cover_replay_and_future(self):
        values = module.sample_instants(NOW)
        self.assertEqual(values, sorted(set(values)))
        self.assertTrue(all(value.tzinfo is not None for value in values))
        self.assertIn(datetime(2026, 9, 30, 12, tzinfo=timezone.utc), values)
        self.assertGreater(values[-1], NOW + timedelta(days=300))
        with self.assertRaises(ValueError):
            module.sample_instants(NOW.replace(tzinfo=None))

    def test_complete_clock_comparison_and_no_empty_success(self):
        value = NOW.astimezone(ZoneInfo(module.ZONE)).replace(tzinfo=None)
        self.assertTrue(module.compare_clocks([(NOW, value)])['passed'])
        self.assertFalse(module.compare_clocks([])['passed'])
        result = module.compare_clocks([(NOW, value + timedelta(hours=1))])
        self.assertEqual(result['mismatch_count'], 1)
        self.assertFalse(result['passed'])

    def test_transaction_is_read_only_before_queries_and_explicitly_rolled_back(self):
        db = Database()
        report = module.collect(db, NOW)
        self.assertEqual(db.calls[0], 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        self.assertTrue(db.rolled_back)
        self.assertTrue(report['read_only'])
        self.assertFalse(report['live_resources_changed'])
        self.assertEqual(report['database_guard_headroom_bytes'], 18_000_000)
        self.assertEqual(report['controls']['app_archive.control']['state'], 'NOT_INSTALLED')
        self.assertIn('PRIVATE_ARCHIVE_BUCKET_NOT_READY', report['confirmed_blockers'])
        self.assertIn('STAGED_SERVICES_NOT_FULLY_INSTALLED', report['confirmed_blockers'])

    def test_installed_disabled_does_not_invent_approval_quota_or_readiness(self):
        report = module.collect(Database(installed=True), NOW)
        self.assertEqual(report['confirmed_blockers'], [])
        self.assertEqual(report['controls']['app_feed.control']['state'], 'DISABLED')
        self.assertFalse(report['activation_ready'])
        self.assertIn('SCOPED_DEPLOYMENT_AUTHORIZATION', report['not_assessed'])
        self.assertIn('ORGANIZATION_STORAGE_HEADROOM', report['not_assessed'])

    def test_enabled_and_invalid_control_rows_are_distinguished(self):
        report = module.collect(Database(installed=True, controls=[(True,)]), NOW)
        self.assertEqual(report['controls']['app_feed.control']['state'], 'ENABLED')
        for rows in [[], [(False,), (False,)]]:
            report = module.collect(Database(installed=True, controls=rows), NOW)
            self.assertIn('INVALID_CONTROL_ROWS', report['confirmed_blockers'])

    def test_timezone_capacity_unknown_sizes_and_public_bucket_fail_closed(self):
        report = module.collect(Database(size=350_000_000, clock_shift=1, unknown=1, public=1, tls=False), NOW)
        self.assertEqual(report['database_guard_headroom_bytes'], 0)
        for blocker in ['HOSTED_PYTHON_TIMEZONE_MISMATCH', 'DATABASE_AT_OR_OVER_STAGED_GUARD',
                        'UNKNOWN_OBJECT_SIZES', 'PUBLIC_STORAGE_BUCKET_EXISTS', 'SQL_TLS_NOT_ACTIVE']:
            self.assertIn(blocker, report['confirmed_blockers'])

    def test_refuses_claiming_read_only_when_database_disagrees(self):
        with self.assertRaises(RuntimeError):
            module.collect(Database(readonly='off'), NOW)

    def test_connection_errors_are_sanitized_and_cannot_claim_activation(self):
        def failure(**options):
            raise RuntimeError('fixture-password@private-host')
        report = module.check(connect=failure, config=CONFIG, moment=NOW)
        self.assertFalse(report['ok'])
        self.assertFalse(report['activation_ready'])
        self.assertEqual(report['error_category'], 'RuntimeError')
        self.assertNotIn('fixture-password', str(report))
        self.assertNotIn('private-host', str(report))

    def test_injected_connection_receives_bound_tls_options(self):
        seen = {}
        db = Database()
        def connect(**options):
            seen.update(options)
            return db
        self.assertTrue(module.check(connect=connect, config=CONFIG, moment=NOW)['ok'])
        self.assertEqual(seen['sslmode'], 'require')
        self.assertEqual(seen['connect_timeout'], 15)


if __name__ == '__main__':
    unittest.main()

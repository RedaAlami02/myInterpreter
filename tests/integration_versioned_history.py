"""Explicit local PostgreSQL integration test; never use a cloud test database.

Run with HISTORY_TEST_SOCKET=/tmp/... pointing at a disposable Unix-only server.
The test connection replaces the production TLS connector solely for local tests.
"""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_import_versioned_history import HistoryImportTests, history
from read_versioned_history import historical_closes


class LocalDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        socket = Path(os.environ["HISTORY_TEST_SOCKET"]).resolve()
        if not socket.is_relative_to("/tmp") or not socket.name.startswith(
            "casablanca-history-"
        ):
            raise ValueError("An isolated test socket is required")
        cls.options = dict(
            host=str(socket), port=55439, user="test_owner", dbname="history_test"
        )
        with psycopg.connect(**cls.options, autocommit=True) as db:
            for role in ("anon", "authenticated", "service_role"):
                if not db.execute(
                    "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
                ).fetchone():
                    db.execute(
                        psycopg.sql.SQL("CREATE ROLE {}").format(
                            psycopg.sql.Identifier(role)
                        )
                    )
            db.execute(
                "CREATE TABLE IF NOT EXISTS public.original_data (id integer PRIMARY KEY, value text)"
            )
            db.execute(
                "INSERT INTO public.original_data VALUES (1,'unchanged') ON CONFLICT DO NOTHING"
            )

    def setUp(self):
        self.fixture = HistoryImportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.bundle = self.fixture.prepare()
        with psycopg.connect(**self.options, autocommit=True) as db:
            db.execute("DROP SCHEMA IF EXISTS market_history_v1 CASCADE")
        self.connector = patch.object(
            history, "connect", lambda _: psycopg.connect(**self.options)
        )
        self.connector.start()
        self.addCleanup(self.connector.stop)

    def schema_exists(self):
        with psycopg.connect(**self.options) as db:
            return db.execute(
                "SELECT to_regnamespace('market_history_v1') IS NOT NULL"
            ).fetchone()[0]

    def test_atomic_append_exact_readback_duplicates_privileges_and_idempotence(self):
        first = history.remote(self.bundle, {}, apply=True)
        self.assertEqual(first["status"], "APPENDED")
        self.assertTrue(first["public_table_contents_unchanged"])
        self.assertTrue(first["verification"]["all_values_and_raw_bytes_match"])
        second = history.remote(self.bundle, {}, apply=True)
        self.assertEqual(second["status"], "ALREADY_PRESENT_VERIFIED")
        readonly = history.remote(self.bundle, {})
        self.assertTrue(readonly["read_only"])
        self.assertEqual(readonly["verification"]["rows_verified"], 2)
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute(
                    "SELECT count(*),count(DISTINCT period_day) FROM market_history_v1.observations"
                ).fetchone(),
                (2, 1),
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM market_history_v1.observations WHERE observed_at IS NULL"
                ).fetchone()[0],
                2,
            )

    def test_interruption_after_copy_rolls_back_schema_and_all_inserted_rows(self):
        with patch.object(
            history, "verify_remote", side_effect=RuntimeError("simulated interruption")
        ):
            with self.assertRaises(RuntimeError):
                history.remote(self.bundle, {}, apply=True)
        self.assertFalse(self.schema_exists())
        self.assertEqual(
            history.remote(self.bundle, {}, apply=True)["status"], "APPENDED"
        )

    def test_retry_after_partial_or_changed_remote_data_refuses_to_repair(self):
        history.remote(self.bundle, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            db.execute(
                "DELETE FROM market_history_v1.observations WHERE source_ordinal=1"
            )
        with self.assertRaises(ValueError):
            history.remote(self.bundle, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM market_history_v1.observations"
                ).fetchone()[0],
                1,
            )

    def test_capacity_failure_creates_nothing(self):
        with self.assertRaises(ValueError):
            history.remote(self.bundle, {}, apply=True, max_bytes=1)
        self.assertFalse(self.schema_exists())

    def test_post_copy_size_failure_rolls_back(self):
        with psycopg.connect(**self.options) as db:
            before = db.execute(
                "SELECT pg_database_size(current_database())"
            ).fetchone()[0]
        with patch.object(
            history, "summary", return_value={"estimated_added_database_bytes": 0}
        ):
            with self.assertRaises(ValueError):
                history.remote(self.bundle, {}, apply=True, max_bytes=before + 1)
        self.assertFalse(self.schema_exists())

    def test_public_table_change_inside_transaction_triggers_rollback(self):
        original_verify = history.verify_remote

        def changed(db, bundle):
            db.execute("UPDATE public.original_data SET value='changed' WHERE id=1")
            return original_verify(db, bundle)

        with patch.object(history, "verify_remote", side_effect=changed):
            with self.assertRaises(ValueError):
                history.remote(self.bundle, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute("SELECT value FROM public.original_data").fetchone()[0],
                "unchanged",
            )
        self.assertFalse(self.schema_exists())

    def test_readonly_preflight_does_not_create_schema(self):
        report = history.remote(self.bundle, {})
        self.assertTrue(report["read_only"])
        self.assertFalse(report["schema_exists"])
        self.assertFalse(self.schema_exists())

    def test_accidental_application_access_blocks_import(self):
        with psycopg.connect(**self.options) as db:
            db.execute(history.SCHEMA.read_text(), prepare=False)
            db.execute("GRANT USAGE ON SCHEMA market_history_v1 TO anon")
        with self.assertRaises(ValueError):
            history.remote(self.bundle, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM market_history_v1.batches").fetchone()[
                    0
                ],
                0,
            )

    def test_reader_rejects_conflicts_missing_masi_stale_fallback_and_namespace_mix(
        self,
    ):
        history.remote(self.bundle, {}, apply=True)
        batch = self.bundle["batch_id"]
        namespace = self.bundle["manifest"]["namespace"]
        with psycopg.connect(**self.options) as db:
            result = historical_closes(db, batch, namespace, "2026-10-22", ["FIX"])
            self.assertEqual(result["duplicate_symbols"], ["FIX"])
            self.assertEqual(result["prices"], [])
            result = historical_closes(
                db, batch, namespace, "2026-10-23", ["FIX", "MASI"]
            )
            self.assertEqual(result["missing_symbols"], ["FIX", "MASI"])
            self.assertEqual(result["prices"], [])
            with self.assertRaises(ValueError):
                historical_closes(db, batch, "wrong.namespace", "2026-10-22", ["FIX"])

    def test_reader_retains_capture_time_and_never_claims_live_observation(self):
        history.remote(self.bundle, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            # Test fixture alteration only; immutable cloud evidence is never modified.
            db.execute(
                "DELETE FROM market_history_v1.observations WHERE source_ordinal=1"
            )
            result = historical_closes(
                db,
                self.bundle["batch_id"],
                self.bundle["manifest"]["namespace"],
                "2026-10-22",
                ["FIX"],
            )
            self.assertEqual(result["readiness"], "HISTORICAL_CLOSES_AVAILABLE")
            self.assertFalse(result["production_eligible"])
            self.assertIsNone(result["prices"][0]["observed_at"])
            self.assertEqual(
                result["prices"][0]["capture_completed_at"], self.fixture.completed
            )
            self.assertEqual(result["prices"][0]["close_decimal"], "123.45000000001")


if __name__ == "__main__":
    # Avoid rediscovering imported fixture test methods in this integration run.
    unittest.main(defaultTest="LocalDatabaseTests")

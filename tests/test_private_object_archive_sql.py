"""Rollback-only integration tests; explicitly supplied /tmp Unix socket required."""

import os
from pathlib import Path
import unittest

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = "feed_0123456789abcdef"


@unittest.skipUnless(
    os.environ.get("APP_TEST_DATABASE"), "Isolated database not configured"
)
class ObjectArchiveSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = conninfo_to_dict(os.environ["APP_TEST_DATABASE"])
        if not options.get("host", "").startswith("/tmp/"):
            raise RuntimeError("Only an isolated local Unix socket is permitted")
        cls.db = psycopg.connect(**options)
        for schema in ["storage", "app_archive", "archive_test_originals"]:
            if (
                cls.db.execute("SELECT to_regnamespace(%s)", (schema,)).fetchone()[0]
                is not None
            ):
                cls.db.rollback()
                cls.db.close()
                raise RuntimeError(
                    "Test database contains existing schemas; refusing overwrite"
                )
        for role in ["anon", "authenticated", "service_role"]:
            if not cls.db.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
            ).fetchone():
                cls.db.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
        cls.db.execute("CREATE SCHEMA storage")
        cls.db.execute(
            "CREATE TABLE storage.buckets(id text PRIMARY KEY,public boolean NOT NULL)"
        )
        cls.db.execute(
            "CREATE TABLE storage.objects(bucket_id text,name text,metadata jsonb,PRIMARY KEY(bucket_id,name))"
        )
        cls.db.execute("CREATE SCHEMA archive_test_originals")
        cls.db.execute("CREATE TABLE archive_test_originals.sentinel(value text)")
        cls.db.execute(
            "INSERT INTO archive_test_originals.sentinel VALUES('irreplaceable')"
        )
        cls.db.execute(
            (ROOT / "migrations/supabase/009_private_object_archive.sql").read_text()
        )
        cls.db.execute(
            "INSERT INTO app_archive.providers VALUES(%s,false)", (PROVIDER,)
        )
        cls.db.execute(
            "INSERT INTO storage.buckets VALUES('private-market-evidence',false)"
        )

    @classmethod
    def tearDownClass(cls):
        cls.db.rollback()
        cls.db.close()

    def setUp(self):
        self.db.execute("SAVEPOINT isolated_case")
        self.db.execute("UPDATE app_archive.control SET enabled=true")
        self.db.execute("UPDATE app_archive.providers SET enabled=true")
        self.stamp = self.db.execute("SELECT clock_timestamp()").fetchone()[0]
        self.slot = self.stamp.replace(minute=0, second=0, microsecond=0)

    def tearDown(self):
        self.db.execute("RESET ROLE")
        self.db.execute("ROLLBACK TO SAVEPOINT isolated_case")
        self.db.execute("RELEASE SAVEPOINT isolated_case")

    def reserve(self, digest="a" * 64, size=41, status="COMPLETE", **overrides):
        args = {
            "digest": digest,
            "provider": PROVIDER,
            "kind": "quotes",
            "slot": self.slot,
            "completed": self.stamp,
            "completeness": status,
            "bytes": size,
            **overrides,
        }
        return self.db.execute(
            "SELECT public.reserve_market_archive(%s,%s,%s,%s,%s,%s,%s)",
            tuple(args.values()),
        ).fetchone()[0]

    def stored(self, digest="a" * 64, size=41):
        self.db.execute(
            "INSERT INTO storage.objects VALUES('private-market-evidence',%s,jsonb_build_object('size',%s::bigint))",
            ("sha256/" + digest[:2] + "/" + digest + ".json.gz", size),
        )

    def finalize(self, digest="a" * 64):
        return self.db.execute(
            "SELECT public.finalize_market_archive(%s)", (digest,)
        ).fetchone()[0]

    def test_disabled_provider_and_global_switch_reject(self):
        for statement in [
            "UPDATE app_archive.control SET enabled=false",
            "UPDATE app_archive.providers SET enabled=false",
        ]:
            with self.db.transaction(force_rollback=True):
                self.db.execute(statement)
                with (
                    self.assertRaises(psycopg.errors.InsufficientPrivilege),
                    self.db.transaction(),
                ):
                    self.reserve()

    def test_bucket_must_exist_and_be_private(self):
        self.db.execute("UPDATE storage.buckets SET public=true")
        with (
            self.assertRaises(psycopg.errors.InsufficientPrivilege),
            self.db.transaction(),
        ):
            self.reserve()

    def test_untrusted_roles_cannot_call_rpcs_or_read_internal_tables(self):
        for role in ["anon", "authenticated"]:
            self.db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            for statement in [
                "SELECT public.market_archive_slot_complete('feed_0123456789abcdef','quotes',now())",
                "SELECT public.finalize_market_archive('a')",
                "SELECT * FROM app_archive.objects",
            ]:
                with (
                    self.assertRaises(psycopg.errors.InsufficientPrivilege),
                    self.db.transaction(),
                ):
                    self.db.execute(statement)
            self.db.execute("RESET ROLE")

    def test_service_role_can_reserve_but_cannot_read_or_change_internal_tables(self):
        self.db.execute("SET LOCAL ROLE service_role")
        self.assertEqual(self.reserve()["state"], "RESERVED")
        for statement in [
            "SELECT * FROM app_archive.objects",
            "DELETE FROM app_archive.objects",
            "SELECT * FROM archive_test_originals.sentinel",
        ]:
            with (
                self.assertRaises(psycopg.errors.InsufficientPrivilege),
                self.db.transaction(),
            ):
                self.db.execute(statement)

    def test_capacity_counts_other_buckets_and_outstanding_reservations(self):
        self.db.execute("UPDATE app_archive.control SET max_storage_bytes=100")
        self.db.execute(
            "INSERT INTO storage.objects VALUES('other','retained', '{\"size\":40}')"
        )
        self.reserve(size=41)
        with (
            self.assertRaises(psycopg.errors.ProgramLimitExceeded),
            self.db.transaction(),
        ):
            self.reserve(digest="b" * 64, size=20)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_archive.objects").fetchone()[0], 1
        )

    def test_uploaded_reservation_not_double_counted_and_exact_budget_allowed(self):
        self.db.execute("UPDATE app_archive.control SET max_storage_bytes=100")
        self.reserve(size=41)
        self.stored(size=41)
        self.reserve(digest="b" * 64, size=59)
        with (
            self.assertRaises(psycopg.errors.ProgramLimitExceeded),
            self.db.transaction(),
        ):
            self.reserve(digest="c" * 64, size=1)

    def test_unknown_or_invalid_storage_sizes_fail_closed(self):
        for metadata in ["{}", '{"size":-1}', '{"size":"unknown"}']:
            with self.db.transaction(force_rollback=True):
                self.db.execute(
                    "INSERT INTO storage.objects VALUES('other','unknown',%s::jsonb)",
                    (metadata,),
                )
                with (
                    self.assertRaises(psycopg.errors.ProgramLimitExceeded),
                    self.db.transaction(),
                ):
                    self.reserve()

    def test_database_capacity_guard_rejects_without_deletion(self):
        self.db.execute("UPDATE app_archive.control SET max_database_bytes=1")
        with (
            self.assertRaises(psycopg.errors.ProgramLimitExceeded),
            self.db.transaction(),
        ):
            self.reserve()
        self.assertEqual(
            self.db.execute("SELECT * FROM archive_test_originals.sentinel").fetchone()[
                0
            ],
            "irreplaceable",
        )

    def test_exact_retry_keeps_original_metadata_conflict_rejected(self):
        first = self.reserve()
        self.assertEqual(first, self.reserve())
        with (
            self.assertRaises(psycopg.errors.InvalidParameterValue),
            self.db.transaction(),
        ):
            self.reserve(size=42)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_archive.objects").fetchone()[0], 1
        )

    def test_finalize_requires_present_object_with_exact_size(self):
        self.reserve()
        with (
            self.assertRaises(psycopg.errors.InvalidParameterValue),
            self.db.transaction(),
        ):
            self.finalize()
        self.stored(size=42)
        with (
            self.assertRaises(psycopg.errors.InvalidParameterValue),
            self.db.transaction(),
        ):
            self.finalize()
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_archive.slots").fetchone()[0], 0
        )

    def test_finalize_retry_and_unique_slot_commit_keep_all_attempts(self):
        for digest in ["a" * 64, "b" * 64]:
            self.reserve(digest=digest)
            self.stored(digest=digest)
            self.assertEqual(self.finalize(digest), digest)
        self.finalize("a" * 64)
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM app_archive.objects WHERE state='STORED'"
            ).fetchone()[0],
            2,
        )
        self.assertEqual(
            self.db.execute("SELECT digest FROM app_archive.slots").fetchall(),
            [("a" * 64,)],
        )
        self.assertTrue(
            self.db.execute(
                "SELECT public.market_archive_slot_complete(%s,'quotes',%s)",
                (PROVIDER, self.slot),
            ).fetchone()[0]
        )

    def test_incomplete_evidence_preserved_without_marking_slot_complete(self):
        self.reserve(status="INCOMPLETE")
        self.stored()
        self.finalize()
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM app_archive.objects WHERE state='STORED'"
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_archive.slots").fetchone()[0], 0
        )

    def test_stale_future_infinite_and_oversized_new_reservations_rejected(self):
        from datetime import timedelta

        for updates in [
            {"completed": self.stamp - timedelta(days=1)},
            {"completed": self.stamp + timedelta(hours=1)},
            {"completed": "infinity"},
            {"slot": "-infinity"},
            {"bytes": 8388609},
        ]:
            with (
                self.assertRaises(psycopg.errors.InvalidParameterValue),
                self.db.transaction(),
            ):
                self.reserve(**updates)

    def test_interrupted_database_transaction_leaves_no_reservation(self):
        try:
            with self.db.transaction():
                self.reserve()
                raise RuntimeError("simulated crash")
        except RuntimeError:
            pass
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_archive.objects").fetchone()[0], 0
        )

    def test_abandoned_reservations_keep_budget_no_silent_cleanup(self):
        self.db.execute("UPDATE app_archive.control SET max_storage_bytes=50")
        self.reserve(size=41)
        self.db.execute(
            "UPDATE app_archive.objects SET reserved_at=now()-interval '30 days'"
        )
        with (
            self.assertRaises(psycopg.errors.ProgramLimitExceeded),
            self.db.transaction(),
        ):
            self.reserve(digest="b" * 64, size=10)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_archive.objects").fetchone()[0], 1
        )

    def test_missing_previously_committed_object_is_an_explicit_error(self):
        self.reserve()
        self.stored()
        self.finalize()
        self.db.execute("DELETE FROM storage.objects")
        with (
            self.assertRaises(psycopg.errors.InvalidParameterValue),
            self.db.transaction(),
        ):
            self.db.execute(
                "SELECT public.market_archive_slot_complete(%s,'quotes',%s)",
                (PROVIDER, self.slot),
            )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_archive.slots").fetchone()[0], 1
        )


if __name__ == "__main__":
    unittest.main()

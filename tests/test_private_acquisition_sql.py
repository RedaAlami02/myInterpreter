"""Run only on an explicitly supplied private Unix-socket test database.

APP_TEST_DATABASE='host=/tmp/... port=... dbname=... user=...' python3 ...
All DDL/fixtures/role changes are rolled back, including on failure.
"""

import gzip
import hashlib
import os
from pathlib import Path
import unittest

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("APP_TEST_DATABASE"), "Isolated database not configured")
class AcquisitionSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = conninfo_to_dict(os.environ["APP_TEST_DATABASE"])
        if not options.get("host", "").startswith("/tmp/"):
            raise RuntimeError("Only an isolated local Unix socket is permitted")
        cls.db = psycopg.connect(**options)
        cls.db.execute("BEGIN")
        for role in ["anon", "authenticated", "service_role"]:
            if not cls.db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                cls.db.execute(
                    psycopg.sql.SQL("CREATE ROLE {}").format(psycopg.sql.Identifier(role))
                )
        cls.db.execute("CREATE SCHEMA app_ingest_test_private")
        cls.db.execute("CREATE TABLE app_ingest_test_private.originals(value text)")
        cls.db.execute("INSERT INTO app_ingest_test_private.originals VALUES ('irreplaceable')")
        cls.db.execute((ROOT / "migrations/supabase/007_private_acquisition.sql").read_text())
        cls.db.execute("INSERT INTO app_ingest.providers VALUES ('feed_0123456789abcdef',true)")
        cls.db.execute("INSERT INTO app_ingest.providers VALUES ('feed_1111111111111111',false)")
        cls.raw = gzip.compress(b'{"fixture":"raw evidence"}', mtime=0)
        cls.digest = hashlib.sha256(cls.raw).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.db.rollback()
        cls.db.close()

    def tearDown(self):
        self.db.execute("RESET ROLE")

    def ingest(
        self,
        digest=None,
        provider="feed_0123456789abcdef",
        completed="clock_timestamp()",
        slot="date_trunc('hour',clock_timestamp())",
        completeness="COMPLETE",
    ):
        query = psycopg.sql.SQL("SELECT app_ingest.save_attempt(%s,%s,%s,{}, {},%s,%s)").format(
            psycopg.sql.SQL(slot), psycopg.sql.SQL(completed)
        )
        return self.db.execute(
            query, (digest or self.digest, provider, "quotes", completeness, self.raw)
        ).fetchone()[0]

    def test_append_and_duplicate_logical_commit(self):
        self.db.execute("SET LOCAL ROLE app_collector")
        # Explicit constant timestamps make an identical retry byte-for-byte.
        stamp = self.db.execute("SELECT clock_timestamp()").fetchone()[0]
        slot = stamp.replace(minute=0, second=0, microsecond=0)
        params = (self.digest, "feed_0123456789abcdef", "quotes", slot, stamp, "COMPLETE", self.raw)
        for _ in range(2):
            self.db.execute("SELECT app_ingest.save_attempt(%s,%s,%s,%s,%s,%s,%s)", params)
        self.assertTrue(
            self.db.execute(
                "SELECT app_ingest.slot_complete(%s,%s,%s)",
                ("feed_0123456789abcdef", "quotes", slot),
            ).fetchone()[0]
        )
        self.db.execute("RESET ROLE")
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_ingest.attempts").fetchone()[0], 1
        )
        self.assertEqual(self.db.execute("SELECT count(*) FROM app_ingest.slots").fetchone()[0], 1)

    def test_role_cannot_read_private_or_raw_tables(self):
        self.db.execute("SET LOCAL ROLE app_collector")
        for table in [
            "app_ingest_test_private.originals",
            "app_ingest.attempts",
            "app_ingest.providers",
        ]:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.db.transaction():
                    self.db.execute(
                        psycopg.sql.SQL("SELECT * FROM {}").format(
                            psycopg.sql.Identifier(*table.split("."))
                        )
                    )

    def test_role_cannot_insert_update_or_delete(self):
        self.db.execute("SET LOCAL ROLE app_collector")
        for statement in [
            "DELETE FROM app_ingest.attempts",
            "UPDATE app_ingest.providers SET enabled=true",
            "INSERT INTO app_ingest.providers VALUES ('feed_aaaaaaaaaaaaaaaa',true)",
        ]:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.db.transaction():
                    self.db.execute(statement)

    def test_disabled_and_unknown_provider(self):
        self.db.execute("SET LOCAL ROLE app_collector")
        for provider in ["feed_1111111111111111", "feed_2222222222222222"]:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.db.transaction():
                    self.ingest(provider=provider)

    def test_hash_time_and_stale_writes_rejected(self):
        self.db.execute("SET LOCAL ROLE app_collector")
        for values in [
            {"digest": "0" * 64},
            {"completed": "clock_timestamp()+interval '1 hour'"},
            {"completed": "clock_timestamp()-interval '1 day'"},
            {"slot": "clock_timestamp()-interval '2 days'"},
        ]:
            with self.assertRaises(psycopg.errors.InvalidParameterValue):
                with self.db.transaction():
                    self.ingest(**values)

    def test_anonymous_and_authenticated_have_no_ingestion_access(self):
        for role in ["anon", "authenticated", "service_role"]:
            self.db.execute(
                psycopg.sql.SQL("SET LOCAL ROLE {}").format(psycopg.sql.Identifier(role))
            )
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.db.transaction():
                    self.db.execute(
                        "SELECT app_ingest.slot_complete('feed_0123456789abcdef','quotes',now())"
                    )
            self.db.execute("RESET ROLE")

    def test_interrupted_commit_rolls_back(self):
        before = self.db.execute("SELECT count(*) FROM app_ingest.attempts").fetchone()[0]
        try:
            with self.db.transaction():
                raw = gzip.compress(b"interrupted", mtime=0)
                self.db.execute(
                    "SELECT app_ingest.save_attempt(%s,%s,%s,date_trunc('hour',now()),clock_timestamp(),%s,%s)",
                    (
                        hashlib.sha256(raw).hexdigest(),
                        "feed_0123456789abcdef",
                        "depth",
                        "COMPLETE",
                        raw,
                    ),
                )
                raise RuntimeError("simulated crash")
        except RuntimeError:
            pass
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_ingest.attempts").fetchone()[0], before
        )
        self.assertEqual(
            self.db.execute("SELECT value FROM app_ingest_test_private.originals").fetchone()[0],
            "irreplaceable",
        )


if __name__ == "__main__":
    unittest.main()

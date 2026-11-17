"""Concurrent transactions in a disposable local database; never a live service."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import threading
import unittest
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = "feed_0123456789abcdef"


@unittest.skipUnless(
    os.environ.get("APP_TEST_DATABASE"), "Isolated database not configured"
)
class ObjectArchiveConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = conninfo_to_dict(os.environ["APP_TEST_DATABASE"])
        if not cls.options.get("host", "").startswith("/tmp/"):
            raise RuntimeError("Only an isolated local Unix socket is permitted")
        cls.admin = psycopg.connect(**cls.options, autocommit=True)
        cls.created_roles = []
        for role in ["anon", "authenticated", "service_role"]:
            if not cls.admin.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
            ).fetchone():
                cls.admin.execute(
                    sql.SQL("CREATE ROLE {}").format(sql.Identifier(role))
                )
                cls.created_roles.append(role)
        cls.database = "archive_concurrency_" + uuid.uuid4().hex
        cls.admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.database))
        )
        cls.options = {**cls.options, "dbname": cls.database}
        cls.db = psycopg.connect(**cls.options, autocommit=True)
        cls.db.execute("CREATE SCHEMA storage")
        cls.db.execute(
            "CREATE TABLE storage.buckets(id text PRIMARY KEY,public boolean)"
        )
        cls.db.execute(
            "CREATE TABLE storage.objects(bucket_id text,name text,metadata jsonb,PRIMARY KEY(bucket_id,name))"
        )
        cls.db.execute(
            "INSERT INTO storage.buckets VALUES('private-market-evidence',false)"
        )
        cls.db.execute(
            (ROOT / "migrations/supabase/009_private_object_archive.sql").read_text()
        )
        cls.db.execute("UPDATE app_archive.control SET enabled=true")
        cls.db.execute("INSERT INTO app_archive.providers VALUES(%s,true)", (PROVIDER,))

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.admin.execute(
            sql.SQL("DROP DATABASE {}").format(sql.Identifier(cls.database))
        )
        for role in cls.created_roles:
            cls.admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        cls.admin.close()

    def setUp(self):
        self.db.execute(
            "TRUNCATE app_archive.slots,app_archive.objects,storage.objects"
        )
        self.db.execute("UPDATE app_archive.control SET max_storage_bytes=100")
        self.stamp = self.db.execute("SELECT clock_timestamp()").fetchone()[0]
        self.slot = self.stamp.replace(minute=0, second=0, microsecond=0)

    def params(self, digest, size=60):
        return (digest, PROVIDER, "quotes", self.slot, self.stamp, "COMPLETE", size)

    def test_concurrent_reservations_cannot_oversubscribe_capacity(self):
        barrier = threading.Barrier(2)

        def reserve(digest):
            try:
                with psycopg.connect(**self.options) as db:
                    db.execute("SET LOCAL ROLE service_role")
                    barrier.wait(timeout=10)
                    db.execute(
                        "SELECT public.reserve_market_archive(%s,%s,%s,%s,%s,%s,%s)",
                        self.params(digest),
                    )
                return "COMMITTED"
            except psycopg.Error as error:
                return error.sqlstate

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(reserve, ["a" * 64, "b" * 64]))
        self.assertEqual(sorted(results), ["54000", "COMMITTED"])
        self.assertEqual(
            self.db.execute(
                "SELECT count(*),sum(compressed_bytes) FROM app_archive.objects"
            ).fetchone(),
            (1, 60),
        )

    def test_concurrent_finalization_retains_two_attempts_and_one_logical_commit(self):
        for digest in ["a" * 64, "b" * 64]:
            self.db.execute(
                "SELECT public.reserve_market_archive(%s,%s,%s,%s,%s,%s,%s)",
                self.params(digest, 41),
            )
            self.db.execute(
                "INSERT INTO storage.objects VALUES('private-market-evidence',%s,'{\"size\":41}')",
                ("sha256/" + digest[:2] + "/" + digest + ".json.gz",),
            )
        barrier = threading.Barrier(2)

        def finalize(digest):
            with psycopg.connect(**self.options) as db:
                db.execute("SET LOCAL ROLE service_role")
                barrier.wait(timeout=10)
                db.execute("SELECT public.finalize_market_archive(%s)", (digest,))
            return "COMMITTED"

        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(
                list(pool.map(finalize, ["a" * 64, "b" * 64])),
                ["COMMITTED", "COMMITTED"],
            )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM app_archive.objects WHERE state='STORED'"
            ).fetchone()[0],
            2,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_archive.slots").fetchone()[0], 1
        )


if __name__ == "__main__":
    unittest.main()

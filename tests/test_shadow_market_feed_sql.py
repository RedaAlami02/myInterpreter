"""Rollback-only preview feed integration; requires an explicit /tmp test socket."""

import copy
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation/managed"))
sys.path.insert(0, str(ROOT / "automation/managed/tests"))
import app_feed
import market_collect
import worker
from test_app_feed import config, mapping
from test_market_frame import body


@unittest.skipUnless(
    os.environ.get("APP_TEST_DATABASE"), "Isolated database not configured"
)
class ShadowFeedSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = conninfo_to_dict(os.environ["APP_TEST_DATABASE"])
        if not options.get("host", "").startswith("/tmp/"):
            raise RuntimeError("Only an isolated local Unix socket is permitted")
        cls.db = psycopg.connect(**options)
        for schema in ["storage", "auth", "app_archive", "app_feed"]:
            if (
                cls.db.execute("SELECT to_regnamespace(%s)", (schema,)).fetchone()[0]
                is not None
            ):
                cls.db.rollback()
                cls.db.close()
                raise RuntimeError("Test database contains existing schemas")
        for role in ["anon", "authenticated", "service_role"]:
            if not cls.db.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
            ).fetchone():
                cls.db.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
        cls.db.execute(
            "CREATE SCHEMA storage; CREATE TABLE storage.buckets(id text PRIMARY KEY,public boolean); CREATE TABLE storage.objects(bucket_id text,name text,metadata jsonb)"
        )
        cls.db.execute(
            "CREATE SCHEMA auth; CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$"
        )
        cls.db.execute(
            "CREATE TABLE public.company(id text PRIMARY KEY,name text); CREATE TABLE public.format(name text,symbol text)"
        )
        cls.db.execute(
            "INSERT INTO public.company VALUES('a','Company A'),('b','Company B'); INSERT INTO public.format VALUES('Company A','A'),('Company B','B')"
        )
        cls.db.execute(
            (ROOT / "migrations/supabase/009_private_object_archive.sql").read_text()
        )
        cls.db.execute(
            (ROOT / "migrations/supabase/010_shadow_market_feed.sql").read_text()
        )
        cls.db.execute(
            "UPDATE app_archive.control SET enabled=true; INSERT INTO app_archive.providers VALUES('feed_0123456789abcdef',true); INSERT INTO storage.buckets VALUES('private-market-evidence',false)"
        )

    @classmethod
    def tearDownClass(cls):
        cls.db.rollback()
        cls.db.close()

    def setUp(self):
        self.db.execute("SAVEPOINT feed_case")
        self.now = self.db.execute("SELECT clock_timestamp()").fetchone()[
            0
        ] - timedelta(seconds=3)
        self.cfg = config()
        self.identities = mapping()
        self.cfg["recipe"]["expected_index_identities"] = ["MASI"]
        self.cfg["recipe"]["views"]["indices"]["constants"]["source_identity"] = "MASI"
        self.identities["indices"] = [
            {
                "source_identity": "MASI",
                "company_id": None,
                "asset_key": "index:MASI",
                "c_name": "MASI",
                "symbol": "MASI",
            }
        ]
        self.db.execute(
            "UPDATE app_feed.control SET provider_namespace=%s,mapping_sha256=%s,recipe_sha256=%s",
            (
                self.cfg["provider_namespace"],
                app_feed.fingerprint(self.identities),
                app_feed.fingerprint(self.cfg["recipe"]),
            ),
        )

    def tearDown(self):
        self.db.execute(
            "RESET ROLE; ROLLBACK TO SAVEPOINT feed_case; RELEASE SAVEPOINT feed_case"
        )

    def prepared(self, stamp=None, partial=False):
        stamp = stamp or self.now
        data = body()
        for row in data["quotes"] + data["indices"]:
            row["time"] = stamp.astimezone(worker.ZONE).strftime("%d/%m/%Y %H:%M:%S")
        if partial:
            data["quotes"].pop()
        slot = stamp.replace(minute=stamp.minute // 15 * 15, second=0, microsecond=0)
        envelope = market_collect.envelope(
            self.cfg,
            json.dumps(data).encode(),
            stamp,
            slot.isoformat(),
            execution="CURRENT_ACQUISITION",
        )
        envelope["completed_at"] = stamp.isoformat()
        digest, blob = worker.packed(envelope)
        self.db.execute(
            "SELECT public.reserve_market_archive(%s,%s,'quotes',%s,%s,%s,%s)",
            (
                digest,
                self.cfg["provider_namespace"],
                slot,
                stamp,
                envelope["completeness"],
                len(blob),
            ),
        )
        self.db.execute(
            "INSERT INTO storage.objects VALUES('private-market-evidence',%s,jsonb_build_object('size',%s::integer))",
            ("sha256/" + digest[:2] + "/" + digest + ".json.gz", len(blob)),
        )
        self.db.execute("SELECT public.finalize_market_archive(%s)", (digest,))
        return app_feed.build(blob, digest, self.cfg, self.identities, as_of=stamp)

    def publish(self, value):
        text = app_feed.canonical(value)
        return self.db.execute(
            "SELECT public.publish_shadow_market_candidate(%s,%s)",
            (text, hashlib.sha256(text.encode()).hexdigest()),
        ).fetchone()[0]

    def read(self, enable=True):
        if enable:
            self.db.execute("UPDATE app_feed.control SET enabled=true")
        self.db.execute(
            "SELECT set_config('request.jwt.claim.sub','00000000-0000-4000-8000-000000000001',true)"
        )
        self.db.execute("SET LOCAL ROLE authenticated")
        result = self.db.execute("SELECT public.read_shadow_market_feed()").fetchone()[
            0
        ]
        self.db.execute("RESET ROLE")
        return result

    def test_disabled_and_waiting_are_explicit_without_legacy_fallback(self):
        self.assertEqual(self.read(enable=False)["status"], "DISABLED")
        self.assertEqual(self.read()["status"], "WAITING")

    def test_anonymous_read_and_normal_user_publish_denied(self):
        self.db.execute("SET LOCAL ROLE anon")
        with (
            self.assertRaises(psycopg.errors.InsufficientPrivilege),
            self.db.transaction(),
        ):
            self.db.execute("SELECT public.read_shadow_market_feed()")
        self.db.execute("RESET ROLE; SET LOCAL ROLE authenticated")
        with (
            self.assertRaises(psycopg.errors.InsufficientPrivilege),
            self.db.transaction(),
        ):
            self.db.execute("SELECT public.publish_shadow_market_candidate('{}','x')")
        with (
            self.assertRaises(psycopg.errors.InsufficientPrivilege),
            self.db.transaction(),
        ):
            self.db.execute("SELECT * FROM app_feed.latest")

    def test_authenticated_role_without_verified_subject_is_denied(self):
        self.db.execute(
            "SELECT set_config('request.jwt.claim.sub','',true); SET LOCAL ROLE authenticated"
        )
        with (
            self.assertRaises(psycopg.errors.InsufficientPrivilege),
            self.db.transaction(),
        ):
            self.db.execute("SELECT public.read_shadow_market_feed()")

    def test_exact_publish_and_redacted_read_leave_original_tables_unchanged(self):
        value = self.prepared()
        self.db.execute("SET LOCAL ROLE service_role")
        self.publish(value)
        self.db.execute("RESET ROLE")
        result = self.read()
        self.assertEqual(result["mode"], "SHADOW_ONLY")
        self.assertEqual(result["rows"][0]["price_decimal"], "10.50")
        self.assertIsNotNone(result["rows"][0]["expires_at"])
        text = json.dumps(result)
        for private in [
            "provider_namespace",
            "archive_sha256",
            "mapping_sha256",
            "recipe_sha256",
            "source_identity",
            "observations",
            "observed_price_decimal",
        ]:
            self.assertNotIn(private, text)
        self.assertEqual(
            self.db.execute("SELECT * FROM public.company ORDER BY id").fetchall(),
            [("a", "Company A"), ("b", "Company B")],
        )

    def test_failed_digest_or_wrong_pin_rejected(self):
        value = self.prepared()
        with (
            self.assertRaises(psycopg.errors.InvalidParameterValue),
            self.db.transaction(),
        ):
            self.db.execute(
                "SELECT public.publish_shadow_market_candidate(%s,%s)",
                (app_feed.canonical(value), "a" * 64),
            )
        value["recipe_sha256"] = "b" * 64
        with (
            self.assertRaises(psycopg.errors.InvalidParameterValue),
            self.db.transaction(),
        ):
            self.publish(value)

    def test_wrong_company_symbol_index_or_duplicate_universe_rejected(self):
        original = self.prepared()
        for mode in ["symbol", "company", "index", "duplicate"]:
            value = copy.deepcopy(original)
            if mode == "symbol":
                value["rows"][0]["symbol"] = "WRONG"
            if mode == "company":
                value["rows"][0]["company_id"] = "b"
            if mode == "index":
                value["rows"][2]["c_name"] = "Average stocks"
            if mode == "duplicate":
                value["rows"][1] = value["rows"][0]
            with (
                self.subTest(mode=mode),
                self.assertRaises(psycopg.errors.InvalidParameterValue),
                self.db.transaction(),
            ):
                self.publish(value)

    def test_replay_or_promoted_candidate_cannot_enter_shadow_service(self):
        original = self.prepared()
        for key, change in [
            ("source_execution", "RECORDED_REPLAY"),
            ("mode", "PRODUCTION"),
            ("prediction_eligible", True),
        ]:
            value = {**original, key: change}
            with (
                self.assertRaises(psycopg.errors.InvalidParameterValue),
                self.db.transaction(),
            ):
                self.publish(value)

    def test_verified_archive_required(self):
        value = self.prepared()
        value["archive_sha256"] = "b" * 64
        with (
            self.assertRaises(psycopg.errors.InsufficientPrivilege),
            self.db.transaction(),
        ):
            self.publish(value)

    def test_naive_receipt_time_is_rejected_without_timezone_inference(self):
        value = self.prepared()
        value["captured_at"] = self.now.replace(tzinfo=None).isoformat()
        with (
            self.assertRaises(psycopg.errors.InvalidParameterValue),
            self.db.transaction(),
        ):
            self.publish(value)

    def test_missing_stock_on_new_snapshot_removes_old_preview_price(self):
        self.publish(self.prepared())
        partial = self.prepared(self.now + timedelta(seconds=1), partial=True)
        self.publish(partial)
        row = self.read()["rows"][1]
        self.assertEqual(row["status"], "MISSING_QUOTE")
        self.assertIsNone(row["price_decimal"])
        self.assertIsNone(row["captured_at"])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_feed.latest").fetchone()[0], 1
        )

    def test_snapshot_expires_at_read_time(self):
        self.publish(self.prepared())
        self.db.execute(
            "UPDATE app_feed.latest SET body=jsonb_set(body,'{capture_max_age_seconds}','1')"
        )
        rows = self.read()["rows"]
        self.assertTrue(
            all(
                row["status"] == "STALE_CAPTURE" and row["price_decimal"] is None
                for row in rows
            )
        )

    def test_missing_archived_evidence_disables_preview_without_deleting_candidate(
        self,
    ):
        self.publish(self.prepared())
        self.db.execute("DELETE FROM storage.objects")
        value = self.read()
        self.assertEqual(value["status"], "EVIDENCE_UNAVAILABLE")
        self.assertEqual(value["rows"], [])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_feed.latest").fetchone()[0], 1
        )

    def test_idempotent_retry_equal_time_conflict_and_older_capture_rejected(self):
        value = self.prepared()
        receipt = self.publish(value)
        self.assertEqual(self.publish(value), receipt)
        conflict = {**value, "as_of": (self.now + timedelta(seconds=1)).isoformat()}
        with (
            self.assertRaises(psycopg.errors.InvalidParameterValue),
            self.db.transaction(),
        ):
            self.publish(conflict)
        older = self.prepared(self.now - timedelta(seconds=1))
        with (
            self.assertRaises(psycopg.errors.InvalidParameterValue),
            self.db.transaction(),
        ):
            self.publish(older)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM app_feed.latest").fetchone()[0], 1
        )


if __name__ == "__main__":
    unittest.main()

"""Explicit disposable Unix-socket PostgreSQL tests. Never target a cloud DB."""

import copy
import contextlib
import gzip
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_history_delta as fixtures
from test_history_delta import delta, v1, fixture_version
from export_history_preview import write_projection
import export_history_preview as preview
from read_versioned_history import historical_closes


class DeltaDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        socket = Path(os.environ["HISTORY_TEST_SOCKET"]).resolve()
        if not socket.is_relative_to("/tmp") or not socket.name.startswith(
            "casablanca-history-pg-"
        ):
            raise ValueError("Isolated test socket required")
        cls.options = dict(
            host=str(socket), port=55439, user="test_owner", dbname="history_delta_test"
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
                "CREATE TABLE IF NOT EXISTS public.original_data(id integer PRIMARY KEY,value text)"
            )
            db.execute(
                "INSERT INTO public.original_data VALUES(1,'untouched') ON CONFLICT DO NOTHING"
            )

    def setUp(self):
        self.fixture = fixtures.DeltaTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.parent, self.current = self.fixture.parent, self.fixture.current
        with psycopg.connect(**self.options, autocommit=True) as db:
            db.execute("DROP SCHEMA IF EXISTS market_history_v1 CASCADE")
        self.connector = patch.object(
            v1, "connect", lambda _: psycopg.connect(**self.options)
        )
        self.connector.start()
        self.addCleanup(self.connector.stop)
        v1.remote(self.parent, {}, apply=True)
        self.plan = delta.plan_delta(self.parent, self.current)

    def test_sparse_append_reconstructs_every_source_observation_and_is_idempotent(
        self,
    ):
        result = delta.remote(self.plan, self.parent, {}, apply=True)
        self.assertEqual(result["status"], "DELTA_APPENDED")
        self.assertEqual(result["verification"]["rows_verified"], 1)
        self.assertEqual(result["verification"]["full_source_observations_verified"], 3)
        self.assertTrue(result["existing_public_and_parent_contents_unchanged"])
        result = delta.remote(self.plan, self.parent, {}, apply=True)
        self.assertEqual(result["status"], "ALREADY_PRESENT_VERIFIED")
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM market_history_v1.observations"
                ).fetchone()[0],
                3,
            )
            full, _ = delta.load_archive(db, self.plan["batch_id"])
            self.assertEqual(v1.canonical(full), v1.canonical(self.current))

    def test_readonly_preflight_verifies_parent_without_inserting_new_rows(self):
        result = delta.remote(self.plan, self.parent, {})
        self.assertTrue(result["read_only"])
        self.assertEqual(result["status"], "READ_ONLY_PLAN_VERIFIED")
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM market_history_v1.batches").fetchone()[
                    0
                ],
                1,
            )

    def test_interruption_after_copy_rolls_back_all_new_evidence_and_retry_works(self):
        with patch.object(
            delta, "verify_delta", side_effect=RuntimeError("simulated interruption")
        ):
            with self.assertRaises(RuntimeError):
                delta.remote(self.plan, self.parent, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM market_history_v1.batches").fetchone()[
                    0
                ],
                1,
            )
            v1.verify_remote(db, self.parent)
        self.assertEqual(
            delta.remote(self.plan, self.parent, {}, apply=True)["status"],
            "DELTA_APPENDED",
        )

    def test_v2_parent_can_extend_again_without_changing_originals(self):
        delta.remote(self.plan, self.parent, {}, apply=True)
        bars = [copy.deepcopy(r[6]) for r in self.current["rows"]]
        bars.append(dict(bars[-1], day="2026-10-24 00:00:00", close=130, high=131))
        next_version = fixture_version(
            self.current, bars, completed="2026-10-28T08:00:00+00:00"
        )
        plan = delta.plan_delta(self.current, next_version, self.plan["batch_id"])
        result = delta.remote(plan, self.current, {}, apply=True)
        self.assertEqual(result["verification"]["rows_verified"], 1)
        self.assertEqual(result["verification"]["full_source_observations_verified"], 4)
        with psycopg.connect(**self.options) as db:
            v1.verify_remote(db, self.parent)
            delta.verify_delta(db, self.plan)

    def test_parent_typed_tampering_blocks_import_without_repair(self):
        with psycopg.connect(**self.options) as db:
            db.execute(
                "UPDATE market_history_v1.observations SET close_text='999' WHERE source_ordinal=0"
            )
        with self.assertRaises(ValueError):
            delta.remote(self.plan, self.parent, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM market_history_v1.batches").fetchone()[
                    0
                ],
                1,
            )
            self.assertEqual(
                db.execute(
                    "SELECT close_text FROM market_history_v1.observations WHERE source_ordinal=0"
                ).fetchone()[0],
                "999",
            )

    def test_missing_delta_row_or_changed_raw_capture_is_rejected(self):
        delta.remote(self.plan, self.parent, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            db.execute(
                "DELETE FROM market_history_v1.observations WHERE batch_id=%s",
                (self.plan["batch_id"],),
            )
        with self.assertRaises(ValueError):
            delta.remote(self.plan, self.parent, {})

    def test_capacity_guard_blocks_before_write(self):
        with self.assertRaises(ValueError):
            delta.remote(self.plan, self.parent, {}, apply=True, max_bytes=1)
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM market_history_v1.batches").fetchone()[
                    0
                ],
                1,
            )

    def test_post_copy_size_failure_rolls_back(self):
        bars = copy.deepcopy(self.fixture.bars)
        bars[0]["synthetic_extra"] = os.urandom(50000).hex()
        plan = delta.plan_delta(self.parent, fixture_version(self.parent, bars))
        with psycopg.connect(**self.options) as db:
            before = db.execute(
                "SELECT pg_database_size(current_database())"
            ).fetchone()[0]
        with patch.object(
            delta, "summary", return_value={"estimated_added_database_bytes": 0}
        ):
            with self.assertRaises(ValueError):
                delta.remote(plan, self.parent, {}, apply=True, max_bytes=before + 1)
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM market_history_v1.batches").fetchone()[
                    0
                ],
                1,
            )

    def test_unchanged_capture_or_rolling_expiry_never_deletes_or_duplicates_sql(self):
        current = fixture_version(self.parent, [self.fixture.bars[0]])
        plan = delta.plan_delta(self.parent, current)
        result = delta.remote(plan, self.parent, {}, apply=True)
        self.assertEqual(result["status"], "NO_ECONOMIC_PAYLOAD_CHANGES")
        with psycopg.connect(**self.options) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM market_history_v1.batches").fetchone()[
                    0
                ],
                1,
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM market_history_v1.observations"
                ).fetchone()[0],
                2,
            )

    def test_sparse_contract_is_not_silently_consumed_as_v1_full_rows(self):
        delta.remote(self.plan, self.parent, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            with self.assertRaises(ValueError):
                historical_closes(
                    db,
                    self.plan["batch_id"],
                    self.current["manifest"]["namespace"],
                    "2026-10-23",
                    ["FIX"],
                )

    def test_full_preview_export_can_include_inherited_rows_without_price_substitution(
        self,
    ):
        delta.remote(self.plan, self.parent, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            full, _ = delta.load_archive(db, self.plan["batch_id"])
        with tempfile.TemporaryDirectory() as folder:
            result = write_projection(full, Path(folder) / "export")
            self.assertEqual(result["observations"], 3)
            self.assertEqual(result["conflicting_days"], 1)
            self.assertTrue(result["not_live"])

    def test_export_cli_verifies_sparse_archive_before_writing_any_preview(self):
        delta.remote(self.plan, self.parent, {}, apply=True)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            raw = gzip.compress(v1.canonical(self.current), mtime=0)
            bundle = folder / "bundle.json.gz"
            bundle.write_bytes(raw)
            argv = [
                "export_history_preview.py",
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                v1.digest(raw),
                "--output",
                str(folder / "export"),
                "--receipt",
                str(folder / "receipt.json"),
                "--verify-remote",
                "--archive-id",
                self.plan["batch_id"],
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(preview, "local_config", return_value={}),
                patch.object(
                    preview, "connect", lambda _: psycopg.connect(**self.options)
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(preview.main(), 0)
            self.assertTrue((folder / "export/manifest.json").is_file())

    def test_export_cli_rejects_a_different_locally_valid_source_snapshot(self):
        delta.remote(self.plan, self.parent, {}, apply=True)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            raw = gzip.compress(v1.canonical(self.parent), mtime=0)
            bundle = folder / "bundle.json.gz"
            bundle.write_bytes(raw)
            argv = [
                "export_history_preview.py",
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                v1.digest(raw),
                "--output",
                str(folder / "export"),
                "--receipt",
                str(folder / "receipt.json"),
                "--verify-remote",
                "--archive-id",
                self.plan["batch_id"],
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(preview, "local_config", return_value={}),
                patch.object(
                    preview, "connect", lambda _: psycopg.connect(**self.options)
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(preview.main(), 1)
            self.assertFalse((folder / "export").exists())

    def test_corrupt_raw_bytes_are_not_silently_accepted(self):
        delta.remote(self.plan, self.parent, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            db.execute(
                "UPDATE market_history_v1.captures SET raw_gzip=%s WHERE batch_id=%s",
                (b"bad gzip", self.plan["batch_id"]),
            )
        with psycopg.connect(**self.options) as db:
            with self.assertRaises((ValueError, OSError)):
                delta.load_archive(db, self.plan["batch_id"])

    def test_missing_parent_manifest_blocks_reading_sparse_version(self):
        delta.remote(self.plan, self.parent, {}, apply=True)
        with psycopg.connect(**self.options) as db:
            for table in ("observations", "captures", "batches"):
                db.execute(
                    psycopg.sql.SQL(
                        "DELETE FROM market_history_v1.{} WHERE batch_id=%s"
                    ).format(psycopg.sql.Identifier(table)),
                    (self.parent["batch_id"],),
                )
        with psycopg.connect(**self.options) as db:
            with self.assertRaises(ValueError):
                delta.load_archive(db, self.plan["batch_id"])


if __name__ == "__main__":
    unittest.main(defaultTest="DeltaDatabaseTests")

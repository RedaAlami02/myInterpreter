import gzip
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import import_versioned_history as history


class HistoryImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.bindings = {
            "rows_path": ["rows"],
            "date_field": "day",
            "date_format": "%Y-%m-%d %H:%M:%S",
            "close_field": "close",
            "open_field": "open",
            "high_field": "high",
            "low_field": "low",
            "volume_mad_field": "volume",
        }
        self.originals = [
            dict(
                day="2026-10-22 00:00:00",
                close=123.45000000001,
                open=120,
                high=122,
                low=119,
                volume=100,
            ),
            dict(
                day="2026-10-22 00:00:00",
                close=124,
                open=120,
                high=125,
                low=119,
                volume=200,
            ),
        ]
        self.completed = "2026-10-26T08:00:00+00:00"
        self.raw = history.canonical({"rows": self.originals})
        self.request = b'{"request":"fixture"}'
        self.receipt = history.canonical(
            {
                "sha256": history.digest(self.raw),
                "request_sha256": history.digest(self.request),
                "completed_at": self.completed,
                "kind": "HTTP_CAPTURED_NOW",
            }
        )
        self.store = self.folder / "capture.sqlite"
        with sqlite3.connect(self.store) as db:
            db.execute("CREATE TABLE artifacts (sha TEXT PRIMARY KEY, body BLOB)")
            for value in (self.raw, self.request, self.receipt):
                db.execute(
                    "INSERT INTO artifacts VALUES (?,?)", (history.digest(value), value)
                )
        self.index = {
            "FIX": dict(
                raw_sha256=history.digest(self.raw),
                request_sha256=history.digest(self.request),
                receipt_sha256=history.digest(self.receipt),
                capture_completed_at=self.completed,
                source_rows=2,
            )
        }
        self.rows = []
        for ordinal, original in enumerate(self.originals):
            day, label, close, warnings = history.native_projection(
                original, self.bindings
            )
            self.rows.append(
                dict(
                    provider="fixture",
                    namespace="fixture.daily.v1",
                    record_identity=history.digest(
                        history.canonical(
                            [
                                "fixture.daily.v1",
                                "FIX",
                                history.digest(self.raw),
                                ordinal,
                            ]
                        )
                    ),
                    symbol="FIX",
                    source_ordinal=ordinal,
                    market_date=day,
                    source_daily_date=label,
                    close_decimal=close,
                    close=original["close"],
                    open=original["open"],
                    high=original["high"],
                    low=original["low"],
                    volume_mad=original["volume"],
                    quantity=None,
                    observed_at=None,
                    observation_time_status="UNKNOWN",
                    price_definition="PROVIDER_DAILY_CLOSE_CANDIDATE",
                    raw_row_json=history.canonical(original).decode(),
                    quality_warnings=json.dumps(warnings),
                    raw_sha256=history.digest(self.raw),
                    capture_completed_at=self.completed,
                )
            )
        self.parquet = self.folder / "history.parquet"
        self.report = dict(
            contract="provider-daily-history-recovery-v2",
            classification="RETROSPECTIVE_SOURCE_HISTORY",
            failed_instruments=[],
            source_rows=2,
            expected_instruments=1,
        )
        self.rewrite()

    def rewrite(self):
        pq.write_table(pa.Table.from_pylist(self.rows), self.parquet)
        self.report["parquet_sha256"] = history.digest(self.parquet.read_bytes())
        for name, value in [
            ("index", self.index),
            ("report", self.report),
            ("bindings", self.bindings),
        ]:
            (self.folder / (name + ".json")).write_bytes(history.canonical(value))

    def prepare(self):
        return history.prepare(
            self.folder / "report.json",
            self.folder / "index.json",
            self.parquet,
            self.store,
            self.folder / "bindings.json",
        )

    def test_every_conflicting_row_and_exact_price_is_preserved(self):
        bundle = self.prepare()
        self.assertEqual(len(bundle["rows"]), 2)
        self.assertNotEqual(bundle["rows"][0][2], bundle["rows"][1][2])
        self.assertEqual(bundle["rows"][0][5], "123.45000000001")
        report = history.summary(bundle)
        self.assertEqual(report["duplicate_economic_keys"], 1)
        self.assertEqual(report["conflicting_close_keys"], 1)
        self.assertEqual(bundle["rows"][0][7], ["SOURCE_OHLC_INCONSISTENT"])
        history.validate(bundle)

    def test_raw_request_receipt_bytes_survive_portable_bundle(self):
        bundle = history.read_json(
            gzip.decompress(gzip.compress(history.canonical(self.prepare())))
        )
        history.validate(bundle)
        import base64

        actual = [
            gzip.decompress(base64.b64decode(s)) for s in bundle["captures"][0][5:]
        ]
        self.assertEqual(actual, [self.raw, self.request, self.receipt])

    def test_missing_capture_or_changed_blob_is_rejected(self):
        for operation in (
            "DELETE FROM artifacts WHERE sha=?",
            "UPDATE artifacts SET body=x'00' WHERE sha=?",
        ):
            with self.subTest(operation=operation):
                with sqlite3.connect(self.store) as db:
                    db.execute(operation, (history.digest(self.raw),))
                with self.assertRaises(ValueError):
                    self.prepare()
                with sqlite3.connect(self.store) as db:
                    db.execute(
                        "INSERT OR REPLACE INTO artifacts VALUES (?,?)",
                        (history.digest(self.raw), self.raw),
                    )

    def test_no_invented_observation_time_or_source_identity(self):
        for field, value in [
            ("observed_at", self.completed),
            ("observation_time_status", "KNOWN"),
            ("record_identity", "0" * 64),
            ("namespace", "other.namespace"),
            ("capture_completed_at", "2026-10-25T00:00:00+00:00"),
            ("raw_sha256", "a" * 64),
            ("quantity", 0),
        ]:
            with self.subTest(field=field):
                saved = self.rows[0][field]
                self.rows[0][field] = value
                self.rewrite()
                with self.assertRaises(ValueError):
                    self.prepare()
                self.rows[0][field] = saved

    def test_projection_must_match_all_raw_fields_and_warnings(self):
        for field, value in [
            ("close_decimal", "123.45"),
            ("market_date", "2026-10-23"),
            ("source_daily_date", "2026-10-22"),
            ("quality_warnings", "[]"),
            ("open", 0),
            ("volume_mad", 0),
            ("raw_row_json", "{}"),
        ]:
            with self.subTest(field=field):
                saved = self.rows[0][field]
                self.rows[0][field] = value
                self.rewrite()
                with self.assertRaises(ValueError):
                    self.prepare()
                self.rows[0][field] = saved

    def test_missing_duplicate_ordinal_and_changed_parquet_are_rejected(self):
        for ordinal in (0, 5):
            self.rows[1]["source_ordinal"] = ordinal
            self.rewrite()
            with self.assertRaises(ValueError):
                self.prepare()
        self.rows[1]["source_ordinal"] = 1
        self.rewrite()
        self.parquet.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.prepare()

    def test_source_volume_placeholder_remains_missing_instead_of_zero(self):
        self.originals[0]["volume"] = "-"
        self.raw = history.canonical({"rows": self.originals})
        self.receipt = history.canonical(
            {
                "sha256": history.digest(self.raw),
                "request_sha256": history.digest(self.request),
                "completed_at": self.completed,
                "kind": "HTTP_CAPTURED_NOW",
            }
        )
        with sqlite3.connect(self.store) as db:
            for value in (self.raw, self.receipt):
                db.execute(
                    "INSERT INTO artifacts VALUES (?,?)", (history.digest(value), value)
                )
        self.index["FIX"].update(
            raw_sha256=history.digest(self.raw),
            receipt_sha256=history.digest(self.receipt),
        )
        self.bindings["nullable_source_values"] = {"volume_mad": ["-"]}
        for r in self.rows:
            r["raw_sha256"] = history.digest(self.raw)
            r["record_identity"] = history.digest(
                history.canonical(
                    [
                        r["namespace"],
                        "FIX",
                        history.digest(self.raw),
                        r["source_ordinal"],
                    ]
                )
            )
        self.rows[0]["volume_mad"] = None
        self.rows[0]["raw_row_json"] = history.canonical(self.originals[0]).decode()
        self.rewrite()
        self.assertEqual(self.prepare()["rows"][0][6]["volume"], "-")
        self.rows[0]["volume_mad"] = 0
        self.rewrite()
        with self.assertRaises(Exception):
            self.prepare()

    def test_portable_bundle_tampering_is_rejected(self):
        for component in ("rows", "captures", "manifest", "batch_id"):
            with self.subTest(component=component):
                bundle = self.prepare()
                if component == "rows":
                    bundle["rows"][0][5] = "1"
                elif component == "captures":
                    bundle["captures"][0][2] = "0" * 64
                elif component == "manifest":
                    bundle["manifest"]["row_count"] = 1
                else:
                    bundle["batch_id"] = "0" * 64
                with self.assertRaises(ValueError):
                    history.validate(bundle)

    def test_recomputed_digest_cannot_hide_wrong_raw_projection(self):
        bundle = self.prepare()
        bundle["rows"][0][5] = "1"
        bundle["manifest"]["rows_sha256"] = history.digest(
            history.canonical(bundle["rows"])
        )
        bundle["batch_id"] = history.digest(history.canonical(bundle["manifest"]))
        with self.assertRaises(ValueError):
            history.validate(bundle)

    def test_daily_label_and_completion_must_not_be_fabricated(self):
        for label in ("2026-10-22 12:00:00", "2026-10-22T00:00:00Z"):
            with self.assertRaises(ValueError):
                history.native_projection(
                    dict(self.originals[0], day=label), self.bindings
                )
        with self.assertRaises(ValueError):
            history.instant("2026-10-26T08:00:00")

    def test_invalid_or_nonpositive_close_cannot_become_market_data(self):
        for close in (0, -1, True, None, float("inf"), float("nan")):
            with self.subTest(close=close), self.assertRaises(ValueError):
                history.native_projection(
                    dict(self.originals[0], close=close), self.bindings
                )

    def test_schema_keeps_economic_duplicates_private_and_original_tables_untouched(
        self,
    ):
        text = history.SCHEMA.read_text()
        self.assertNotIn("public.", text)
        self.assertNotIn("ON CONFLICT", text)
        self.assertIn("PRIMARY KEY (batch_id, symbol, source_ordinal)", text)
        self.assertIn("CHECK (observed_at IS NULL)", text)
        self.assertEqual(text.count("ENABLE ROW LEVEL SECURITY"), 3)


if __name__ == "__main__":
    unittest.main()

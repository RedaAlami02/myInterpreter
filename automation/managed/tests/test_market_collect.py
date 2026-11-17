import contextlib
from datetime import timedelta
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_collect as collector
import market_frame
import worker
from test_market_frame import CAPTURED, body, recipe


def config():
    return {
        "contract": "private-market-config/v2",
        "provider_namespace": "feed_0123456789abcdef",
        "recipe": recipe(),
    }


def receipt(raw):
    return {"received_at": CAPTURED.isoformat(), "sha256": hashlib.sha256(raw).hexdigest()}


class MarketCollectorTests(unittest.TestCase):
    def test_replay_keeps_original_capture_and_never_becomes_forward_run(self):
        raw = json.dumps(body()).encode()
        value = collector.replay(config(), raw, receipt(raw))
        self.assertEqual(value["execution"], "RECORDED_REPLAY")
        self.assertEqual(value["captures"][0]["received_at"], CAPTURED.isoformat())
        self.assertFalse(value["prediction_eligible"])
        self.assertEqual(bytes.fromhex(value["captures"][0]["raw_hex"]), raw)

    def test_wrong_raw_hash_is_rejected(self):
        raw = json.dumps(body()).encode()
        r = receipt(raw)
        r["sha256"] = "0" * 64
        with self.assertRaisesRegex(market_frame.FrameError, "RECORDED_RAW_HASH_MISMATCH"):
            collector.replay(config(), raw, r)

    def test_raw_survives_json_failure(self):
        value = collector.replay(config(), b"not-json", receipt(b"not-json"))
        self.assertIsNone(value["market_frame"])
        self.assertEqual(value["completeness"], "INCOMPLETE")
        self.assertEqual(bytes.fromhex(value["captures"][0]["raw_hex"]), b"not-json")

    def test_replay_without_isolation_cannot_construct_remote_store(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "config.json").write_text(json.dumps(config()))
            (root / "raw.json").write_text(json.dumps(body()))
            (root / "receipt.json").write_text(
                json.dumps(receipt((root / "raw.json").read_bytes()))
            )
            with patch("worker.PostgresStore") as remote, contextlib.redirect_stdout(io.StringIO()):
                status = collector.main(
                    [
                        "--config",
                        str(root / "config.json"),
                        "--recorded-response",
                        str(root / "raw.json"),
                        "--recorded-receipt",
                        str(root / "receipt.json"),
                    ]
                )
            self.assertEqual(status, 1)
            remote.assert_not_called()

    def test_partial_batch_persisted_and_reported_incomplete_not_failed_or_filled(self):
        data = body()
        data["quotes"].pop()
        raw = json.dumps(data).encode()
        value = collector.replay(config(), raw, receipt(raw))
        with tempfile.TemporaryDirectory() as folder:
            store = worker.SQLiteStore(Path(folder) / "isolated.sqlite")
            digest = store.save(value)
            saved = store.db.execute(
                "SELECT raw FROM attempts WHERE digest=?", (digest,)
            ).fetchone()[0]
            recovered = json.loads(gzip.decompress(saved))
            self.assertEqual(
                recovered["market_frame"]["coverage"]["missing_quote_identities"], ["B"]
            )
            self.assertEqual(recovered["execution"], "RECORDED_REPLAY")
            self.assertFalse(
                store.complete(config()["provider_namespace"], "quotes", value["slot"])
            )
            store.db.close()

    def test_cli_replay_creates_only_isolated_data_and_summary_contains_no_source_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = json.dumps(body()).encode()
            for name, data in [("config.json", config()), ("receipt.json", receipt(raw))]:
                (root / name).write_text(json.dumps(data))
            (root / "raw.json").write_bytes(raw)
            output = io.StringIO()
            with (
                patch("worker.PostgresStore") as remote,
                patch("worker.fetch") as fetch,
                contextlib.redirect_stdout(output),
            ):
                result = collector.main(
                    [
                        "--config",
                        str(root / "config.json"),
                        "--recorded-response",
                        str(root / "raw.json"),
                        "--recorded-receipt",
                        str(root / "receipt.json"),
                        "--isolated-store",
                        str(root / "isolated.sqlite"),
                    ]
                )
            self.assertEqual(result, 0)
            remote.assert_not_called()
            fetch.assert_not_called()
            metrics = json.loads(output.getvalue())
            self.assertEqual(metrics["stock_quotes"], 2)
            self.assertNotIn("recipe", metrics)
            self.assertNotIn("views", metrics)
            self.assertEqual(metrics["execution"], "RECORDED_REPLAY")

    def test_current_capture_is_labeled_without_claiming_prediction_or_valuation(self):
        value = collector.envelope(
            config(),
            json.dumps(body()).encode(),
            CAPTURED,
            CAPTURED.isoformat(),
            execution="CURRENT_ACQUISITION",
        )
        self.assertEqual(value["execution"], "CURRENT_ACQUISITION")
        self.assertFalse(value["prediction_eligible"])
        self.assertFalse(value["market_frame"]["portfolio_valuation_eligible"])

    def test_observation_identity_is_stable_for_replay_not_processing_timestamp(self):
        raw = json.dumps(body()).encode()
        first = collector.replay(config(), raw, receipt(raw))
        second = collector.replay(config(), raw, receipt(raw))
        self.assertEqual(first["captures"][0]["capture_id"], second["captures"][0]["capture_id"])
        self.assertEqual(
            first["market_frame"]["views"]["quotes"][0]["observation_id"],
            second["market_frame"]["views"]["quotes"][0]["observation_id"],
        )
        later = receipt(raw)
        later["received_at"] = (CAPTURED + timedelta(seconds=1)).isoformat()
        self.assertNotEqual(
            first["captures"][0]["capture_id"],
            collector.replay(config(), raw, later)["captures"][0]["capture_id"],
        )

    def test_duplicate_security_rows_have_distinct_source_observation_identities(self):
        data = body()
        data["quotes"].append(dict(data["quotes"][0], p="11,00"))
        raw = json.dumps(data).encode()
        value = collector.replay(config(), raw, receipt(raw))
        rows = value["market_frame"]["views"]["quotes"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({row["observation_id"] for row in rows}), 3)
        self.assertEqual(value["completeness"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()

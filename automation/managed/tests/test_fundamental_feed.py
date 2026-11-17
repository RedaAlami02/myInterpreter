import gzip
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fundamental_feed
import worker
from test_fundamental_frame import financial, tables

ROOT = Path(__file__).resolve().parents[3]
PROVIDER = "feed_0123456789abcdef"
CAPTURED = datetime(2026, 10, 28, 14, 10, tzinfo=timezone.utc)


def config():
    return {"contract": "private-fundamental-config/v1", "provider_namespace": PROVIDER}


def index(symbols=None):
    return {
        "contract": "private-fundamental-index/v1",
        "provider_namespace": PROVIDER,
        "symbols": symbols if symbols is not None else {"AAA": "Alpha"},
    }


def payloads():
    return {
        "stock": {"name": "Alpha SA"},
        "symlinks": [{"symbol": "AAA", "name": "Alpha SA", "type": "Banks"}],
        "financial": financial(),
        **tables(),
    }


def archive(values=None, symbol="AAA", execution="CURRENT_ACQUISITION",
            completeness="COMPLETE"):
    values = values if values is not None else payloads()
    captures, targets = [], []
    for position, (kind, value) in enumerate(values.items()):
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        digest = hashlib.sha256(raw).hexdigest()
        identity = hashlib.sha256(
            json.dumps(
                [PROVIDER, digest, CAPTURED.isoformat()], separators=(",", ":")
            ).encode()
        ).hexdigest()
        captures.append(
            {
                "request_index": position,
                "capture_id": identity,
                "received_at": CAPTURED.isoformat(),
                "sha256": digest,
                "raw_hex": raw.hex(),
            }
        )
        targets.append({"request_index": position, "kind": kind})
    value = {
        "contract": "private-acquisition/v2",
        "provider_namespace": PROVIDER,
        "kind": "fundamentals",
        "symbol": symbol,
        "slot": CAPTURED.replace(minute=0, second=0, microsecond=0).isoformat(),
        "completed_at": CAPTURED.isoformat(),
        "execution": execution,
        "completeness": completeness,
        "errors": [],
        "captures": captures,
        "targets": targets,
        "authority": "UNPROMOTED",
        "prediction_eligible": False,
    }
    return worker.packed(value)


def build(values=None, selected_index=None, as_of=CAPTURED, **options):
    digest, blob = archive(values, **options)
    return fundamental_feed.build(
        blob, digest, config(), selected_index or index(), as_of=as_of
    )


class ProjectionTests(unittest.TestCase):
    def test_projection_carries_the_reported_figures_and_identity(self):
        value = build()
        self.assertEqual(value["contract"], "fundamental-projection/v1")
        self.assertEqual(value["mode"], "PROJECTION_ONLY")
        self.assertEqual(value["symbol"], "AAA")
        self.assertEqual(value["c_name"], "Alpha")
        fields = value["fields"]
        self.assertEqual(fields["fiscal_year"], 2023)
        self.assertEqual(fields["ext_name"], "Alpha SA")
        self.assertEqual(fields["sector"], "Banks")
        self.assertEqual(fields["net_profit"], 20.0)
        self.assertEqual(fields["revenue"], 140.0)
        self.assertEqual(fields["bpa"], 16.67)
        self.assertEqual(fields["na"], 1200000.0)
        self.assertEqual(fields["fy_est"], 2025)
        self.assertEqual(fields["rnpg_est"], 30.0)
        self.assertEqual(
            json.loads(fields["shareholders"]), [{"name": "Holder", "pct": 51.0}]
        )
        self.assertEqual(value["errors"], [])
        self.assertEqual(value["completeness"], "COMPLETE")
        self.assertFalse(value["prediction_eligible"])
        self.assertFalse(value["portfolio_valuation_eligible"])
        self.assertEqual(
            value["candidate_sha256"],
            fundamental_feed.fingerprint(
                {key: item for key, item in value.items() if key != "candidate_sha256"}
            ),
        )

    def test_unmapped_symbol_is_refused(self):
        with self.assertRaisesRegex(ValueError, "SYMBOL_NOT_MAPPED"):
            build(selected_index=index({"BBB": "Beta"}))

    def test_index_contract_and_provider_are_enforced(self):
        for selected in [
            {**index(), "contract": "private-fundamental-index/v0"},
            {**index(), "provider_namespace": "feed_1111111111111111"},
            {**index(), "symbols": {}},
            {**index(), "symbols": {"AAA": 5}},
        ]:
            with self.assertRaisesRegex(ValueError, "INVALID_FUNDAMENTAL_INDEX"):
                build(selected_index=selected)

    def test_archive_tampering_and_replay_are_refused(self):
        digest, blob = archive()
        with self.assertRaisesRegex(ValueError, "ARCHIVE_HASH_MISMATCH"):
            fundamental_feed.build(blob, "b" * 64, config(), index(), as_of=CAPTURED)
        original = json.loads(gzip.decompress(blob))
        for mode in ["raw", "capture", "target", "unreferenced", "replay", "kind"]:
            value = json.loads(json.dumps(original))
            if mode == "raw":
                value["captures"][0]["sha256"] = "c" * 64
            if mode == "capture":
                value["captures"][0]["capture_id"] = "c" * 64
            if mode == "target":
                value["targets"][1]["kind"] = value["targets"][0]["kind"]
            if mode == "unreferenced":
                value["targets"].pop()
            if mode == "replay":
                value["execution"] = "RECORDED_REPLAY"
            if mode == "kind":
                value["kind"] = "quotes"
            altered_digest, altered = worker.packed(value)
            with self.assertRaises(ValueError):
                fundamental_feed.build(
                    altered, altered_digest, config(), index(), as_of=CAPTURED
                )

    def test_undecodable_response_is_reported_and_never_guessed(self):
        values = payloads()
        values["desc"] = b'{"broken": '
        value = build(values)
        self.assertIsNone(value["fields"]["description"])
        self.assertEqual(value["errors"], [{"kind": "desc"}])
        self.assertEqual(value["completeness"], "INCOMPLETE")
        self.assertEqual(value["fields"]["fiscal_year"], 2023)

    def test_invalid_derived_values_are_refused(self):
        values = payloads()
        values["holders"] = {"data": [{"Shareholder": "X", "Percentage": 1.5}]}
        with self.assertRaisesRegex(ValueError, "INVALID_FUNDAMENTAL_VALUE"):
            build(values)

    def test_incomplete_acquisition_is_reported(self):
        value = build(completeness="INCOMPLETE")
        self.assertEqual(value["completeness"], "INCOMPLETE")

    def test_cutoff_before_completion_is_refused(self):
        digest, blob = archive()
        with self.assertRaisesRegex(ValueError, "INVALID_PROJECTION_CUTOFF"):
            fundamental_feed.build(
                blob,
                digest,
                config(),
                index(),
                as_of=CAPTURED - timedelta(seconds=1),
            )


if __name__ == "__main__":
    unittest.main()

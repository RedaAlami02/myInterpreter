from datetime import datetime, timedelta, timezone
import hashlib, json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from depth_frame import manifest, normalize
from market_frame import FrameError

NOW = datetime(2026, 10, 27, 14, 10, tzinfo=timezone.utc)


def spec():
    fields = {
        "price_decimal": {"path": ["price"], "type": "decimal", "optional": True},
        "quantity_decimal": {"path": ["quantity"], "type": "decimal", "optional": True},
        "orders_decimal": {"path": ["orders"], "type": "decimal", "optional": True},
        "level_time_text": {"path": ["clock"], "type": "text", "optional": True},
    }
    return {
        "summary_path": ["summary"],
        "summary_fields": {
            "source_identity": {"path": ["symbol"], "type": "text"},
            "reported_time": {
                "path": ["time"],
                "type": "reported_time",
                "format": "%d/%m/%Y %H:%M:%S",
            },
        },
        "bids": {"rows_path": ["bids"], "fields": fields},
        "asks": {"rows_path": ["asks"], "fields": fields},
    }


def body():
    return {
        "summary": {"symbol": "A", "time": "27/10/2026 14:00:00"},
        "bids": [{"price": 10, "quantity": 20, "orders": 2, "clock": "14:00:01"}],
        "asks": [{"price": 11, "quantity": 30, "orders": 3, "clock": "14:00:02"}],
    }


def parse(data=None, identity="A"):
    return normalize(json.dumps(body() if data is None else data).encode(), spec(), identity, NOW)


class DepthFrameTests(unittest.TestCase):
    def test_native_clock_and_source_order_retained_without_utc_guess(self):
        result = parse()
        self.assertEqual(result["bids"][0]["level_time_text"], "14:00:01")
        self.assertIsNone(result["summary"]["reported_time"]["utc"])
        self.assertEqual(result["captured_at"], NOW.isoformat())
        self.assertFalse(result["prediction_eligible"])

    def test_empty_book_is_an_explicit_source_result(self):
        data = body()
        data["bids"] = []
        data["asks"] = []
        result = parse(data)
        self.assertEqual(result["book_state"], "EMPTY")
        self.assertEqual(result["completeness"], "COMPLETE")

    def test_zero_placeholder_is_not_a_zero_price_order(self):
        data = body()
        data["bids"] = [{"price": 0, "quantity": 0}]
        self.assertEqual(parse(data)["bids"], [])

    def test_invalid_nonempty_level_is_partial_with_raw_hash_preserved(self):
        data = body()
        data["bids"][0]["quantity"] = 0
        result = parse(data)
        self.assertEqual(result["completeness"], "INCOMPLETE")
        self.assertEqual(
            result["raw_sha256"], hashlib.sha256(json.dumps(data).encode()).hexdigest()
        )

    def test_wrong_security_rejected(self):
        with self.assertRaisesRegex(FrameError, "RESPONSE_SECURITY_MISMATCH"):
            parse(identity="B")

    def test_crossed_book_is_flagged_not_sorted_or_repaired(self):
        data = body()
        data["bids"][0]["price"] = 12
        result = parse(data)
        self.assertEqual(result["book_state"], "CROSSED_UNCLASSIFIED")
        self.assertEqual(result["bids"][0]["price_decimal"], "12")

    def test_unordered_levels_preserved_and_flagged(self):
        data = body()
        data["bids"].append({"price": 11, "quantity": 1})
        result = parse(data)
        self.assertEqual([r["price_decimal"] for r in result["bids"]], ["10", "11"])
        self.assertEqual(result["completeness"], "INCOMPLETE")

    def test_fractional_quantity_rejected(self):
        data = body()
        data["bids"][0]["quantity"] = 1.5
        self.assertEqual(parse(data)["completeness"], "INCOMPLETE")

    def test_more_than_five_levels_rejected(self):
        data = body()
        data["bids"] *= 6
        with self.assertRaises(FrameError):
            parse(data)

    def batch(self, attempts, expected=None):
        return manifest(
            "feed_0123456789abcdef",
            expected or ["A"],
            attempts,
            started_at=NOW - timedelta(seconds=1),
            finished_at=NOW + timedelta(seconds=1),
        )

    def test_complete_manifest_is_not_prediction_authority(self):
        result = self.batch([{"source_identity": "A", "frame": parse()}])
        self.assertEqual(result["completeness"], "COMPLETE")
        self.assertFalse(result["prediction_eligible"])

    def test_missing_security_failed_request_and_duplicate_each_fail_completeness(self):
        for attempts, expected in [
            ([], ["A"]),
            ([{"source_identity": "A", "frame": None}], ["A"]),
            ([{"source_identity": "A", "frame": parse()}] * 2, ["A"]),
        ]:
            self.assertEqual(self.batch(attempts, expected)["completeness"], "INCOMPLETE")

    def test_capture_outside_batch_is_not_backdated_into_it(self):
        frame = parse()
        frame["captured_at"] = (NOW - timedelta(days=1)).isoformat()
        self.assertEqual(
            self.batch([{"source_identity": "A", "frame": frame}])["completeness"], "INCOMPLETE"
        )

    def test_manifest_digest_changes_for_any_capture_change(self):
        first = self.batch([{"source_identity": "A", "frame": parse()}])
        data = body()
        data["bids"][0]["price"] = 9
        second = self.batch([{"source_identity": "A", "frame": parse(data)}])
        self.assertNotEqual(first["manifest_sha256"], second["manifest_sha256"])

    def test_decimal_zero_placeholders_remain_empty(self):
        data = body()
        data["bids"] = [{"price": "0.00", "quantity": "0.0"}]
        result = parse(data)
        self.assertEqual(result["bids"], [])
        self.assertEqual(result["completeness"], "COMPLETE")

    def test_wrong_provider_namespace_rejected(self):
        with self.assertRaisesRegex(FrameError, "INVALID_DEPTH_BATCH"):
            manifest("original_provider", ["A"], [], started_at=NOW, finished_at=NOW)

    def test_unexpected_capture_is_explicitly_retained_in_manifest(self):
        result = self.batch([{"source_identity": "FOREIGN", "frame": parse()}])
        self.assertEqual(result["completeness"], "INCOMPLETE")
        self.assertEqual(result["entries"][0]["status"], "UNEXPECTED")
        self.assertEqual(result["entries"][0]["raw_sha256"], parse()["raw_sha256"])

    def test_empty_placeholder_does_not_require_a_level_clock(self):
        data = body()
        data["bids"] = [{"price": 0, "quantity": 0, "clock": ""}]
        result = parse(data)
        self.assertEqual(result["completeness"], "COMPLETE")
        self.assertEqual(result["bids"], [])

    def test_blank_optional_last_trade_is_null_only_with_explicit_policy(self):
        data = body()
        data["summary"]["last"] = ""
        recipe = spec()
        recipe["summary_fields"]["last_trade_price_decimal"] = {
            "path": ["last"], "type": "decimal", "optional": True,
        }
        with self.assertRaisesRegex(FrameError, "INVALID_NUMBER"):
            normalize(json.dumps(data).encode(), recipe, "A", NOW)
        recipe["summary_fields"]["last_trade_price_decimal"]["blank_is_null"] = True
        result = normalize(json.dumps(data).encode(), recipe, "A", NOW)
        self.assertIsNone(result["summary"]["last_trade_price_decimal"])
        self.assertEqual(result["bids"][0]["price_decimal"], "10")
        self.assertEqual(result["completeness"], "COMPLETE")
        self.assertFalse(result["prediction_eligible"])

    def test_blank_policy_does_not_hide_nonblank_malformed_last_trade(self):
        recipe = spec()
        recipe["summary_fields"]["last_trade_price_decimal"] = {
            "path": ["last"], "type": "decimal", "optional": True,
            "blank_is_null": True,
        }
        for value in ["bad", " ", "NaN", True]:
            data = body()
            data["summary"]["last"] = value
            with self.subTest(value=value), self.assertRaisesRegex(FrameError, "INVALID_NUMBER"):
                normalize(json.dumps(data).encode(), recipe, "A", NOW)

    def test_blank_required_level_price_still_invalid(self):
        data = body()
        data["bids"][0]["price"] = ""
        recipe = spec()
        recipe["bids"]["fields"]["price_decimal"]["blank_is_null"] = True
        result = normalize(json.dumps(data).encode(), recipe, "A", NOW)
        self.assertEqual(result["completeness"], "INCOMPLETE")
        self.assertEqual(result["bids"], [])

    def test_failed_normalization_manifest_retains_raw_receipt(self):
        digest = "a" * 64
        result = self.batch([{
            "source_identity": "A", "frame": None,
            "raw_sha256": digest, "captured_at": NOW.isoformat(), "code": "INVALID_NUMBER",
        }])
        entry = result["entries"][0]
        self.assertEqual(entry["raw_sha256"], digest)
        self.assertEqual(entry["captured_at"], NOW.isoformat())
        self.assertEqual(entry["error_code"], "INVALID_NUMBER")
        self.assertEqual(entry["status"], "FAILED")
        self.assertEqual(result["completeness"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()

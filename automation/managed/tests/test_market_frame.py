from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_frame as frame

CAPTURED = datetime(2026, 10, 27, 14, 10, tzinfo=timezone.utc)
DAY = date(2026, 10, 27)


def recipe():
    return {
        "expected_stock_identities": ["A", "B"],
        "expected_index_identities": ["INDEX_MAIN"],
        "views": {
            "instruments": {
                "rows_path": ["catalog"],
                "fields": {
                    "source_identity": {"path": ["key"], "type": "text"},
                    "reported_price_decimal": {
                        "path": ["p"],
                        "type": "decimal",
                        "locale": "comma",
                        "optional": True,
                    },
                },
            },
            "quotes": {
                "rows_path": ["quotes"],
                "fields": {
                    "source_identity": {"path": ["key"], "type": "text"},
                    "price_decimal": {"path": ["p"], "type": "decimal", "locale": "comma"},
                    "reported_time": {
                        "path": ["time"],
                        "type": "reported_time",
                        "format": "%d/%m/%Y %H:%M:%S",
                    },
                },
            },
            "indices": {
                "rows_path": ["indices"],
                "constants": {"source_identity": "INDEX_MAIN"},
                "fields": {
                    "price_decimal": {"path": ["p"], "type": "decimal", "locale": "comma"},
                    "reported_time": {
                        "path": ["time"],
                        "type": "reported_time",
                        "format": "%d/%m/%Y %H:%M:%S",
                    },
                },
            },
            "status": {
                "rows_path": ["status"],
                "fields": {"state_code": {"path": ["code"], "type": "code"}},
            },
        },
    }


def body():
    return {
        "catalog": [{"key": "A", "p": "10,50"}, {"key": "B", "p": "21,25"}],
        "quotes": [
            {"key": "A", "p": "10,50", "time": "27/10/2026 14:00:00"},
            {"key": "B", "p": "21,25", "time": "27/10/2026 14:00:00"},
        ],
        "indices": [{"p": "1234,56", "time": "27/10/2026 14:05:00"}],
        "status": [{"code": 1}],
    }


def parse(data=None, spec=None):
    return frame.normalize(
        json.dumps(body() if data is None else data).encode(),
        spec or recipe(),
        CAPTURED,
        market_date=DAY,
    )


class MarketFrameTests(unittest.TestCase):
    def test_complete_calendar_coverage_never_promotes_authority(self):
        result = parse()
        self.assertEqual(result["completeness"], "COMPLETE")
        self.assertFalse(result["prediction_eligible"])
        self.assertFalse(result["portfolio_valuation_eligible"])
        quote = result["views"]["quotes"][0]
        self.assertEqual(quote["price_decimal"], "10.50")
        self.assertEqual(quote["reported_time"]["timezone"], "UNKNOWN")
        self.assertIsNone(quote["reported_time"]["utc"])
        self.assertEqual(quote["captured_at"], CAPTURED.isoformat())
        self.assertFalse(quote["source_timezone_known"])

    def test_reference_catalog_does_not_manufacture_missing_quote(self):
        data = body()
        data["quotes"].pop()
        result = parse(data)
        self.assertEqual(result["completeness"], "INCOMPLETE")
        self.assertEqual(len(result["views"]["instruments"]), 2)
        self.assertEqual(len(result["views"]["quotes"]), 1)
        self.assertEqual(result["coverage"]["missing_quote_identities"], ["B"])

    def test_last_reported_reference_price_is_not_copied_into_quotes(self):
        data = body()
        data["catalog"][1]["p"] = "999,00"
        data["quotes"].pop()
        result = parse(data)
        self.assertEqual(result["views"]["instruments"][1]["reported_price_decimal"], "999.00")
        self.assertEqual([r["source_identity"] for r in result["views"]["quotes"]], ["A"])

    def test_stale_source_date_is_preserved_and_coverage_fails(self):
        data = body()
        data["quotes"][0]["time"] = "26/10/2026 14:00:00"
        result = parse(data)
        self.assertEqual(result["completeness"], "INCOMPLETE")
        self.assertEqual(result["views"]["quotes"][0]["reported_time"]["date"], "2026-10-26")
        self.assertFalse(result["views"]["quotes"][0]["source_date_matches_capture"])

    def test_future_naive_date_is_not_certified(self):
        data = body()
        data["quotes"][0]["time"] = "28/10/2026 14:00:00"
        self.assertEqual(parse(data)["completeness"], "INCOMPLETE")

    def test_missing_and_wrong_index_both_fail(self):
        data = body()
        data["indices"] = []
        self.assertEqual(parse(data)["completeness"], "INCOMPLETE")
        spec = recipe()
        spec["views"]["indices"]["constants"]["source_identity"] = "WRONG_INDEX"
        self.assertEqual(parse(spec=spec)["completeness"], "INCOMPLETE")

    def test_duplicate_observations_and_conflicting_prices_both_retained(self):
        data = body()
        data["quotes"].append(dict(data["quotes"][0], p="11,00"))
        result = parse(data)
        self.assertEqual(len(result["views"]["quotes"]), 3)
        self.assertEqual(result["completeness"], "INCOMPLETE")
        self.assertIn("CONFLICTING_IDENTITIES", [i["code"] for i in result["issues"]])

    def test_zero_bool_nan_and_malformed_prices_rejected_without_zero_fill(self):
        for price in ["0,00", True, "1,2,3", "NaN", "-2,50"]:
            data = body()
            data["quotes"][0]["p"] = price
            result = parse(data)
            self.assertEqual(result["completeness"], "INCOMPLETE")
            self.assertEqual([r["source_identity"] for r in result["views"]["quotes"]], ["B"])

    def test_numeric_precision_and_locale_are_explicit(self):
        raw = b'{"x":1.1234567890123456789012345}'
        value = frame.read_json(raw)["x"]
        self.assertIsInstance(value, Decimal)
        self.assertEqual(frame.decimal_value(value, "plain"), "1.1234567890123456789012345")
        self.assertEqual(frame.decimal_value("1\u202f234,50", "comma"), "1234.50")
        self.assertEqual(frame.decimal_value("1.234,50", "comma_dot_grouping"), "1234.50")
        for value, locale in [("1.234,50", "plain"), ("12 34,50", "comma"), ("1e1000000", "plain")]:
            with self.assertRaises(frame.FrameError):
                frame.decimal_value(value, locale)

    def test_unexpected_identity_is_not_merged_with_expected_security(self):
        data = body()
        data["quotes"][0]["key"] = "C"
        result = parse(data)
        self.assertEqual(result["completeness"], "INCOMPLETE")
        self.assertEqual(result["coverage"]["unexpected_identities"], ["C"])

    def test_invalid_source_section_does_not_reuse_its_data(self):
        data = body()
        data["valid"] = False
        spec = recipe()
        spec["views"]["quotes"]["checks"] = [{"path": ["valid"], "equals": True}]
        self.assertEqual(parse(data, spec)["views"]["quotes"], [])

    def test_field_dates_and_prices_cannot_come_from_constants(self):
        for field, value in [("price_decimal", "99.00"), ("reported_time", "2026-10-27")]:
            spec = recipe()
            spec["views"]["quotes"]["constants"] = {field: value}
            with self.assertRaises(frame.FrameError):
                parse(spec=spec)

    def test_missing_optional_field_is_explicitly_null(self):
        data = body()
        del data["catalog"][0]["p"]
        self.assertIsNone(parse(data)["views"]["instruments"][0]["reported_price_decimal"])

    def test_naive_clock_never_becomes_aware_by_configuration(self):
        spec = recipe()
        spec["views"]["quotes"]["fields"]["source_event_at"] = {
            "path": ["time"],
            "type": "aware_time",
        }
        result = parse(spec=spec)
        self.assertEqual(result["views"]["quotes"], [])
        self.assertEqual(result["completeness"], "INCOMPLETE")

    def test_aware_future_and_stale_events_rejected(self):
        spec = recipe()
        spec["views"]["quotes"]["fields"]["source_event_at"] = {
            "path": ["event"],
            "type": "aware_time",
        }
        for event in ["2026-10-27T14:11:00Z", "2026-10-27T10:00:00Z"]:
            data = body()
            for row in data["quotes"]:
                row["event"] = event
            self.assertEqual(parse(data, spec)["views"]["quotes"], [])

    def test_capture_and_market_date_cannot_be_backdated_independently(self):
        with self.assertRaises(frame.FrameError):
            frame.normalize(
                json.dumps(body()).encode(), recipe(), CAPTURED, market_date=date(2026, 10, 26)
            )

    def test_root_bindings_keep_index_reported_date_separate_from_stock_date(self):
        spec = recipe()
        spec["views"]["indices"]["fields"]["reported_time"] = {
            "path": ["indices", 0, "time"],
            "scope": "document",
            "type": "reported_time",
            "format": "%d/%m/%Y %H:%M:%S",
        }
        self.assertEqual(parse(spec=spec)["completeness"], "COMPLETE")

    def test_digest_covers_original_bytes_without_reserialization(self):
        raw = json.dumps(body(), indent=3).encode()
        result = frame.normalize(raw, recipe(), CAPTURED, market_date=DAY)
        self.assertEqual(result["raw_sha256"], hashlib.sha256(raw).hexdigest())

    def test_optional_flag_cannot_hide_a_missing_required_price(self):
        data = body()
        data["quotes"][0]["p"] = None
        configured = recipe()
        configured["views"]["quotes"]["fields"]["price_decimal"]["optional"] = True
        result = parse(data, configured)
        self.assertEqual(result["completeness"], "INCOMPLETE")
        self.assertEqual([r["source_identity"] for r in result["views"]["quotes"]], ["B"])


if __name__ == "__main__":
    unittest.main()

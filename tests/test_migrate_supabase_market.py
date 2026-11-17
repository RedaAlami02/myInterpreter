import importlib.util
from datetime import timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("migrate_supabase_market", TOOLS / "migrate_supabase_market.py")
MARKET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MARKET)


class MarketMigrationTests(unittest.TestCase):
    def test_precise_numbers_and_negative_ratios_remain_intact(self):
        value = Decimal("123456789012345678901234567890.123456789")
        self.assertEqual(MARKET.convert(value, "numeric"), value)
        self.assertNotEqual(MARKET.row_hash({"x": value}), MARKET.row_hash({"x": value + 1}))
        row = MARKET.normalize("data", {"$id": "original", "c_name": "FIXTURE", "pa": 123.45,
                                      "date": "2026-10-21T10:29:37+01:00", "per": -70.97})
        self.assertEqual(row["per"], Decimal("-70.97"))
        self.assertIsNone(row["pb"])
        self.assertEqual(row["date"].tzinfo, timezone.utc)
        self.assertEqual(row["date"].hour, 9)

    def test_source_metadata_and_unapproved_fields_are_excluded(self):
        row = MARKET.normalize("dividends", {"$id": "original", "c_name": "FIXTURE", "year": 2026,
                                           "confirmed": False, "source": "fixture-provider",
                                           "$permissions": ["private"], "secret": "fixture"})
        self.assertFalse(row["confirmed"])
        self.assertIsNone(row["amount"])
        self.assertNotIn("source", row)
        self.assertNotIn("$permissions", row)
        self.assertNotIn("secret", row)

    def test_typed_values_are_not_silently_coerced(self):
        for value, kind in [(True, "integer"), ("123.45", "numeric"), (1.5, "bigint"),
                            (2**31, "integer"), (float("nan"), "numeric"), ("false", "boolean"),
                            ("2026-10-21T09:30:00", "timestamptz"), ("2026-10", "date")]:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                MARKET.convert(value, kind)

    def test_latest_quote_uses_actual_timestamp_and_keeps_old_date(self):
        old = {"$id": "old", "c_name": "FIXTURE", "pa": 100, "date": "2026-09-19T12:00:00Z"}
        newer = dict(old, **{"$id": "new", "pa": 101.5, "date": "2026-10-21T12:00:00Z"})
        selected = MARKET.choose_latest([(old, "latest_prices"), (newer, "data")])
        self.assertEqual(selected[0]["id"], "new")
        self.assertEqual(selected[0]["origin_collection"], "data")
        self.assertEqual(selected[0]["date"].isoformat(), "2026-10-21T12:00:00+00:00")
        self.assertEqual(MARKET.choose_latest([(old, "latest_prices")])[0]["id"], "old")

    def test_equal_timestamp_conflicts_fail_and_equal_prices_are_deterministic(self):
        a = {"$id": "a", "c_name": "FIXTURE", "pa": 100, "date": "2026-10-21T12:00:00Z"}
        b = dict(a, **{"$id": "b"})
        candidates = [(b, "data"), (a, "data")]
        self.assertEqual(MARKET.choose_latest(candidates), MARKET.choose_latest(reversed(candidates)))
        with self.assertRaises(ValueError):
            MARKET.choose_latest([(a, "data"), (dict(b, pa=101), "data")])


if __name__ == "__main__":
    unittest.main()

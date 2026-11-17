from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_supabase_recovery import compare_daily_reference, compare_rows


class RecoveryAuditTests(unittest.TestCase):
    def test_missing_extra_and_changed_records_are_separate(self):
        expected = [{"id": "a", "pa": Decimal("100.15")},
                    {"id": "b", "per": -70.97}, {"id": "c", "pb": None}]
        actual = [{"id": "a", "pa": Decimal("100.1500")},
                  {"id": "b", "per": -70.96}, {"id": "d", "pb": None}]
        result = compare_rows(expected, iter(actual))
        self.assertEqual([result[k] for k in ("matching_rows", "changed_rows", "missing_rows", "extra_rows")], [1, 1, 1, 1])
        self.assertFalse(result["all_typed_values_match"])

    def test_order_and_equivalent_numeric_formatting_do_not_change_values(self):
        rows = [{"id": "a", "pa": Decimal("100.15"), "per": Decimal("-70.97"), "pb": None},
                {"id": "b", "na": Decimal("123456789012345678901234567890.12345")}]
        self.assertTrue(compare_rows(rows, iter(reversed(rows)))["all_typed_values_match"])

    def test_duplicate_expected_ids_fail_instead_of_hiding_missing_data(self):
        with self.assertRaises(ValueError):
            compare_rows([{"id": "a"}, {"id": "a"}], [])

    def test_daily_reference_distinguishes_gaps_and_intraday_differences_without_overwriting(self):
        first = {"id": "a", "c_name": "Fixture", "date": datetime(2026, 10, 20, 10, tzinfo=timezone.utc), "pa": Decimal("100")}
        newer = dict(first, id="b", date=datetime(2026, 10, 20, 15, tzinfo=timezone.utc), pa=Decimal("102"))
        prepared = {"format": [{"name": "Fixture", "symbol": "FIX"}], "data": [first, newer]}
        reference = [{"symbol": "FIX", "date": "2026-10-20", "close": 103},
                     {"symbol": "FIX", "date": "2026-10-21", "close": 104}]
        result = compare_daily_reference(prepared, reference)
        self.assertEqual(result["overlapping_company_days"], 1)
        self.assertEqual(result["different_last_capture_prices"], 1)
        self.assertEqual(result["missing_company_days"], 1)
        self.assertEqual(result["rows_imported"], 0)
        self.assertEqual(newer["pa"], Decimal("102"))

    def test_duplicate_reference_days_are_not_silently_chosen(self):
        prepared = {"format": [{"name": "Fixture", "symbol": "FIX"}], "data": []}
        row = {"symbol": "FIX", "date": "2026-10-20", "close": 100}
        with self.assertRaises(ValueError):
            compare_daily_reference(prepared, [row, row])


if __name__ == "__main__":
    unittest.main()

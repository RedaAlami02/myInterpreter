import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_health


class MarketHealthTests(unittest.TestCase):
    def setUp(self):
        self.as_of = datetime(2026, 11, 16, tzinfo=timezone.utc)
        self.companies = [
            {"name": "FRESH", "fiscal_year": 2025, "na": 100,
             "shareholders": '[{"name":"Holder","pct":10}]'},
            {"name": "STALE", "fiscal_year": 2024, "na": 100, "shareholders": ""},
            {"name": "MISSING", "fiscal_year": None, "na": None, "shareholders": "[]"},
            {"name": "ZERO", "fiscal_year": 2025, "na": 100,
             "shareholders": '[{"name":"Holder","pct":10}]'},
        ]
        self.prices = [
            {"c_name": "FRESH", "pa": 10, "date": "2026-11-16T15:00:00Z"},
            {"c_name": "STALE", "pa": 5, "date": "2026-10-01T15:00:00Z"},
            {"c_name": "ZERO", "pa": 0, "date": "2026-11-16T15:00:00Z"},
        ]
        self.dividends = [
            {"c_name": "FRESH", "year": 2025, "confirmed": True},
            {"c_name": "STALE", "year": 2020, "confirmed": True},
        ]
        self.formats = [{"name": name, "symbol": name} for name in
                        ("FRESH", "STALE", "MISSING", "ZERO")]

    def test_statuses_and_summary(self):
        report = market_health.audit(
            self.prices, self.companies, self.dividends, self.formats,
            as_of=self.as_of, max_age_days=7)
        summary = report["summary"]
        self.assertEqual(summary["companies"], 4)
        self.assertEqual(summary["price_ok"], 1)
        self.assertEqual(summary["price_stale"], 1)
        self.assertEqual(summary["price_missing"], 1)
        self.assertEqual(summary["price_zero"], 1)
        self.assertEqual(summary["fiscal_stale"], 1)
        self.assertEqual(summary["fiscal_missing"], 1)
        self.assertEqual(summary["shares_missing"], 1)
        self.assertEqual(summary["dividend_recent"], 1)
        self.assertEqual(summary["dividend_stale"], 1)
        self.assertEqual(summary["dividend_missing"], 2)
        self.assertEqual(summary["shareholders_missing"], 2)
        self.assertEqual(summary["needs_attention"], 3)
        by_name = {row["name"]: row for row in report["companies"]}
        self.assertTrue(any(flag.startswith("PRICE_STALE_") for flag in by_name["STALE"]["flags"]))
        self.assertIn("PRICE_MISSING", by_name["MISSING"]["flags"])
        self.assertIn("FISCAL_YEAR_MISSING", by_name["MISSING"]["flags"])
        self.assertIn("SHARES_MISSING", by_name["MISSING"]["flags"])
        self.assertEqual(by_name["FRESH"]["dividend_status"], "CONFIRMED")

    def test_report_shapes(self):
        report = market_health.audit(
            self.prices, self.companies, self.dividends, self.formats,
            as_of=self.as_of)
        rows = market_health.to_csv_rows(report)
        self.assertEqual(len(rows), 4)
        self.assertIn("PRICE_STALE", rows[0]["flags"] + rows[1]["flags"] + rows[2]["flags"])
        self.assertIn("Market data health", market_health.to_markdown(report))


if __name__ == "__main__":
    unittest.main()

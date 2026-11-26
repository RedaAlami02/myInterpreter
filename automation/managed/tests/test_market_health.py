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
            {"c_name": "FRESH", "year": 2025, "confirmed": True, "amount": 1.5,
             "ex_date": "2026-07-01", "pay_date": "2026-07-15", "type": "Ordinary"},
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
        self.assertEqual(by_name["FRESH"]["dividend_amount"], 1.5)
        self.assertEqual(by_name["FRESH"]["dividend_pay_date"], "2026-07-15")

    def test_an_instrument_the_exchange_did_not_trade_is_not_stale(self):
        history = [
            {"c_name": "STALE", "date": "2026-11-16T15:00:00Z",
             "volume": None, "qty_traded": None},
            {"c_name": "FRESH", "date": "2026-11-16T15:00:00Z",
             "volume": 1000, "qty_traded": 10},
        ]
        traded = market_health.traded_in_latest_session(history)
        self.assertNotIn("STALE", traded)
        report = market_health.audit(
            self.prices, self.companies, self.dividends, self.formats,
            as_of=self.as_of, max_age_days=7, traded=traded)
        by_name = {row["name"]: row for row in report["companies"]}
        self.assertEqual(by_name["STALE"]["price_status"], "NOT_TRADED")
        self.assertEqual(report["summary"]["price_stale"], 0)

    def test_a_trade_without_a_price_update_is_still_stale(self):
        history = [
            {"c_name": "STALE", "date": "2026-11-16T15:00:00Z",
             "volume": 500, "qty_traded": 5},
            {"c_name": "FRESH", "date": "2026-11-16T15:00:00Z",
             "volume": 1000, "qty_traded": 10},
        ]
        traded = market_health.traded_in_latest_session(history)
        self.assertIn("STALE", traded)
        report = market_health.audit(
            self.prices, self.companies, self.dividends, self.formats,
            as_of=self.as_of, max_age_days=7, traded=traded)
        self.assertEqual(report["summary"]["price_stale"], 1)

    def test_an_empty_trade_map_keeps_the_old_verdict(self):
        report = market_health.audit(
            self.prices, self.companies, self.dividends, self.formats,
            as_of=self.as_of, max_age_days=7, traded=set())
        self.assertEqual(report["summary"]["price_stale"], 1)

    def test_report_shapes(self):
        report = market_health.audit(
            self.prices, self.companies, self.dividends, self.formats,
            as_of=self.as_of)
        rows = market_health.to_csv_rows(report)
        self.assertEqual(len(rows), 4)
        self.assertIn("PRICE_STALE", rows[0]["flags"] + rows[1]["flags"] + rows[2]["flags"])
        self.assertIn("Market data health", market_health.to_markdown(report))


class BookHealthTests(unittest.TestCase):
    def test_fresh_stale_and_missing_books(self):
        summary, statuses, ages = market_health.book_health(
            [{"symbol": "ADH", "captured_at": "2026-11-17T15:00:00Z"},
             {"symbol": "ADH", "captured_at": "2026-11-17T14:00:00Z"},
             {"symbol": "BCP", "captured_at": "2026-11-10T15:00:00Z"}],
            [{"symbol": "ADH"}, {"symbol": "BCP"}, {"symbol": "NRJ"}],
            as_of=datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(statuses["ADH"], "FRESH")
        self.assertEqual(statuses["BCP"], "STALE")
        self.assertEqual(statuses["NRJ"], "MISSING")
        self.assertEqual(ages["ADH"], 3.0)
        self.assertEqual(summary, {"book_symbols": 3, "book_fresh": 1,
                                   "book_stale": 1, "book_missing": 1,
                                   "book_untraded": 0})

    def test_a_suspended_instrument_has_no_book_to_miss(self):
        summary, statuses, _ages = market_health.book_health(
            [{"symbol": "ADH", "captured_at": "2026-11-17T15:00:00Z"}],
            [{"name": "ADDOHA", "symbol": "ADH"},
             {"name": "SAMIR", "symbol": "SAM"}],
            as_of=datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc),
            traded={"ADDOHA"})
        self.assertEqual(statuses["ADH"], "FRESH")
        self.assertEqual(statuses["SAM"], "NOT_TRADED")
        self.assertEqual(summary["book_missing"], 0)
        self.assertEqual(summary["book_untraded"], 1)

    def test_a_friday_close_is_fresh_on_monday_morning(self):
        summary, statuses, _ages = market_health.book_health(
            [{"symbol": "ADH", "captured_at": "2026-11-20T15:00:00Z"}],
            [{"symbol": "ADH"}],
            as_of=datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(statuses["ADH"], "FRESH")
        self.assertEqual(summary["book_fresh"], 1)


class HistoryHealthTests(unittest.TestCase):
    def test_history_ages_and_missing_companies(self):
        summary, statuses, ages = market_health.history_health(
            [{"c_name": "FRESH CO", "date": "2026-11-17T10:00:00Z"},
             {"c_name": "FRESH CO", "date": "2026-11-16T10:00:00Z"},
             {"c_name": "OLD CO", "date": "2026-10-21T10:00:00Z"}],
            [{"name": "FRESH CO", "symbol": "FRS"},
             {"name": "OLD CO", "symbol": "OLD"},
             {"name": "NEVER CO", "symbol": "NVR"}],
            as_of=datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(statuses, {"FRS": "FRESH", "OLD": "STALE", "NVR": "MISSING"})
        self.assertEqual(ages["OLD"], 27)
        self.assertEqual(summary["history_fresh"], 1)
        self.assertEqual(summary["history_stale"], 1)
        self.assertEqual(summary["history_missing"], 1)
        self.assertEqual(summary["history_latest_age_days"], 0)

    def test_empty_history_does_not_crash(self):
        summary, statuses, _ages = market_health.history_health(
            [], [{"name": "A", "symbol": "A"}],
            as_of=datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc))
        self.assertIsNone(summary["history_latest_age_days"])
        self.assertEqual(statuses, {"A": "MISSING"})


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import exchange_history as history

MOMENT = datetime(2026, 11, 17, 16, 45, tzinfo=timezone.utc)


def company(**overrides):
    value = {"name": "TEST CO", "cp": 1_000_000_000, "net_profit": 100,
             "bpa": 10, "tc5": 5, "roe": 10, "na": 5_000_000}
    value.update(overrides)
    return value


class RatioTests(unittest.TestCase):
    def test_per_uses_market_cap_over_net_income(self):
        per, _peg, _pr, _pb, _r = history.ratios(50, 1_000_000_000, company())
        self.assertAlmostEqual(per, 10.0)

    def test_negative_earnings_keep_a_negative_per_and_no_rating(self):
        per, _peg, _pr, _pb, ratings = history.ratios(50, 1_000_000_000,
                                                      company(net_profit=-100))
        self.assertAlmostEqual(per, -10.0)
        self.assertIsNone(ratings["per_rating"])

    def test_implausible_per_is_suppressed(self):
        per, peg, pr, _pb, ratings = history.ratios(
            10, 1_000_000_000, company(net_profit=0.5))
        self.assertIsNone(per)
        self.assertIsNone(peg)
        self.assertIsNone(pr)
        self.assertIsNone(ratings["per_rating"])

    def test_pb_and_its_rating(self):
        _per, _peg, _pr, pb, ratings = history.ratios(
            50, 1_000_000_000, company(cp=500_000_000))
        self.assertAlmostEqual(pb, 2.0)
        self.assertEqual(ratings["pb_rating"], "green")

    def test_peg_and_pr_require_meaningful_denominators(self):
        _per, peg, pr, _pb, _r = history.ratios(
            10, 1_000_000_000, company(tc5=0.5, roe=0.5))
        self.assertIsNone(peg)
        self.assertIsNone(pr)


class DailyRowTests(unittest.TestCase):
    def test_row_carries_market_fields(self):
        action = {"dernierCours": 50, "capitalisation": 1_000_000_000,
                  "reference": 49, "variation": 2.04, "ouverture": 49.5,
                  "plusHaut": 50.5, "plusBas": 48.9, "volume": 123456.7,
                  "quantite": 2500}
        row = history.daily_row("TST", "TEST CO", action, {}, company(), MOMENT)
        self.assertEqual(row["pa"], 50)
        self.assertEqual(row["cours_ref"], 49)
        self.assertAlmostEqual(row["variation_v"], 1.0)
        self.assertEqual(row["qty_traded"], 2500)
        self.assertEqual(row["trade_day"], "2026-11-17")

    def test_trade_day_is_the_casablanca_day(self):
        moment = datetime(2026, 11, 17, 23, 30, tzinfo=timezone.utc)
        expected = moment.astimezone(history.CASABLANCA).date().isoformat()
        row = history.daily_row("TST", "TEST CO", {"dernierCours": 50}, {}, company(), moment)
        self.assertEqual(row["trade_day"], expected)

    def test_missing_price_is_skipped_not_zeroed(self):
        self.assertIsNone(history.daily_row("TST", "TEST CO", {}, {}, company(), MOMENT))
        self.assertIsNone(history.daily_row("TST", "TEST CO", {"dernierCours": 0}, {},
                                            company(), MOMENT))

    def test_price_falls_back_to_the_instrument_record(self):
        row = history.daily_row("TST", "TEST CO", {}, {"price": 44}, company(), MOMENT)
        self.assertEqual(row["pa"], 44)

    def test_none_fields_are_omitted(self):
        row = history.daily_row("TST", "TEST CO", {"dernierCours": 50}, {}, company(), MOMENT)
        self.assertNotIn("volume", row)
        self.assertNotIn("open_price", row)


class BuildRowsTests(unittest.TestCase):
    def test_one_row_per_mapped_symbol_and_unpriced_are_listed(self):
        formats = [{"symbol": "AAA", "name": "AAA CO"}, {"symbol": "BBB", "name": "BBB CO"}]
        actions = [{"symbol": "AAA", "dernierCours": 10}]
        rows, skipped = history.build_rows([], actions, formats,
                                           {"AAA CO": company(), "BBB CO": company()}, MOMENT)
        self.assertEqual([row["symbol"] for row in rows], ["AAA"])
        self.assertEqual(skipped, ["BBB"])

    def test_unmapped_format_rows_are_ignored(self):
        rows, skipped = history.build_rows(
            [], [{"symbol": "AAA", "dernierCours": 10}],
            [{"symbol": "AAA", "name": ""}], {}, MOMENT)
        self.assertEqual(rows, [])
        self.assertEqual(skipped, [])


if __name__ == "__main__":
    unittest.main()

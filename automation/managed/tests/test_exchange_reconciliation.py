import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import exchange_reconciliation as recon


def record(**overrides):
    value = {
        "symbol": "TST",
        "company": "TEST COMPANY",
        "sector": "Industrie",
        "isin": "MA0000000000",
        "shares": 10_000_000,
        "nominal": 10,
        "price": 100.0,
        "cap": 1_000_000_000.0,
        "annual_rows": [{
            "exercice": 2025,
            "capitalSocial": 100_000_000,
            "capitalPropre": 500_000_000,
            "nombreTitres": 10_000_000,
            "chiffreAffaire": 800_000_000,
            "resultatExploitation": 120_000_000,
            "resultatNet": 100_000_000,
            "compteConsolide": True,
        }],
        "capital_actions": [],
    }
    value.update(overrides)
    return value


class CurrentShareTests(unittest.TestCase):
    def test_two_checks_verify(self):
        result = recon.validate_current_shares(record())
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["confidence"], "HIGH")
        self.assertEqual(result["shares"], 10_000_000)

    def test_capitalization_price_conflict_is_quarantined(self):
        result = recon.validate_current_shares(record(cap=10_000_000_000.0))
        self.assertEqual(result["status"], "CONFLICT")

    def test_missing_price_keeps_single_capital_check(self):
        result = recon.validate_current_shares(record(price=None, cap=None))
        self.assertEqual(result["status"], "VERIFIED_SINGLE_CHECK")
        self.assertEqual(result["confidence"], "MEDIUM")

    def test_no_independent_check_is_insufficient(self):
        result = recon.validate_current_shares(record(price=None, cap=None, annual_rows=[]))
        self.assertEqual(result["status"], "INSUFFICIENT")

    def test_latest_capital_action_beats_annual_capital(self):
        result = recon.validate_current_shares(record(
            shares=12_000_000,
            cap=1_200_000_000.0,
            annual_rows=[{
                "exercice": 2025, "capitalSocial": 100_000_000,
                "capitalPropre": 500_000_000, "nombreTitres": 10_000_000,
                "chiffreAffaire": 800_000_000, "resultatExploitation": 120_000_000,
                "resultatNet": 100_000_000, "compteConsolide": True,
            }],
            capital_actions=[{"date": "2026-03-01", "capital": 120_000_000}],
        ))
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["latest_capital"], 120_000_000)

    def test_same_date_actions_use_the_final_total(self):
        result = recon.validate_current_shares(record(
            shares=38_641_338, nominal=100, price=315.0, cap=12_172_021_470.0,
            capital_actions=[
                {"date": "2026-08-04", "capital": 3_774_848_100, "nominal": 100},
                {"date": "2026-08-04", "capital": 3_864_133_800, "nominal": 100},
            ]))
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["latest_capital"], 3_864_133_800)

    def test_action_nominal_that_disagrees_with_current_is_a_conflict(self):
        result = recon.validate_current_shares(record(
            shares=17_695_150, nominal=10, price=49.3, cap=872_370_895.0,
            capital_actions=[{"date": "2024-10-18", "capital": 353_903_000, "nominal": 20}]))
        self.assertEqual(result["status"], "CONFLICT")


class AnnualRowTests(unittest.TestCase):
    def test_tenfold_row_count_is_classified_as_pre_split(self):
        result = recon.validate_annual(record(annual_rows=[{
            "exercice": 2025, "capitalSocial": 100_000_000,
            "capitalPropre": 500_000_000, "nombreTitres": 1_000_000,
            "chiffreAffaire": 800_000_000, "resultatExploitation": 120_000_000,
            "resultatNet": 100_000_000, "compteConsolide": True,
        }]))
        self.assertEqual(result["status"], "OK")
        self.assertIn("ANNUAL_ROW_COUNT_PRE_SPLIT_10X", result["notes"])

    def test_sothema_fivefold_case(self):
        result = recon.validate_annual(record(
            shares=38_309_500, nominal=10, price=321.9, cap=12_331_828_050.0,
            annual_rows=[{
                "exercice": 2025, "capitalSocial": 380_336_400,
                "capitalPropre": 2_649_675_000, "nombreTitres": 7_606_728,
                "chiffreAffaire": 3_225_670_000, "resultatExploitation": 626_524_000,
                "resultatNet": 385_526_000, "compteConsolide": True,
            }]))
        self.assertEqual(result["status"], "OK")
        self.assertIn("ANNUAL_ROW_COUNT_PRE_SPLIT_5X", result["notes"])

    def test_unexplained_row_count_is_quarantined(self):
        result = recon.validate_annual(record(annual_rows=[{
            "exercice": 2025, "capitalSocial": 80_000_000,
            "capitalPropre": 500_000_000, "nombreTitres": 8_000_000,
            "chiffreAffaire": 800_000_000, "resultatExploitation": 120_000_000,
            "resultatNet": 100_000_000, "compteConsolide": True,
        }]))
        self.assertEqual(result["status"], "SHARE_ROW_ANOMALY")
        self.assertIn("UNEXPLAINED_SHARE_DIFFERENCE", result["reasons"])

    def test_dated_capital_action_is_not_an_anomaly(self):
        result = recon.validate_annual(record(
            shares=12_000_000, cap=1_200_000_000.0,
            capital_actions=[{"date": "2026-03-01", "capital": 120_000_000}],
        ))
        self.assertEqual(result["status"], "OK")
        self.assertIn("DATED_BEFORE_LATER_CAPITAL_ACTION", result["reasons"])

    def test_stale_year_is_flagged(self):
        result = recon.validate_annual(record(annual_rows=[{
            "exercice": 2021, "capitalSocial": 100_000_000,
            "capitalPropre": 500_000_000, "nombreTitres": 10_000_000,
            "chiffreAffaire": 800_000_000, "resultatExploitation": 120_000_000,
            "resultatNet": 100_000_000, "compteConsolide": True,
        }]))
        self.assertEqual(result["status"], "STALE")


class ProposalTests(unittest.TestCase):
    def test_units_follow_application_contract(self):
        result = recon.propose(record())
        fields = result["fields"]
        self.assertEqual(fields["na"], 10_000_000)
        self.assertEqual(fields["net_profit"], 100.0)
        self.assertEqual(fields["revenue"], 800.0)
        self.assertEqual(fields["cp"], 500_000_000.0)
        self.assertEqual(fields["bpa"], 10.0)
        self.assertEqual(fields["roe"], 20.0)
        self.assertEqual(fields["profit_margin"], 12.5)

    def test_bank_marks_scope_warning(self):
        result = recon.propose(record(sector="Banques"))
        self.assertIn("BANK_PROFIT_GROUP_OVER_TOTAL_EQUITY", result["warnings"])
        self.assertEqual(result["review_class"], "BANK_REVIEW")
        self.assertIsNone(result["fields"]["profit_margin"])

    def test_consolidated_non_financial_is_auto_annual_candidate(self):
        result = recon.propose(record())
        self.assertEqual(result["review_class"], "AUTO_ANNUAL_CANDIDATE")

    def test_share_conflict_quarantines(self):
        result = recon.propose(record(cap=10_000_000_000.0))
        self.assertEqual(result["status"], "QUARANTINE")
        self.assertIn("CURRENT_SHARE_COUNT_CONFLICT", result["warnings"])

    def test_saved_comparison_and_report_shapes(self):
        report = recon.reconcile(
            [record()],
            companies=[{"name": "TEST COMPANY", "na": 9_000_000, "fiscal_year": 2024}],
        )
        self.assertEqual(report["summary"]["companies"], 1)
        row = report["companies"][0]
        self.assertEqual(row["saved"]["na"], 9_000_000)
        csv_rows = recon.to_csv_rows(report)
        self.assertEqual(csv_rows[0]["saved_shares"], 9_000_000)
        self.assertIn("Exchange reconciliation report", recon.to_markdown(report))


if __name__ == "__main__":
    unittest.main()

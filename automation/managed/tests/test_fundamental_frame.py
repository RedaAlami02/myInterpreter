import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "cloud_function/functions/onboard_company/src"))
import fundamental_frame as frame
import main as legacy  # noqa: E402  (archival pure helpers, parity reference)

# The archival module imports the retired SDK; do not leak it into other suites.
for _name in [
    name
    for name in sys.modules
    if name in {"main", "sources"} or name == "appwrite" or name.startswith("appwrite.")
]:
    del sys.modules[_name]
del _name


def payload(values):
    return {"data": values}


def tables(**overrides):
    value = {
        "rnpg": payload({"2022": 10, "2023": 20, "2024": 0, "2025p": 30}),
        "fp": payload({"2022": 100, "2023": 120, "2024": 130}),
        "ca": payload(
            {"2019": 100, "2020": 110, "2021": 120, "2022": 130, "2023": 140, "2024": 150}
        ),
        "ebe": payload({"2023": 60}),
        "ebit": payload({"2023": 50}),
        "dn": payload({"2023": 40}),
        "tn": payload({"2023": 5}),
        "fcf": payload({"2023": 25}),
        "actif": payload({"2023": 900}),
        "dpa": payload({"2023": 0}),
        "nmt": payload({"2023": 1000000, "2024": 1100000, "2025p": 1200000}),
        "beta": payload({"Béta 3 ans": 0.8, "Béta 5 ans": 0.9}),
        "desc": payload({"description": "  Fixture description  "}),
        "holders": payload(
            [
                {"Shareholder": "Holder", "Percentage": 0.51},
                {"Shareholder": "Empty", "Percentage": 0},
            ]
        ),
    }
    value.update(overrides)
    return value


def financial(bpa=None, dpa=None):
    return {
        "financialData": {
            "beneficeParAction": bpa or {},
            "dividendeParAction": dpa or {},
        }
    }


def derive(selected=None, fin=None, stock=None, symlinks=None):
    return frame.derive(
        "AAA",
        stock if stock is not None else {"name": "Alpha SA"},
        symlinks if symlinks is not None else [
            {"symbol": "AAA", "name": "Alpha SA", "type": "Banks"}
        ],
        fin if fin is not None else financial(),
        selected or tables(),
    )


class ParityTests(unittest.TestCase):
    def test_helper_rules_match_the_archival_enrichment(self):
        selected = tables()
        self.assertEqual(
            frame.reported_years(selected["rnpg"], selected["fp"]),
            legacy._reported_years(selected["rnpg"], selected["fp"]),
        )
        self.assertEqual(
            frame.consistent_year(selected["rnpg"], selected["fp"], selected["ca"]),
            legacy._consistent_year(selected["rnpg"], selected["fp"], selected["ca"]),
        )
        self.assertEqual(
            frame.projected_profit(selected["rnpg"]),
            legacy._projected_profit(selected["rnpg"]),
        )
        self.assertEqual(
            frame.shares_now(selected["nmt"]), legacy._shares_now(selected["nmt"])
        )
        self.assertEqual(
            frame.cagr(selected["ca"], 5), legacy._cagr(selected["ca"], 5)
        )
        self.assertEqual(
            frame.latest(selected["ca"]), legacy._latest(selected["ca"])
        )
        self.assertEqual(
            frame.series(selected["ca"]), legacy._series(selected["ca"])
        )

    def test_helper_rules_match_on_degenerate_payloads(self):
        cases = [
            payload(None),
            payload({}),
            payload({"2024": 0, "2025p": 0}),
            payload({"2024": "12.5", "2023": None, "2022": True}),
        ]
        for case in cases:
            self.assertEqual(frame.reported_years(case), legacy._reported_years(case))
            self.assertEqual(frame.projected_profit(case), legacy._projected_profit(case))
            self.assertEqual(frame.shares_now(case), legacy._shares_now(case))
            self.assertEqual(frame.cagr(case, 5), legacy._cagr(case, 5))
            self.assertEqual(frame.latest(case), legacy._latest(case))
            self.assertEqual(
                frame.latest(case, allow_projected=True),
                legacy._latest(case, allow_projected=True),
            )


class DeriveTests(unittest.TestCase):
    def test_one_fiscal_year_pins_every_reported_figure(self):
        computed = derive()["computed"]
        self.assertEqual(computed["fiscal_year"], 2023)
        self.assertEqual(
            (computed["net_profit"], computed["revenue"], computed["roe"]),
            (20.0, 140.0, 16.67),
        )
        self.assertEqual(computed["cp"], 120000000.0)
        self.assertEqual(computed["profit_margin"], 14.29)
        self.assertEqual(
            (computed["ebitda"], computed["ebit"], computed["net_debt"],
             computed["net_cash"], computed["fcf"], computed["total_assets"]),
            (60.0, 50.0, 40.0, 5.0, 25.0, 900.0),
        )
        self.assertEqual(computed["rev_growth_5y"], 8.45)
        self.assertEqual(computed["na"], 1200000.0)
        self.assertEqual(computed["bpa"], 16.67)
        self.assertEqual(computed["fy_est"], 2025)
        self.assertEqual(computed["rnpg_est"], 30.0)
        self.assertFalse(any(
            isinstance(value, float) and (value != value) for value in computed.values()
        ))

    def test_projection_never_becomes_a_reported_figure_or_vice_versa(self):
        computed = derive()["computed"]
        self.assertEqual(computed["revenue"], 140.0)  # 2023 reported, not 2024/2025p
        self.assertEqual(computed["net_profit"], 20.0)  # not the projected 30
        projected = dict(
            tables(), rnpg=payload({"2022": 10, "2023": 20, "2024": 25, "2024p": 90})
        )
        value = derive(projected)["computed"]
        # A projection that is not newer than the reported year tells us nothing.
        self.assertEqual((value["fiscal_year"], value["fy_est"]), (2024, None))
        self.assertEqual(value["net_profit"], 25.0)

    def test_shares_are_current_and_split_aware(self):
        computed = derive()["computed"]
        self.assertEqual(computed["na"], 1200000.0)  # 2025p, not the 2023 count
        split = tables(nmt=payload({"2024": 11864676, "2025p": 118646760}))
        self.assertEqual(derive(split)["computed"]["na"], 118646760.0)

    def test_fallback_per_share_values_are_used_only_when_missing(self):
        computed = derive(fin=financial(
            bpa={"2023": 1.5, "2022": 1.2}, dpa={"2023": 0.5}
        ))["computed"]
        self.assertEqual(computed["bpa"], 16.67)  # derived from profit/shares
        # A literal zero in the dpa table is a real dividend value and is kept.
        self.assertEqual(computed["dpa"], 0.0)
        no_dpa = derive(tables(dpa=payload({})), financial(dpa={"2023": 0.5}))
        self.assertEqual(no_dpa["computed"]["dpa"], 0.5)
        no_shares = tables(nmt=payload({}))
        computed = derive(no_shares, financial(bpa={"2023": 1.5}))["computed"]
        self.assertEqual(computed["bpa"], 1.5)

    def test_degenerate_tables_leave_fields_unknown_instead_of_guessed(self):
        empty = {kind: payload(None) for kind in tables()}
        result = derive(empty)
        computed = result["computed"]
        self.assertIsNone(computed["fiscal_year"])
        self.assertIsNone(computed["fy_est"])
        self.assertIsNone(computed["net_profit"])
        self.assertIsNone(computed["bpa"])
        self.assertIsNone(computed["cp"])
        self.assertEqual(result["ext_name"], "Alpha SA")

    def test_profile_text_and_holders_are_preserved_without_placeholders(self):
        result = derive()
        self.assertEqual(result["description"], "Fixture description")
        self.assertEqual(result["sector"], "Banks")
        self.assertEqual(
            json.loads(result["computed"]["shareholders"]),
            [{"name": "Holder", "pct": 51.0}],
        )
        self.assertEqual(result["computed"]["beta_3y"], 0.8)
        self.assertEqual(result["computed"]["beta_5y"], 0.9)
        no_description = tables(desc=payload({"description": "   "}))
        self.assertIsNone(derive(no_description)["description"])
        no_holders = tables(holders=payload([]))
        self.assertIsNone(derive(no_holders)["computed"]["shareholders"])

    def test_missing_registered_identity_is_refused(self):
        with self.assertRaisesRegex(ValueError, "SYMBOL_NOT_IN_SOURCE_REGISTRY"):
            frame.derive("AAA", {}, [], financial(), tables())
        with self.assertRaisesRegex(ValueError, "SYMBOL_NOT_IN_SOURCE_REGISTRY"):
            frame.derive("AAA", {"name": None}, [{"symbol": "OTHER"}], {}, tables())


if __name__ == "__main__":
    unittest.main()

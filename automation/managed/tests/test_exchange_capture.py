import json
import sys
import unittest
from pathlib import Path
import base64

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import capture_exchange_pages as capture
import apply_reconciliation_cloud as apply_cloud
import cloud_auth


def settings_page(payload):
    return ("<html><script type=\"application/json\" "
            "data-drupal-selector=\"drupal-settings-json\">"
            + json.dumps(payload) + "</script></html>")


class CaptureParserTests(unittest.TestCase):
    def test_actions_and_instrument(self):
        actions_html = settings_page({"live_market": {"actions": [
            {"symbol": "TST", "ce": "TST010101"}]}})
        self.assertEqual(capture.actions(actions_html)[0]["symbol"], "TST")
        detail = settings_page({"live_market": {"action_data": {
            "symbol": "TST", "ce": "TST010101",
            "emetteur": {"fr": "TEST COMPANY"}, "secteur": {"fr": "Industrie"},
            "dernierCours": 10, "capitalisation": 1000000,
            "instrument_details": {"isin": "MA0000000000", "shares_count": 100000,
                                   "nominal_value": 10},
            "financials_details": {"chiffres": [{"exercice": 2025}],
                                   "ratios": []},
            "capital_increase_details": [], "dividend_details": [],
        }}})
        record = capture.instrument(detail, 200, "a" * 64)
        self.assertEqual(record["symbol"], "TST")
        self.assertEqual(record["shares"], 100000)
        self.assertEqual(record["annual_rows"][0]["exercice"], 2025)
        self.assertEqual(record["page_sha256"], "a" * 64)

    def test_summary_counts(self):
        rows = [{"annual_rows": [{"exercice": 2025}], "capital_actions": [1],
                 "dividends": []}, {"annual_rows": [], "capital_actions": [],
                                    "dividends": [1]}, {"error": "X"}]
        result = capture.summary(rows)
        self.assertEqual(result["requested"], 3)
        self.assertEqual(result["ok"], 2)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["with_annual_rows"], 1)
        self.assertEqual(result["without_annual_rows"], 1)
        self.assertEqual(result["latest_year_counts"], {"2025": 1})


class ServiceKeyTests(unittest.TestCase):
    def test_new_secret_key_is_apikey_only(self):
        headers = cloud_auth.service_headers("sb_secret_example")
        self.assertEqual(headers, {"apikey": "sb_secret_example"})

    def test_legacy_service_role_jwt_gets_bearer(self):
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"role": "service_role"}).encode()).rstrip(b"=").decode()
        key = header + "." + payload + ".signature"
        headers = cloud_auth.service_headers(key)
        self.assertEqual(headers["apikey"], key)
        self.assertEqual(headers["Authorization"], "Bearer " + key)

    def test_publishable_and_anon_are_rejected(self):
        with self.assertRaises(cloud_auth.ServiceKeyError):
            cloud_auth.service_headers("sb_publishable_example")
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        anon = header + "." + base64.urlsafe_b64encode(
            json.dumps({"role": "anon"}).encode()).rstrip(b"=").decode() + ".signature"
        with self.assertRaises(cloud_auth.ServiceKeyError):
            cloud_auth.service_headers(anon)

    def test_junk_is_rejected(self):
        with self.assertRaises(cloud_auth.ServiceKeyError):
            cloud_auth.service_headers("not-a-key")


class CloudEligibilityTests(unittest.TestCase):
    def test_share_changes_and_annual_candidates(self):
        report = {"companies": [
            {"status": "ANNUAL_REVIEW", "review_class": "AUTO_ANNUAL_CANDIDATE",
             "current_shares": {"status": "VERIFIED"},
             "proposed_fields": {"na": 120, "fiscal_year": 2025},
             "saved": {"na": 100}},
            {"status": "ANNUAL_REVIEW", "review_class": "AUTO_ANNUAL_CANDIDATE",
             "current_shares": {"status": "VERIFIED"},
             "proposed_fields": {"na": 100, "fiscal_year": 2025},
             "saved": {"na": 100}},
            {"status": "QUARANTINE", "review_class": "CONFLICT",
             "current_shares": {"status": "CONFLICT"},
             "proposed_fields": {"na": 99, "fiscal_year": 2025},
             "saved": {"na": 99}},
        ]}
        shares, changes, annual = apply_cloud.eligible(report)
        self.assertEqual(shares, 2)
        self.assertEqual(changes, 1)
        self.assertEqual(annual, 2)


if __name__ == "__main__":
    unittest.main()

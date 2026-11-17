from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_database_privacy import verify_api_access

CONFIG = {
    "SUPABASE_PROJECT_URL": "https://abcdefghijklmnopqrst.supabase.co",
    "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_fixture_only",
}


def opener(statuses, calls):
    @contextmanager
    def get(request, timeout):
        calls.append(request)
        code = statuses[len(calls) - 1]
        if code >= 400:
            raise HTTPError("https://example.invalid", code, "fixture", {}, None)

        class Response:
            status = code

        yield Response()

    return get


class DatabasePrivacyVerifierTests(unittest.TestCase):
    def test_unregistered_key_never_counts_as_privacy_success(self):
        calls = []
        result = verify_api_access(CONFIG, ["company"], opener([401], calls))
        self.assertFalse(result["api_privacy_verified"])
        self.assertEqual(result["api_check_blocker"], "API_KEY_REJECTED")
        self.assertEqual(result["anonymous_api_checks"], [])
        self.assertEqual(len(calls), 1)

    def test_valid_key_and_actual_denial_can_verify_privacy(self):
        calls = []
        result = verify_api_access(
            CONFIG, ["company", "data"], opener([200, 401, 403, 406, 406], calls)
        )
        self.assertTrue(result["api_privacy_verified"])
        self.assertEqual(len(calls), 5)

    def test_anonymous_read_is_failure_even_when_key_valid(self):
        calls = []
        result = verify_api_access(CONFIG, ["company"], opener([200, 200, 406, 406], calls))
        self.assertFalse(result["api_privacy_verified"])

    def test_server_outage_is_unknown_not_successful_denial(self):
        calls = []
        result = verify_api_access(CONFIG, ["company"], opener([503], calls))
        self.assertFalse(result["api_privacy_verified"])
        self.assertEqual(result["api_check_blocker"], "API_UNAVAILABLE")

    def test_exposed_internal_schema_fails_verification(self):
        calls = []
        result = verify_api_access(CONFIG, ["company"], opener([200, 401, 200], calls))
        self.assertFalse(result["api_privacy_verified"])
        self.assertFalse(result["internal_schemas_not_exposed"])


if __name__ == "__main__":
    unittest.main()

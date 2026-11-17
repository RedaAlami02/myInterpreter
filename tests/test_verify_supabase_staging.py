import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("verify_supabase_staging", TOOLS / "verify_supabase_staging.py")
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class VerificationTests(unittest.TestCase):
    def test_jsonb_number_and_key_formatting_is_semantically_equal(self):
        self.assertEqual(VERIFY.fingerprint({"b": [1e20, -0.0, 2.5], "a": 1}),
                         VERIFY.fingerprint({"a": 1.0, "b": [10**20, 0, 2.5]}))
        self.assertNotEqual(VERIFY.fingerprint({"value": True}),
                            VERIFY.fingerprint({"value": 1}))
        self.assertNotEqual(VERIFY.fingerprint({"value": "1"}),
                            VERIFY.fingerprint({"value": 1}))
        self.assertNotEqual(VERIFY.fingerprint({"value": 10**30 + 1}),
                            VERIFY.fingerprint({"value": 10**30}))

    def test_changed_payload_missing_and_duplicate_rows_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "response.json"
            source = {"value": 123.45, "$permissions": ['read("user:original")']}
            path.write_text(json.dumps(source))
            from stage_supabase import Dataset, sha256
            dataset = Dataset("fixture", "fixture", path, sha256(path), path.stat().st_size, 1)
            self.assertEqual(VERIFY.compare_payloads(dataset, [("response", source)]), 1)
            for rows in ([], [("response", dict(source, value=123.46))],
                         [("response", dict(source, **{"$permissions": []}))],
                         [("response", source), ("response", source)]):
                with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                    VERIFY.compare_payloads(dataset, rows)


if __name__ == "__main__":
    unittest.main()

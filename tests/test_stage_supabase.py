import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "stage_supabase", Path(__file__).resolve().parents[1] / "tools/stage_supabase.py")
STAGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = STAGE
SPEC.loader.exec_module(STAGE)


class StageTests(unittest.TestCase):
    def test_pooler_must_match_project_reference_and_keep_tls(self):
        reference = "abcdefghijklmnopqrst"
        config = {
            "SUPABASE_PROJECT_URL": f"https://{reference}.supabase.co",
            "SUPABASE_DATABASE_URL": f"postgresql://postgres.{reference}:fixture@aws-0-eu-central-1.pooler.supabase.com:5432/postgres",
        }
        self.assertEqual(STAGE.connection_options(config)["sslmode"], "require")
        mismatch = dict(config)
        mismatch["SUPABASE_PROJECT_URL"] = "https://zyxwvutsrqponmlkjihg.supabase.co"
        with self.assertRaises(ValueError):
            STAGE.connection_options(mismatch)
        no_tls = dict(config)
        no_tls["SUPABASE_DATABASE_URL"] += "?sslmode=disable"
        with self.assertRaises(ValueError):
            STAGE.connection_options(no_tls)
        api_path = dict(config)
        api_path["SUPABASE_PROJECT_URL"] += "/rest/v1"
        with self.assertRaises(ValueError):
            STAGE.connection_options(api_path)

    def test_unrelated_database_host_is_rejected(self):
        with self.assertRaises(ValueError):
            STAGE.connection_options({
                "SUPABASE_PROJECT_URL": "https://abcdefghijklmnopqrst.supabase.co",
                "SUPABASE_DATABASE_URL": "postgresql://postgres:fixture@example.invalid/postgres"})

    def test_config_is_parsed_as_data_without_shell_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "credentials.env"
            p.write_text("SUPABASE_SECRET_KEY='literal$(not-a-command)#value'\n")
            self.assertEqual(STAGE.local_config(p)["SUPABASE_SECRET_KEY"],
                             "literal$(not-a-command)#value")

    def test_import_preserves_legacy_permissions_and_rejects_missing_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "data.json"
            row = {"$id": "original-id", "$collectionId": "data", "$databaseId": "myinterpreter",
                   "$permissions": ['read("any")'], "pa": 123.45, "volume": None}
            p.write_text(json.dumps([row]))
            dataset = STAGE.Dataset("legacy/data", "fixture", p, STAGE.sha256(p),
                                    p.stat().st_size, 1, "data")
            self.assertEqual(STAGE.verify(dataset), 1)
            self.assertEqual(list(STAGE.records(dataset)), [row])
            del row["$permissions"]
            with self.assertRaises(ValueError):
                STAGE.record_id(dataset, row)

    def test_changed_source_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "response.json"
            p.write_text('{"value":1}')
            dataset = STAGE.Dataset("fresh/fixture", "fixture", p, STAGE.sha256(p), p.stat().st_size, 1)
            p.write_text('{"value":2}')
            with self.assertRaises(ValueError):
                STAGE.verify(dataset)

    def test_nonfinite_numbers_are_rejected(self):
        with self.assertRaises(ValueError):
            STAGE.decode('{"price":NaN}')


if __name__ == "__main__":
    unittest.main()

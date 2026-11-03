import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
spec = importlib.util.spec_from_file_location("flutter_config",ROOT/"tools/write_flutter_build_config.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FlutterBuildConfigTests(unittest.TestCase):
    def test_market_preview_requires_an_explicit_strict_boolean_define(self):
        config = {"SUPABASE_PROJECT_URL":"https://abcdefghijklmnopqrst.supabase.co",
                  "SUPABASE_PUBLISHABLE_KEY":"sb_publishable_fixture"}
        for setting in ('true','false'):
            values=module.public_config({**config,'MYINTERPRETER_MARKET_PREVIEW':setting})
            self.assertEqual(values['MYINTERPRETER_MARKET_PREVIEW'],setting)
        for setting in ('1','TRUE',True):
            with self.assertRaises(ValueError):
                module.public_config({**config,'MYINTERPRETER_MARKET_PREVIEW':setting})

    def test_recurring_reader_requires_strict_explicit_flag(self):
        config={'SUPABASE_PROJECT_URL':'https://abcdefghijklmnopqrst.supabase.co',
                'SUPABASE_PUBLISHABLE_KEY':'sb_publishable_fixture'}
        self.assertNotIn('MYINTERPRETER_RECURRING_FEED',module.public_config(config))
        self.assertEqual(module.public_config({**config,'MYINTERPRETER_RECURRING_FEED':'true'})['MYINTERPRETER_RECURRING_FEED'],'true')
        with self.assertRaises(ValueError):module.public_config({**config,'MYINTERPRETER_RECURRING_FEED':'TRUE'})

    def test_mobile_callbacks_are_explicit_build_configuration(self):
        config = {'SUPABASE_PROJECT_URL':'https://abcdefghijklmnopqrst.supabase.co',
                  'SUPABASE_PUBLISHABLE_KEY':'sb_publishable_fixture'}
        self.assertNotIn('MYINTERPRETER_MOBILE_AUTH_LINKS',module.public_config(config))
        for value in ('true','false'):
            self.assertEqual(module.public_config({**config,'MYINTERPRETER_MOBILE_AUTH_LINKS':value})[
                'MYINTERPRETER_MOBILE_AUTH_LINKS'],value)
        for value in ('1','TRUE',True):
            with self.assertRaises(ValueError):module.public_config({**config,'MYINTERPRETER_MOBILE_AUTH_LINKS':value})

    def test_only_public_fields_are_written_and_file_is_private(self):
        config = {"SUPABASE_PROJECT_URL":"https://abcdefghijklmnopqrst.supabase.co",
                  "SUPABASE_PUBLISHABLE_KEY":"sb_publishable_fixture_only",
                  "SUPABASE_SECRET_KEY":"sb_secret_fixture_never_written",
                  "SUPABASE_DATABASE_URL":"fixture-private-database"}
        values = module.public_config(config)
        self.assertEqual(set(values),{"MYINTERPRETER_BACKEND","SUPABASE_PROJECT_URL","SUPABASE_PUBLISHABLE_KEY"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"client.json"
            module.write_config(path,values)
            self.assertEqual(json.loads(path.read_text()),values)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertNotIn("sb_secret_",path.read_text())

    def test_secret_key_and_nonproject_urls_are_rejected(self):
        for url,key in [("https://abcdefghijklmnopqrst.supabase.co","sb_secret_fixture"),
                        ("https://example.invalid","sb_publishable_fixture"),
                        ("https://abcdefghijklmnopqrst.supabase.co/rest/v1","sb_publishable_fixture")]:
            with self.assertRaises(ValueError):
                module.public_config({"SUPABASE_PROJECT_URL":url,"SUPABASE_PUBLISHABLE_KEY":key})

    def test_retired_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            module.public_config({},"appwrite")

    def test_ci_mode_needs_no_python_site_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable,"-S",str(ROOT/"tools/write_flutter_build_config.py"),
                "--from-env","--backend","supabase","--output",str(Path(directory)/"client.json")],
                capture_output=True,text=True,env={"PATH":__import__("os").environ["PATH"],"SUPABASE_PROJECT_URL":"https://abcdefghijklmnopqrst.supabase.co","SUPABASE_PUBLISHABLE_KEY":"sb_publishable_fixture","MYINTERPRETER_MOBILE_AUTH_LINKS":"true"})
            self.assertEqual(result.returncode,0)
            self.assertTrue(json.loads(result.stdout)["written"])
            self.assertEqual(json.loads((Path(directory)/"client.json").read_text())["MYINTERPRETER_MOBILE_AUTH_LINKS"],"true")


if __name__ == "__main__":
    unittest.main()

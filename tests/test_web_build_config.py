import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from write_web_build_config import write_web_config


class WebBuildConfigTests(unittest.TestCase):
    def test_public_refresh_preserves_explicit_disabled_valuation_gate(self):
        config = {'SUPABASE_PROJECT_URL':'https://abcdefghijklmnopqrst.supabase.co',
                  'SUPABASE_PUBLISHABLE_KEY':'sb_publishable_fixture'}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'runtime.php';write_web_config(config,path)
            path.write_text(path.read_text().replace("'admin_user_id' => ''", "'admin_user_id' => '',\n  'portfolio_valuation' => false"))
            write_web_config(config,path,refresh_public=True)
            values=json.loads(subprocess.run(['php','-r','echo json_encode(require $argv[1]);',str(path)],
                              capture_output=True,text=True,check=True).stdout)
            self.assertIs(values['portfolio_valuation'],False)

    def test_public_key_refresh_preserves_explicit_market_preview_setting(self):
        config = {'SUPABASE_PROJECT_URL':'https://abcdefghijklmnopqrst.supabase.co',
                  'SUPABASE_PUBLISHABLE_KEY':'sb_publishable_before'}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'runtime.php';write_web_config(config,path)
            path.write_text(path.read_text().replace("'admin_user_id' => ''", "'admin_user_id' => '',\n  'market_preview' => true"))
            config['SUPABASE_PUBLISHABLE_KEY']='sb_publishable_after'
            write_web_config(config,path,refresh_public=True)
            values=json.loads(subprocess.run(['php','-r','echo json_encode(require $argv[1]);',str(path)],
                              capture_output=True,text=True,check=True).stdout)
            self.assertIs(values['market_preview'],True)
            self.assertEqual(values['publishable_key'],'sb_publishable_after')

    def test_public_fields_only_and_loadable_by_php(self):
        config = {
            "SUPABASE_PROJECT_URL": "https://abcdefghijklmnopqrst.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_fixture",
            "SUPABASE_SECRET_KEY": "sb_secret_do_not_ship",
            "SUPABASE_DATABASE_URL": "private-database-password",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.php"
            self.assertTrue(write_web_config(config, path))
            result = subprocess.run(
                ["php", "-r", "echo json_encode(require $argv[1]);", str(path)],
                capture_output=True,
                text=True,
                check=True,
            )
            values = json.loads(result.stdout)
            self.assertEqual(set(values), {"backend", "url", "publishable_key", "admin_user_id", "public_url"})
            self.assertEqual(values["backend"], "supabase")
            self.assertNotIn("sb_secret_", path.read_text())
            self.assertNotIn("private-database-password", path.read_text())

    def test_refresh_upgrades_old_config_and_preserves_explicit_public_destination(self):
        config = {'SUPABASE_PROJECT_URL':'https://abcdefghijklmnopqrst.supabase.co',
                  'SUPABASE_PUBLISHABLE_KEY':'sb_publishable_fixture'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'runtime.php'
            path.write_text("<?php return ['backend'=>'supabase','url'=>'https://abcdefghijklmnopqrst.supabase.co',"
                            "'publishable_key'=>'sb_publishable_old','admin_user_id'=>'fixture-owner'];")
            write_web_config(config,path,refresh_public=True)
            config['MYINTERPRETER_PUBLIC_URL']='https://example.invalid/application'
            write_web_config(config,path,refresh_public=True)
            del config['MYINTERPRETER_PUBLIC_URL']
            write_web_config(config,path,refresh_public=True)
            values=json.loads(subprocess.check_output(['php','-r','echo json_encode(require $argv[1]);',str(path)]))
            self.assertEqual(values['admin_user_id'],'fixture-owner')
            self.assertEqual(values['public_url'],'https://example.invalid/application')

    def test_invalid_public_url_cannot_replace_existing_config(self):
        config = {'SUPABASE_PROJECT_URL':'https://abcdefghijklmnopqrst.supabase.co',
                  'SUPABASE_PUBLISHABLE_KEY':'sb_publishable_fixture'}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'runtime.php';write_web_config(config,path)
            before=path.read_bytes()
            config['MYINTERPRETER_PUBLIC_URL']='http://localhost:3000'
            with self.assertRaises(subprocess.CalledProcessError):write_web_config(config,path,refresh_public=True)
            self.assertEqual(path.read_bytes(),before)

    def test_existing_configuration_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.php"
            path.write_bytes(b"fixture administrator configuration")
            self.assertFalse(write_web_config({}, path))
            self.assertEqual(path.read_bytes(), b"fixture administrator configuration")

    def test_elevated_key_cannot_be_used_as_public_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.php"
            with self.assertRaises(ValueError):
                write_web_config(
                    {
                        "SUPABASE_PROJECT_URL": "https://abcdefghijklmnopqrst.supabase.co",
                        "SUPABASE_PUBLISHABLE_KEY": "sb_secret_private",
                    },
                    path,
                )
            self.assertFalse(path.exists())

    def test_explicit_public_refresh_preserves_administrator(self):
        config = {
            "SUPABASE_PROJECT_URL": "https://abcdefghijklmnopqrst.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_before",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.php"
            write_web_config(config, path)
            text = path.read_text().replace(
                "'admin_user_id' => ''", "'admin_user_id' => 'fixture-admin'"
            )
            path.write_text(text)
            config["SUPABASE_PUBLISHABLE_KEY"] = "sb_publishable_after"
            self.assertTrue(write_web_config(config, path, refresh_public=True))
            result = subprocess.run(
                ["php", "-r", "echo json_encode(require $argv[1]);", str(path)],
                capture_output=True,
                text=True,
                check=True,
            )
            values = json.loads(result.stdout)
            self.assertEqual(values["publishable_key"], "sb_publishable_after")
            self.assertEqual(values["admin_user_id"], "fixture-admin")
            self.assertNotIn("sb_publishable_before", path.read_text())

    def test_public_refresh_refuses_project_change(self):
        config = {
            "SUPABASE_PROJECT_URL": "https://abcdefghijklmnopqrst.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_fixture",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.php"
            write_web_config(config, path)
            before = path.read_bytes()
            config["SUPABASE_PROJECT_URL"] = "https://differentprojectref.supabase.co"
            with self.assertRaises(ValueError):
                write_web_config(config, path, refresh_public=True)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

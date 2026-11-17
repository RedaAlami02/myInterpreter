import importlib.util
import unittest
import contextlib
import io
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).resolve().parents[1] / 'deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeployTests(unittest.TestCase):
    def test_help_and_unknown_options_never_load_credentials_or_connect(self):
        for args,code in [(['--help'],0),(['--dry-rnu'],2)]:
            with patch.object(deploy,'credentials') as credentials, patch.object(deploy.ftplib,'FTP_TLS') as ftp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:deploy.main(args)
                self.assertEqual(raised.exception.code,code)
                credentials.assert_not_called();ftp.assert_not_called()

    def test_dry_run_never_loads_credentials_or_connects(self):
        with patch.object(deploy,'credentials') as credentials, patch.object(deploy.ftplib,'FTP_TLS') as ftp, contextlib.redirect_stdout(io.StringIO()):
            deploy.main(['--dry-run','index.php'])
            credentials.assert_not_called();ftp.assert_not_called()

    def test_runtime_manifest(self):
        with patch.object(deploy.subprocess, 'check_output', return_value=b'index.php\0locales/en.json\0tests/i18n_test.php\0config/sources.example.php\0design-review/private.png\0migrations/supabase/market_contract.json\0migrations/supabase/supplemental_contract.json\0migrations/supabase/003_private_portfolio.sql\0'):
            files = deploy.local_files([])
        self.assertIn('locales/en.json', files)
        self.assertIn('index.php', files)
        self.assertNotIn('tests/i18n_test.php', files)
        self.assertNotIn('config/sources.example.php', files)
        self.assertNotIn('design-review/private.png', files)
        self.assertIn('migrations/supabase/market_contract.json', files)
        self.assertIn('migrations/supabase/supplemental_contract.json', files)
        self.assertNotIn('migrations/supabase/003_private_portfolio.sql', files)
        self.assertIn('config/supabase.local.php', files)
        self.assertIn('auth_callback.php', files)
        self.assertIn('auth_reset.php', files)
        self.assertIn('core/ShadowMarketFeed.php', files)
        self.assertIn('core/market_preview_panel.php', files)
        self.assertIn('assets/js/market_preview.js', files)
        self.assertIn('assets/css/market_preview.css', files)
        self.assertTrue(deploy.RUNTIME_DEPENDENCIES.issubset(files))
        self.assertLess(files.index('locales/en.json'), files.index('index.php'))

    def test_explicit_escape_rejected(self):
        for path in ['../private.php', '/tmp/private.php']:
            with self.assertRaises(SystemExit):
                deploy.local_files([path])

    def test_explicit_upload_obeys_publication_boundary(self):
        for path in ['config/secrets.php', 'private/notes.php',
                     'config/database.php', 'migrations/supabase/003_private_portfolio.sql',
                     '.supabase-migration.env', 'tests/supabase_app_test.php']:
            self.assertFalse(deploy.runtime_path(path))
        with self.assertRaises(SystemExit):
            deploy.local_files(['tests/supabase_app_test.php'])
        for path in ['index.php', 'core/backend.php', 'config/supabase.local.php',
                     'config/sources.php', 'locales/en.json']:
            self.assertTrue(deploy.runtime_path(path))


if __name__ == '__main__':
    unittest.main()

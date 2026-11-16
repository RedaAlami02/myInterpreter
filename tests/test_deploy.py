import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).resolve().parents[1] / 'deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeployTests(unittest.TestCase):
    def test_runtime_manifest(self):
        with patch.object(deploy.subprocess, 'check_output', return_value=b'index.php\0locales/en.json\0tests/i18n_test.php\0config/sources.example.php\0design-review/private.png\0'):
            files = deploy.local_files([])
        self.assertIn('locales/en.json', files)
        self.assertIn('index.php', files)
        self.assertNotIn('tests/i18n_test.php', files)
        self.assertNotIn('config/sources.example.php', files)
        self.assertNotIn('design-review/private.png', files)
        self.assertLess(files.index('locales/en.json'), files.index('index.php'))

    def test_explicit_escape_rejected(self):
        for path in ['../private.php', '/tmp/private.php']:
            with self.assertRaises(SystemExit):
                deploy.local_files([path])


if __name__ == '__main__':
    unittest.main()

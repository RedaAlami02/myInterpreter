"""The website cutover must not start a market capture on a user page load."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DirectSourceGateTests(unittest.TestCase):
    def php(self, body):
        environment = dict(os.environ)
        environment.pop('MYINTERPRETER_DIRECT_SOURCE_REQUESTS', None)
        result = subprocess.run(['php', '-n', '-d', 'session.save_path=/tmp', '-r', body], cwd=ROOT,
                                env=environment, capture_output=True, text=True, check=True)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def test_default_backend_disables_direct_collection(self):
        self.assertEqual(self.php("require 'core/backend.php'; echo json_encode(MYINTERPRETER_DIRECT_SOURCE_REQUESTS);"), 'false')

    def test_nonempty_batch_cannot_reach_network_without_explicit_gate(self):
        # php -n has no curl extension; reaching the network path would fail.
        self.assertEqual(self.php("require 'handlers/market_proxy.php'; echo json_encode(mkt_batch(['x'=>['url'=>'https://example.invalid']]));"), '[]')

    def test_direct_endpoint_fails_before_capture(self):
        result = self.php("$_SERVER['SCRIPT_FILENAME']=getcwd().'/handlers/market_proxy.php'; $_SERVER['SCRIPT_NAME']='/handlers/market_proxy.php'; $_GET['symbol']='TEST'; require 'handlers/market_proxy.php';")
        self.assertEqual(json.loads(result), {'error':'Market enrichment is unavailable.'})


if __name__ == '__main__':
    unittest.main()

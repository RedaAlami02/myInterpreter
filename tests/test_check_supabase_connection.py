import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
try:
    SPEC = importlib.util.spec_from_file_location("check_connection", ROOT / "tools/check_supabase_connection.py")
    CHECK = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(CHECK)
finally:
    sys.path.pop(0)


class ConnectionCheckTests(unittest.TestCase):
    def run_check(self, secret):
        config = {"SUPABASE_PROJECT_URL": "https://abcdefghijklmnopqrst.supabase.co",
                  "SUPABASE_DATABASE_URL": "fixture-only-database-uri",
                  "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_fixture_only",
                  "SUPABASE_SECRET_KEY": secret}
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.pgconn.ssl_in_use = True
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        cursor.fetchone.side_effect = [(1, "on"), (10000000,), (True,)]
        connection.cursor.return_value = cursor
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.status_code = 200
        with patch.object(CHECK, "local_config", return_value=config), \
                patch.object(CHECK, "connection_options", return_value={}), \
                patch.object(CHECK.psycopg, "connect", return_value=connection), \
                patch.object(CHECK.requests, "get", return_value=response) as get:
            result = CHECK.check()
        return result, config, cursor, get

    def test_valid_check_is_read_only_and_never_returns_credentials(self):
        result, config, cursor, get = self.run_check("sb_secret_fixture_only")
        self.assertTrue(result["ok"])
        self.assertEqual(cursor.execute.call_args_list[0].args, ("SET TRANSACTION READ ONLY",))
        self.assertEqual(get.call_count, 2)
        output = json.dumps(result)
        for value in config.values():
            self.assertNotIn(value, output)

    def test_publishable_key_cannot_pass_as_server_secret(self):
        result, _, _, get = self.run_check("sb_publishable_wrong_key_kind")
        self.assertFalse(result["ok"])
        self.assertFalse(result["api"]["secret"]["key_kind_matches_field"])
        self.assertEqual(get.call_count, 1)


if __name__ == "__main__":
    unittest.main()

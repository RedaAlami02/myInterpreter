import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_collection


class CollectionEntryTests(unittest.TestCase):
    def test_quote_dispatch_never_calls_legacy_or_depth_collector(self):
        with patch("market_collect.main", return_value=2) as market, patch("depth_collect.main") as depth:
            self.assertEqual(run_collection.main(["quotes"]), 2)
        market.assert_called_once_with([])
        depth.assert_not_called()

    def test_depth_dispatch_preserves_store_and_config_without_shell_interpolation(self):
        with patch("depth_collect.main", return_value=0) as depth, patch("market_collect.main") as market:
            self.assertEqual(run_collection.main([
                "depth", "--config", "/private/a recipe.json", "--isolated-store", "/tmp/local.sqlite",
            ]), 0)
        depth.assert_called_once_with([
            "--config", "/private/a recipe.json", "--isolated-store", "/tmp/local.sqlite",
        ])
        market.assert_not_called()

    def test_dividend_dispatch_uses_its_own_collector(self):
        with patch("dividend_collect.main", return_value=0) as dividends, patch("market_collect.main") as market:
            self.assertEqual(run_collection.main([
                "dividends", "--config", "/private/calendar.json",
                "--isolated-store", "/tmp/local.sqlite",
            ]), 0)
        dividends.assert_called_once_with([
            "--config", "/private/calendar.json", "--isolated-store", "/tmp/local.sqlite",
        ])
        market.assert_not_called()

    def test_fundamental_dispatch_forwards_the_symbol(self):
        with patch("fundamental_collect.main", return_value=0) as fundamentals, patch("market_collect.main") as market:
            self.assertEqual(run_collection.main([
                "fundamentals", "--symbol", "AAA",
                "--config", "/private/fundamentals.json",
            ]), 0)
        fundamentals.assert_called_once_with([
            "--config", "/private/fundamentals.json", "--symbol", "AAA",
        ])
        market.assert_not_called()

    def test_symbol_and_publish_flags_are_limited_to_their_collectors(self):
        for arguments in [
            ["fundamentals"],
            ["quotes", "--symbol", "AAA"],
            ["depth", "--publish-profile", "/private/profile.json"],
            ["dividends", "--publish-profile", "/private/profile.json"],
        ]:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run_collection.main(arguments)

    def test_unmigrated_jobs_cannot_fall_back_to_legacy_parser(self):
        for kind in ["orders"]:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run_collection.main([kind])


if __name__ == "__main__":
    unittest.main()

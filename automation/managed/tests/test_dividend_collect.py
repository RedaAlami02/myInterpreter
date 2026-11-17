import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dividend_collect
import dividend_feed
import worker

PROVIDER = "feed_0123456789abcdef"
PAGE = "<html><table><tr><th>Émetteur</th></tr></table></html>"
RECEIVED = datetime(2026, 10, 30, 18, 5, tzinfo=timezone.utc)


def config(**overrides):
    value = {
        "contract": "private-dividend-config/v1",
        "provider_namespace": PROVIDER,
        "jobs": {
            "dividends": [
                {"year": 2026, "url": "https://example.invalid/c/2026"},
                {
                    "year": 2027,
                    "url": "https://example.invalid/c/2027",
                    "optional": True,
                    "charset": "utf-8",
                },
            ]
        },
    }
    value.update(overrides)
    return value


def fetcher(pages, received=RECEIVED):
    def fetch(recipe, deadline, limit):
        value = pages.get(recipe["year"])
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise worker.AcquisitionError("HTTP_FAILURE", http_status=404)
        return value, received

    return fetch


class EnvelopeTests(unittest.TestCase):
    def test_capture_identity_targets_and_completeness(self):
        value = dividend_collect.acquire(
            config(), fetcher=fetcher({2026: PAGE.encode()}), seconds=5,
            now=RECEIVED + timedelta(seconds=10)
        )
        self.assertEqual(value["contract"], "private-acquisition/v2")
        self.assertEqual(value["kind"], "dividends")
        self.assertEqual(value["execution"], "CURRENT_ACQUISITION")
        self.assertEqual(value["authority"], "UNPROMOTED")
        self.assertFalse(value["prediction_eligible"])
        # The optional next-year page is absent but does not make the run incomplete.
        self.assertEqual(value["completeness"], "COMPLETE")
        self.assertEqual(value["errors"], [])
        self.assertEqual([t["year"] for t in value["targets"]], [2026])
        self.assertEqual(value["targets"][0]["charset"], None)
        capture = value["captures"][0]
        self.assertEqual(bytes.fromhex(capture["raw_hex"]), PAGE.encode())
        self.assertEqual(capture["capture_id"], hashlib.sha256(
            json.dumps(
                [PROVIDER, capture["sha256"], capture["received_at"]],
                separators=(",", ":"),
            ).encode()
        ).hexdigest())

    def test_optional_redirect_is_not_calendar_evidence(self):
        value = dividend_collect.acquire(config(), fetcher=fetcher({2026: PAGE.encode(),
            2027: worker.AcquisitionError("HTTP_FAILURE", http_status=302)}), seconds=5,
            now=RECEIVED + timedelta(seconds=10))
        self.assertEqual(value['completeness'], 'COMPLETE')
        self.assertEqual(len(value['captures']), 1)
        with self.assertRaises(worker.AcquisitionError):
            dividend_collect.acquire(config(), fetcher=fetcher({2026:
                worker.AcquisitionError("HTTP_FAILURE", http_status=302)}), seconds=5)

    def test_required_page_failure_fails_the_run(self):
        with self.assertRaisesRegex(worker.AcquisitionError, "HTTP_FAILURE"):
            dividend_collect.acquire(
                config(), fetcher=fetcher({}), seconds=5,
            now=RECEIVED + timedelta(seconds=10)
            )
        with self.assertRaisesRegex(
            worker.AcquisitionError, "NO_CALENDAR_PAGES"
        ):
            dividend_collect.acquire(
                config(
                    jobs={"dividends": [
                        {"year": 2027, "url": "https://example.invalid/c/2027",
                         "optional": True}
                    ]}
                ),
                fetcher=fetcher({}),
                seconds=5,
                now=RECEIVED + timedelta(seconds=10),
            )

    def test_invalid_configuration_is_refused(self):
        for value in [
            config(contract="private-dividend-config/v0"),
            config(provider_namespace="legacy"),
            config(jobs={"quotes": []}),
            config(jobs={"dividends": [
                {"year": 2026, "url": "http://example.invalid/c"}
            ]}),
            config(jobs={"dividends": [
                {"year": 2026, "url": "https://example.invalid/a"},
                {"year": 2026, "url": "https://example.invalid/b"},
            ]}),
            config(jobs={"dividends": [
                {"year": 2026, "url": "https://example.invalid/a",
                 "charset": "bad charset"}
            ]}),
            config(jobs={"dividends": []}),
        ]:
            with self.assertRaises(worker.AcquisitionError):
                dividend_collect.acquire(value, fetcher=fetcher({2026: PAGE.encode()}), now=RECEIVED + timedelta(seconds=10))
        with self.assertRaises(worker.AcquisitionError):
            dividend_collect.config_check(None)

    def test_collected_archive_feeds_the_projection(self):
        value = dividend_collect.acquire(
            config(), fetcher=fetcher({2026: PAGE.encode()}), seconds=5,
            now=RECEIVED + timedelta(seconds=10)
        )
        digest, blob = worker.packed(value)
        projection = dividend_feed.build(
            blob,
            digest,
            {"provider_namespace": PROVIDER},
            {
                "contract": "private-dividend-index/v1",
                "provider_namespace": PROVIDER,
                "index": {"FIXTURE": "Fixture"},
            },
            as_of=RECEIVED + timedelta(minutes=1),
        )
        self.assertEqual(projection["years"], [2026])
        self.assertEqual(projection["source_execution"], "CURRENT_ACQUISITION")


class EntryPointTests(unittest.TestCase):
    def test_main_stores_an_envelope_and_reports_already_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            config_path = folder / "config.json"
            config_path.write_text(json.dumps(config()))
            database = folder / "isolated.sqlite"
            value = dividend_collect.acquire(
                config(), fetcher=fetcher({2026: PAGE.encode()}), seconds=5,
            now=RECEIVED + timedelta(seconds=10)
            )
            with patch.object(dividend_collect, "acquire", return_value=value):
                with patch("builtins.print") as printed:
                    code = dividend_collect.main(
                        ["--config", str(config_path),
                         "--isolated-store", str(database)], clock=lambda: RECEIVED
                    )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(printed.call_args.args[0])["status"], "COMPLETE")
            store = worker.SQLiteStore(database)
            self.assertTrue(
                store.complete(PROVIDER, "dividends", value["slot"])
            )
            with patch.object(dividend_collect, "acquire", return_value=value):
                with patch("builtins.print") as printed:
                    code = dividend_collect.main(
                        ["--config", str(config_path),
                         "--isolated-store", str(database)], clock=lambda: RECEIVED
                    )
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads(printed.call_args.args[0])["status"], "ALREADY_COMPLETE"
            )


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fundamental_collect
import fundamental_feed
import worker
from test_fundamental_frame import payload, tables

PROVIDER = "feed_0123456789abcdef"
RECEIVED = datetime(2026, 10, 30, 18, 5, tzinfo=timezone.utc)


def config(**overrides):
    value = {
        "contract": "private-fundamental-config/v1",
        "provider_namespace": PROVIDER,
        "jobs": {
            "fundamentals": {
                "identity": [
                    {"kind": "stock", "url": "https://example.invalid/stock/{symbol}"},
                    {"kind": "symlinks", "url": "https://example.invalid/symlinks"},
                ],
                "company": [
                    {
                        "kind": "fp",
                        "method": "POST",
                        "url": "https://example.invalid/sb",
                        "body": {
                            "table": "fp-corpo",
                            "options": {"filter": {
                                "column": "Société", "value": "{company}",
                            }},
                        },
                    },
                    {"kind": "nmt", "method": "POST", "url": "https://example.invalid/sb",
                     "body": {"table": "nmt-corpo"}},
                ],
                "symbol": [
                    {"kind": "desc", "url": "https://example.invalid/desc/{symbol}"},
                ],
            }
        },
    }
    value.update(overrides)
    return value


def values():
    return {
        "stock": {"name": "Alpha SA"},
        "symlinks": [{"symbol": "AAA", "name": "Alpha SA", "type": "Banks"}],
        "fp": tables()["fp"],
        "nmt": tables()["nmt"],
        "desc": payload({"description": "Fixture description"}),
    }


def fetcher(data=None, received=RECEIVED, failures=()):
    data = data if data is not None else values()
    calls = []

    def fetch(recipe, deadline, limit):
        calls.append(recipe)
        if recipe["kind"] in failures:
            raise worker.AcquisitionError("HTTP_FAILURE", http_status=500)
        return json.dumps(data[recipe["kind"]]).encode(), received

    return fetch, calls


class EnvelopeTests(unittest.TestCase):
    def test_subject_archive_preserves_times_and_rejects_mismatched_subject(self):
        fetch, _ = fetcher()
        value = fundamental_collect.acquire(config(), 'AAA', fetcher=fetch,
            now=RECEIVED + timedelta(seconds=10), subject_scoped=True)
        self.assertEqual(value['contract'], 'private-acquisition/v3')
        self.assertEqual(value['subject_key'], 'symbol:AAA')
        self.assertEqual(value['captures'][0]['received_at'], RECEIVED.isoformat())
        digest, blob = worker.packed(value)
        fundamental_feed.verified_archive(blob, digest, config())
        value['subject_key'] = 'symbol:BBB'
        digest, blob = worker.packed(value)
        with self.assertRaises(ValueError):
            fundamental_feed.verified_archive(blob, digest, config())

    def test_captures_targets_and_company_substitution(self):
        fetch, calls = fetcher()
        value = fundamental_collect.acquire(
            config(), "AAA", fetcher=fetch, seconds=5,
            now=RECEIVED + timedelta(seconds=10),
        )
        self.assertEqual(value["contract"], "private-acquisition/v2")
        self.assertEqual(value["kind"], "fundamentals")
        self.assertEqual(value["symbol"], "AAA")
        self.assertEqual(value["execution"], "CURRENT_ACQUISITION")
        self.assertEqual(value["completeness"], "COMPLETE")
        self.assertEqual(value["errors"], [])
        self.assertEqual(
            [target["kind"] for target in value["targets"]],
            ["stock", "symlinks", "fp", "nmt", "desc"],
        )
        self.assertEqual(len(value["captures"]), 5)
        for capture, target in zip(value["captures"], value["targets"]):
            self.assertEqual(target["request_index"], capture["request_index"])
            self.assertEqual(
                hashlib.sha256(bytes.fromhex(capture["raw_hex"])).hexdigest(),
                capture["sha256"],
            )
        company_calls = [call for call in calls if call["kind"] in {"fp", "nmt"}]
        self.assertTrue(company_calls)
        for call in company_calls:
            self.assertNotIn("{company}", json.dumps(call))
        self.assertEqual(
            [call["body"]["options"]["filter"]["value"]
             for call in company_calls if call["kind"] == "fp"],
            ["Alpha SA"],
        )
        self.assertEqual(
            [call["url"] for call in calls if call["kind"] == "desc"],
            ["https://example.invalid/desc/AAA"],
        )

    def test_a_failed_table_makes_the_run_incomplete_but_is_retained(self):
        fetch, _ = fetcher(failures={"fp"})
        value = fundamental_collect.acquire(
            config(), "AAA", fetcher=fetch, seconds=5,
            now=RECEIVED + timedelta(seconds=10),
        )
        self.assertEqual(value["completeness"], "INCOMPLETE")
        self.assertIn({"kind": "fp", "code": "HTTP_FAILURE"}, value["errors"])
        self.assertEqual(
            [target["kind"] for target in value["targets"]],
            ["stock", "symlinks", "nmt", "desc"],
        )

    def test_unresolved_identity_is_refused(self):
        fetch, _ = fetcher(failures={"stock", "symlinks"})
        with self.assertRaisesRegex(
            worker.AcquisitionError, "UNRESOLVED_COMPANY_IDENTITY"
        ):
            fundamental_collect.acquire(
                config(), "AAA", fetcher=fetch, seconds=5,
                now=RECEIVED + timedelta(seconds=10),
            )
        other = values()
        other["symlinks"] = [{"symbol": "OTHER", "name": "Other"}]
        other["stock"] = {}
        fetch, _ = fetcher(other)
        with self.assertRaisesRegex(
            worker.AcquisitionError, "UNRESOLVED_COMPANY_IDENTITY"
        ):
            fundamental_collect.acquire(
                config(), "AAA", fetcher=fetch, seconds=5,
                now=RECEIVED + timedelta(seconds=10),
            )

    def test_invalid_configuration_and_symbols_are_refused(self):
        broken = [
            config(contract="private-fundamental-config/v0"),
            config(provider_namespace="legacy"),
            config(jobs={"quotes": {"identity": []}}),
            config(jobs={"fundamentals": {"company": []}}),
            config(jobs={"fundamentals": {"identity": [
                {"kind": "stock", "url": "https://example.invalid/{company}"}
            ]}}),
            config(jobs={"fundamentals": {"identity": [
                {"kind": "stock", "url": "http://example.invalid/s"}
            ]}}),
            config(jobs={"fundamentals": {"identity": [
                {"kind": "stock", "url": "https://example.invalid/a"},
                {"kind": "stock", "url": "https://example.invalid/b"},
            ]}}),
            config(jobs={"fundamentals": {"identity": [
                {"kind": "legacy", "url": "https://example.invalid/a"}
            ]}}),
            config(jobs={"fundamentals": {"identity": [
                {"kind": "stock", "url": "https://example.invalid/a",
                 "headers": {"X": "a\r\nInjected: 1"}}
            ]}}),
        ]
        for value in broken:
            with self.assertRaises(worker.AcquisitionError):
                fundamental_collect.config_check(value)
        fetch, _ = fetcher()
        for symbol in ["aaa", "", "A" * 40, "A B", "../etc"]:
            with self.assertRaisesRegex(worker.AcquisitionError, "INVALID_SYMBOL"):
                fundamental_collect.acquire(config(), symbol, fetcher=fetch)

    def test_collected_archive_feeds_the_projection(self):
        fetch, _ = fetcher()
        value = fundamental_collect.acquire(
            config(), "AAA", fetcher=fetch, seconds=5,
            now=RECEIVED + timedelta(seconds=10),
        )
        digest, blob = worker.packed(value)
        projection = fundamental_feed.build(
            blob,
            digest,
            {"provider_namespace": PROVIDER},
            {
                "contract": "private-fundamental-index/v1",
                "provider_namespace": PROVIDER,
                "symbols": {"AAA": "Alpha"},
            },
            as_of=RECEIVED + timedelta(minutes=1),
        )
        self.assertEqual(projection["symbol"], "AAA")
        self.assertEqual(projection["c_name"], "Alpha")
        self.assertIsNone(projection["fields"]["fiscal_year"])
        self.assertEqual(projection["fields"]["ext_name"], "Alpha SA")


class EntryPointTests(unittest.TestCase):
    def test_default_scoped_cli_rejects_unadmitted_capture_before_acquisition(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(config()))
            with patch.object(worker.SQLiteStore, 'admit_subject', return_value=False), \
                    patch.object(fundamental_collect, 'acquire') as source, patch('builtins.print') as printed:
                result = fundamental_collect.main(['--config', str(path), '--symbol', 'AAA',
                    '--isolated-store', str(Path(directory) / 'isolated.sqlite')])
            self.assertEqual(result, 1)
            source.assert_not_called()
            self.assertEqual(json.loads(printed.call_args.args[0])['code'], 'SUBJECT_ACQUISITION_NOT_ADMITTED')

    def test_legacy_store_rejected_before_scoped_acquisition(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(config()))
            with patch.object(worker, 'open_store', return_value=object()), \
                    patch.object(fundamental_collect, 'acquire') as source, patch('builtins.print'):
                result = fundamental_collect.main(['--config', str(path), '--symbol', 'AAA'])
            self.assertEqual(result, 1)
            source.assert_not_called()

    def test_main_stores_a_bundle_and_reports_already_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            path = folder / "config.json"
            path.write_text(json.dumps(config()))
            database = folder / "isolated.sqlite"
            fetch, _ = fetcher()
            bundle = fundamental_collect.acquire(
                config(), "AAA", fetcher=fetch, seconds=5,
                now=RECEIVED + timedelta(seconds=10),
            )
            with patch.object(fundamental_collect, "acquire", return_value=bundle):
                with patch("builtins.print") as printed:
                    code = fundamental_collect.main([
                        "--config", str(path), "--symbol", "AAA", "--legacy-unscoped",
                        "--isolated-store", str(database),
                    ])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(printed.call_args.args[0])["status"], "COMPLETE")
            store = worker.SQLiteStore(database)
            self.assertTrue(store.complete(PROVIDER, "fundamentals", bundle["slot"]))
            with patch.object(fundamental_collect, "acquire", return_value=bundle):
                with patch("builtins.print") as printed:
                    code = fundamental_collect.main([
                        "--config", str(path), "--symbol", "AAA", "--legacy-unscoped",
                        "--isolated-store", str(database),
                    ])
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads(printed.call_args.args[0])["status"], "ALREADY_COMPLETE"
            )


if __name__ == "__main__":
    unittest.main()

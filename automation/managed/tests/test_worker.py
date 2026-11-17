import copy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import worker

NOW = datetime(2026, 10, 27, 14, 10, tzinfo=timezone.utc)
NAMESPACE = "feed_0123456789abcdef"
SLOT = "2026-10-27T14:00:00+00:00"


def config():
    return {
        "provider_namespace": NAMESPACE,
        "jobs": {
            "quotes": [
                {
                    "url": "https://example.invalid/market",
                    "rows_path": ["rows"],
                    "expected_identities": ["a", "index"],
                    "fields": {
                        "source_identity": ["key"],
                        "price": ["value"],
                        "instrument_type": ["type"],
                        "session_date": ["day"],
                        "source_event_at": ["time"],
                    },
                }
            ]
        },
    }


def payload():
    return {
        "rows": [
            {
                "key": identity,
                "value": price,
                "type": kind,
                "day": "2026-10-27",
                "time": NOW.isoformat(),
            }
            for identity, price, kind in [("a", 12.5, "STOCK"), ("index", 200, "INDEX")]
        ]
    }


class WorkerTests(unittest.TestCase):
    def collect(self, value=None, cfg=None):
        body = payload() if value is None else value
        return worker.acquire(
            cfg or config(), "quotes", SLOT, fetcher=lambda *_: (json.dumps(body).encode(), NOW)
        )

    def test_complete_capture_separate_from_source_event_and_not_promoted(self):
        body = payload()
        body["rows"][0]["time"] = (NOW - timedelta(minutes=5)).isoformat()
        result = self.collect(body)
        self.assertEqual(result["completeness"], "COMPLETE")
        row = result["observations"][0]
        self.assertNotEqual(row["source_event_at"], row["captured_at"])
        self.assertFalse(result["prediction_eligible"])
        capture = result["captures"][0]
        raw = bytes.fromhex(capture["raw_hex"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), capture["sha256"])
        self.assertEqual(json.loads(raw), body)

    def test_missing_stock_and_index_both_fail_closed(self):
        for index in [0, 1]:
            body = payload()
            del body["rows"][index]
            self.assertEqual(self.collect(body)["completeness"], "INCOMPLETE")

    def test_wrong_session_date(self):
        body = payload()
        body["rows"][0]["day"] = "2026-10-26"
        self.assertEqual(self.collect(body)["errors"][0]["code"], "WRONG_SESSION_DATE")

    def test_stale_and_future_events_fail(self):
        for delta in [timedelta(days=-1), timedelta(seconds=1)]:
            body = payload()
            body["rows"][0]["time"] = (NOW + delta).isoformat()
            self.assertEqual(self.collect(body)["completeness"], "INCOMPLETE")

    def test_unknown_event_is_explicitly_only_session_date(self):
        cfg = config()
        del cfg["jobs"]["quotes"][0]["fields"]["source_event_at"]
        row = self.collect(cfg=cfg)["observations"][0]
        self.assertNotIn("source_event_at", row)
        self.assertEqual(row["freshness"], "SESSION_DATE_ONLY")

    def test_conflicting_prices_are_not_silently_deduplicated(self):
        body = payload()
        body["rows"].append(dict(body["rows"][0], value=99))
        self.assertEqual(self.collect(body)["errors"][0]["code"], "CONFLICTING_IDENTITIES")

    def test_namespace_and_missing_universe_rejected(self):
        cfg = config()
        cfg["provider_namespace"] = "legacy-name"
        with self.assertRaises(worker.AcquisitionError):
            self.collect(cfg=cfg)
        cfg = config()
        del cfg["jobs"]["quotes"][0]["expected_identities"]
        with self.assertRaises(worker.AcquisitionError):
            self.collect(cfg=cfg)

    def test_corrupt_raw_preserved_even_when_normalization_fails(self):
        envelope = worker.acquire(config(), "quotes", SLOT, fetcher=lambda *_: (b"not-json", NOW))
        self.assertEqual(envelope["completeness"], "INCOMPLETE")
        self.assertEqual(bytes.fromhex(envelope["captures"][0]["raw_hex"]), b"not-json")

    def test_failure_retry_restart_and_unique_logical_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "isolated.sqlite"
            store = worker.SQLiteStore(path)
            incomplete = worker.acquire(
                config(),
                "quotes",
                SLOT,
                fetcher=lambda *_: (_ for _ in ()).throw(
                    worker.AcquisitionError("NETWORK_FAILURE")
                ),
            )
            store.save(incomplete)
            self.assertFalse(store.complete(NAMESPACE, "quotes", SLOT))
            complete = self.collect()
            digest = store.save(complete)
            store.save(complete)
            later = copy.deepcopy(complete)
            later["completed_at"] = datetime.now(timezone.utc).isoformat()
            store.save(later)
            store.db.close()
            restarted = worker.SQLiteStore(path)
            self.assertTrue(restarted.complete(NAMESPACE, "quotes", SLOT))
            self.assertEqual(restarted.db.execute("SELECT COUNT(*) FROM slots").fetchone()[0], 1)
            self.assertEqual(restarted.db.execute("SELECT digest FROM slots").fetchone()[0], digest)
            self.assertEqual(restarted.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 3)
            restarted.db.close()

    def test_invalid_prices(self):
        for value in [0, -1, True, "12.5", float("nan")]:
            body = payload()
            body["rows"][0]["value"] = value
            self.assertEqual(self.collect(body)["completeness"], "INCOMPLETE")

    def test_packed_bytes_verify_and_retain_native_payload(self):
        envelope = self.collect()
        digest, blob = worker.packed(envelope)
        self.assertEqual(digest, hashlib.sha256(blob).hexdigest())
        self.assertEqual(json.loads(gzip.decompress(blob)), envelope)

    def test_windows_skip_weekend_and_stale_depth_slot(self):
        self.assertIsNone(worker.scheduled_slot(NOW.replace(day=25), "quotes"))
        self.assertIsNone(worker.scheduled_slot(NOW.replace(minute=17), "depth"))
        self.assertIsNotNone(worker.scheduled_slot(NOW, "depth"))
        self.assertIsNone(worker.scheduled_slot(NOW, "fundamentals"))

    def test_worker_database_credentials_are_project_bound_and_not_admin(self):
        base = "host=aws-0-eu-west-1.pooler.supabase.com dbname=postgres user=app_collector.abcdefghijklmnopqrst password=fixture_only sslmode=verify-full"
        with patch("psycopg.connect") as connect:
            worker.PostgresStore(base, "abcdefghijklmnopqrst")
            self.assertEqual(connect.call_args.kwargs["sslrootcert"], "system")
            connect.reset_mock()
            for candidate, reference in [
                (base.replace("app_collector.", "postgres."), "abcdefghijklmnopqrst"),
                (base.replace("verify-full", "require"), "abcdefghijklmnopqrst"),
                (base, "wrongprojectreference"),
                (
                    base.replace("aws-0-eu-west-1.pooler.supabase.com", "example.invalid"),
                    "abcdefghijklmnopqrst",
                ),
                (base + " options=unsafe", "abcdefghijklmnopqrst"),
                (base, None),
            ]:
                with self.assertRaises(worker.AcquisitionError):
                    worker.PostgresStore(candidate, reference)
            connect.assert_not_called()

    def test_deadline_failure_is_incomplete_not_empty_success(self):
        envelope = worker.acquire(
            config(),
            "quotes",
            SLOT,
            fetcher=lambda *_: (_ for _ in ()).throw(worker.AcquisitionError("DEADLINE")),
        )
        self.assertEqual(envelope["completeness"], "INCOMPLETE")
        self.assertEqual(envelope["captures"], [])

    def test_conflicts_across_requests_are_preserved_and_fail_complete(self):
        cfg = config()
        cfg["jobs"]["quotes"] *= 2
        envelope = self.collect(cfg=cfg)
        self.assertEqual(len(envelope["captures"]), 2)
        self.assertEqual(envelope["completeness"], "INCOMPLETE")
        self.assertIn("CROSS_REQUEST_IDENTITY_CONFLICT", [r["code"] for r in envelope["errors"]])

    def response(self, status=200, body=b"{}"):
        response = MagicMock()
        response.status_code = status
        response.iter_content.return_value = [body]
        context = MagicMock()
        context.__enter__.return_value = response
        return context

    def test_http_client_uses_no_redirects_and_no_ambient_machine_auth(self):
        with patch("worker.requests.request", return_value=self.response()) as request:
            raw, received = worker.fetch(config()["jobs"]["quotes"][0], time.monotonic() + 20)
            self.assertEqual(raw, b"{}")
            self.assertIsNotNone(received.tzinfo)
            self.assertFalse(request.call_args.kwargs["allow_redirects"])
            self.assertIsInstance(request.call_args.kwargs["auth"], worker.NoAmbientAuth)

    def test_transient_http_failure_retries_but_forbidden_does_not(self):
        with (
            patch(
                "worker.requests.request", side_effect=[self.response(503), self.response()]
            ) as request,
            patch("worker.time.sleep"),
        ):
            worker.fetch(config()["jobs"]["quotes"][0], time.monotonic() + 20)
            self.assertEqual(request.call_count, 2)
        with patch("worker.requests.request", return_value=self.response(403)) as request:
            with self.assertRaises(worker.AcquisitionError) as error:
                worker.fetch(config()["jobs"]["quotes"][0], time.monotonic() + 20)
            self.assertEqual(error.exception.http_status, 403)
            self.assertEqual(str(error.exception), "HTTP_FAILURE")
            self.assertEqual(request.call_count, 1)

    def test_network_timeout_retry_and_response_size_limit(self):
        with (
            patch(
                "worker.requests.request", side_effect=[worker.requests.Timeout(), self.response()]
            ) as request,
            patch("worker.time.sleep"),
        ):
            worker.fetch(config()["jobs"]["quotes"][0], time.monotonic() + 20)
            self.assertEqual(request.call_count, 2)
        with patch("worker.requests.request", return_value=self.response(body=b"12345")):
            with self.assertRaisesRegex(worker.AcquisitionError, "RESPONSE_TOO_LARGE"):
                worker.fetch(config()["jobs"]["quotes"][0], time.monotonic() + 20, max_body=4)

    def test_cleartext_endpoint_rejected_before_any_request(self):
        recipe = dict(config()["jobs"]["quotes"][0], url="http://example.invalid")
        with patch("worker.requests.request") as request:
            with self.assertRaisesRegex(worker.AcquisitionError, "INVALID_ENDPOINT"):
                worker.fetch(recipe, time.monotonic() + 20)
            request.assert_not_called()

    def test_session_date_and_price_cannot_be_invented_by_configuration(self):
        for field, value in [
            ("session_date", "2026-10-27"),
            ("price", 12.5),
            ("source_event_at", NOW.isoformat()),
        ]:
            cfg = config()
            cfg["jobs"]["quotes"][0]["constants"] = {field: value}
            cfg["jobs"]["quotes"][0]["fields"].pop(field, None)
            with self.assertRaises(worker.AcquisitionError):
                self.collect(cfg=cfg)

    def test_appwrite_not_imported(self):
        self.assertNotIn("appwrite", sys.modules)


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from archive_store import ArchiveGatewayStore
import worker

REF = "a" * 20
URL = "https://" + REF + ".supabase.co/functions/v1/private-market-archive"
TOKEN = "arc_write_" + "a" * 64


def envelope():
    return {"execution": "CURRENT_ACQUISITION", "value": "raw-evidence-fixture"}


class Response:
    def __init__(self, value, status=200):
        self.raw = json.dumps(value).encode()
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def iter_content(self, _):
        yield self.raw


class HTTP:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        value = self.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class ArchiveStoreTests(unittest.TestCase):
    def setUp(self):
        self.spool = tempfile.TemporaryDirectory()
        self.addCleanup(self.spool.cleanup)
        self.environment = patch.dict(
            "os.environ", {"APP_ARCHIVE_SPOOL_DIR": self.spool.name}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def receipt(self, value=None, **updates):
        digest, blob = worker.packed(value or envelope())
        return {
            "contract": "private-archive-receipt/v1",
            "status": "STORED",
            "sha256": digest,
            "bytes": len(blob),
            "prediction_eligible": False,
            **updates,
        }

    def test_exact_compressed_archive_sent_and_receipt_checked(self):
        http = HTTP(Response(self.receipt()))
        store = ArchiveGatewayStore(URL, TOKEN, REF, session=http)
        digest, raw = worker.packed(envelope())
        self.assertEqual(store.save(envelope()), digest)
        args, kwargs = http.calls[0]
        self.assertEqual(args, (URL,))
        self.assertEqual(kwargs["data"], raw)
        self.assertFalse(kwargs["allow_redirects"])
        self.assertIsInstance(kwargs["auth"], worker.NoAmbientAuth)
        self.assertEqual(set(kwargs["headers"]), {"Authorization", "Content-Type"})

    def test_replays_and_diagnostics_never_leave_local_storage(self):
        http = HTTP()
        store = ArchiveGatewayStore(URL, TOKEN, REF, session=http)
        for mode in ["RECORDED_REPLAY", "AFTER_HOURS_DIAGNOSTIC", None]:
            with self.assertRaisesRegex(
                worker.AcquisitionError, "REMOTE_ARCHIVE_REQUIRES"
            ):
                store.save({**envelope(), "execution": mode})
        self.assertEqual(http.calls, [])

    def test_wrong_destination_project_or_privileged_credential_rejected(self):
        for url, token, project in [
            (URL.replace("https:", "http:"), TOKEN, REF),
            (URL + "?redirect=1", TOKEN, REF),
            (URL, TOKEN, "b" * 20),
            (URL, "privileged-key-placeholder", REF),
            (URL, TOKEN, None),
        ]:
            with self.assertRaisesRegex(
                worker.AcquisitionError, "INVALID_ARCHIVE_CREDENTIAL"
            ):
                ArchiveGatewayStore(url, token, project)

    def test_receipt_hash_size_status_and_authority_must_match(self):
        for updates in [
            {"sha256": "b" * 64},
            {"bytes": 1},
            {"bytes": True},
            {"status": "RESERVED"},
            {"prediction_eligible": True},
            {"contract": "other"},
        ]:
            store = ArchiveGatewayStore(
                URL, TOKEN, REF, session=HTTP(Response(self.receipt(**updates)))
            )
            with self.assertRaisesRegex(
                worker.AcquisitionError, "INVALID_ARCHIVE_RECEIPT"
            ):
                store.save(envelope())

    def test_transient_retry_resends_identical_bytes(self):
        http = HTTP(Response({}, 503), Response(self.receipt()))
        ArchiveGatewayStore(URL, TOKEN, REF, session=http).save(envelope())
        self.assertEqual(http.calls[0][1]["data"], http.calls[1][1]["data"])

    def test_failed_upload_retained_and_restart_flush_does_not_reacquire_or_retimestamp(
        self,
    ):
        http = HTTP(Response({}, 503), Response({}, 503))
        store = ArchiveGatewayStore(URL, TOKEN, REF, session=http)
        with self.assertRaises(worker.AcquisitionError):
            store.save(envelope())
        digest, blob = worker.packed(envelope())
        self.assertEqual(store.outbox.read(store.outbox.entries()[0]), blob)
        recovered_http = HTTP(Response(self.receipt()))
        restarted = ArchiveGatewayStore(URL, TOKEN, REF, session=recovered_http)
        self.assertEqual(restarted.flush_pending(), 1)
        self.assertEqual(recovered_http.calls[0][1]["data"], blob)
        self.assertEqual(restarted.outbox.entries(), [])

    def test_bad_receipt_keeps_unacknowledged_evidence(self):
        store = ArchiveGatewayStore(
            URL, TOKEN, REF, session=HTTP(Response(self.receipt(sha256="b" * 64)))
        )
        with self.assertRaises(worker.AcquisitionError):
            store.save(envelope())
        self.assertEqual(len(store.outbox.entries()), 1)

    def test_network_error_is_sanitized_and_retry_bounded(self):
        http = HTTP(
            requests.Timeout("PRIVATE_DETAIL"), requests.Timeout("PRIVATE_DETAIL")
        )
        with self.assertRaisesRegex(
            worker.AcquisitionError, "^ARCHIVE_GATEWAY_UNAVAILABLE$"
        ):
            ArchiveGatewayStore(URL, TOKEN, REF, session=http).save(envelope())
        self.assertEqual(len(http.calls), 2)

    def test_unauthorized_or_redirect_response_is_never_followed(self):
        for status in [401, 403, 302]:
            http = HTTP(Response({}, status))
            with self.assertRaisesRegex(
                worker.AcquisitionError, "ARCHIVE_GATEWAY_REJECTED"
            ):
                ArchiveGatewayStore(URL, TOKEN, REF, session=http).save(envelope())
            self.assertEqual(len(http.calls), 1)

    def test_status_response_requires_boolean_not_truthy_value(self):
        for complete in [True, False, "false", 1]:
            http = HTTP(
                Response(
                    {"contract": "private-archive-receipt/v1", "complete": complete}
                )
            )
            store = ArchiveGatewayStore(URL, TOKEN, REF, session=http)
            if type(complete) is bool:
                self.assertIs(
                    store.complete(
                        "feed_0123456789abcdef", "quotes", "2026-10-28T12:00:00Z"
                    ),
                    complete,
                )
            else:
                with self.assertRaises(worker.AcquisitionError):
                    store.complete(
                        "feed_0123456789abcdef", "quotes", "2026-10-28T12:00:00Z"
                    )

    def test_oversized_receipt_rejected(self):
        store = ArchiveGatewayStore(
            URL, TOKEN, REF, session=HTTP(Response({"x": "x" * 5000}))
        )
        with self.assertRaisesRegex(worker.AcquisitionError, "INVALID_ARCHIVE_RECEIPT"):
            store.save(envelope())

    def test_factory_never_mixes_gateway_and_database_credentials(self):
        with patch.dict(
            "os.environ",
            {
                "APP_ARCHIVE_GATEWAY_URL": URL,
                "APP_ARCHIVE_WRITE_TOKEN": TOKEN,
                "APP_WORKER_DATABASE_URL": "forbidden",
            },
            clear=True,
        ):
            with (
                patch("worker.PostgresStore") as db,
                self.assertRaises(worker.AcquisitionError),
            ):
                worker.open_store(None, {"archive_project_reference": REF})
            db.assert_not_called()

    def test_factory_gateway_and_isolation_paths(self):
        with patch.dict(
            "os.environ",
            {"APP_ARCHIVE_GATEWAY_URL": URL, "APP_ARCHIVE_WRITE_TOKEN": TOKEN},
            clear=True,
        ):
            with patch("worker.PostgresStore") as db:
                self.assertIsInstance(
                    worker.open_store(None, {"archive_project_reference": REF}),
                    ArchiveGatewayStore,
                )
                with tempfile.TemporaryDirectory() as folder:
                    store = worker.open_store(Path(folder) / "local.sqlite", {})
                    self.assertIsInstance(store, worker.SQLiteStore)
                    store.db.close()
            db.assert_not_called()

    def test_pending_upload_failure_prevents_starting_a_new_collection(self):
        from unittest.mock import Mock
        store = Mock(spec=["flush_pending"])
        store.flush_pending.side_effect = worker.AcquisitionError("ARCHIVE_GATEWAY_UNAVAILABLE")
        with self.assertRaisesRegex(worker.AcquisitionError, "ARCHIVE_GATEWAY_UNAVAILABLE"):
            worker.resume_store(store)
        store.flush_pending.assert_called_once_with()
        self.assertEqual(worker.resume_store(object()), 0)


if __name__ == "__main__":
    unittest.main()

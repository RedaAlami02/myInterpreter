import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projection_store
import worker

from fixture_projection import Session, Response, TOKEN, URL
DOCUMENT = '{"contract":"dividend-projection/v1","rows":[{"fixture":"client-only"}]}'


def receipt(document=DOCUMENT, **update):
    value = {
        "contract": "projection-receipt/v1",
        "status": "PUBLISHED",
        "kind": "dividends",
        "sha256": hashlib.sha256(document.encode()).hexdigest(),
        "records": 1,
    }
    value.update(update)
    return json.dumps(value).encode()


class PublisherTests(unittest.TestCase):
    def store(self, *responses):
        session = Session(*responses)
        return (
            projection_store.ProjectionPublisher(
                URL, TOKEN, "a" * 20, session=session
            ),
            session,
        )

    def test_credentials_are_bound_to_the_project_and_endpoint(self):
        for url, token, reference in [
            (URL.replace("https://", "http://"), TOKEN, "a" * 20),
            (URL + "?x=1", TOKEN, "a" * 20),
            (URL, "app_publish_" + "a" * 64, "a" * 20),
            (URL, TOKEN, "b" * 20),
            (URL, TOKEN, None),
        ]:
            with self.assertRaises(worker.AcquisitionError):
                projection_store.ProjectionPublisher(url, token, reference)

    def test_exact_document_is_sent_once_and_receipt_validated(self):
        store, session = self.store(Response(200, receipt()))
        result = store.publish(DOCUMENT)
        self.assertEqual(
            result,
            {
                "status": "PUBLISHED",
                "kind": "dividends",
                "sha256": hashlib.sha256(DOCUMENT.encode()).hexdigest(),
                "records": 1,
            },
        )
        url, options = session.calls[0]
        self.assertEqual(url, URL)
        self.assertEqual(options["headers"]["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(options["headers"]["Content-Type"], "application/json")
        self.assertFalse(options["allow_redirects"])
        value = json.loads(options["data"])
        self.assertEqual(set(value), {"document", "sha256"})
        self.assertEqual(value["document"], DOCUMENT)
        self.assertEqual(
            value["sha256"], hashlib.sha256(DOCUMENT.encode()).hexdigest()
        )

    def test_only_an_exact_published_receipt_is_accepted(self):
        for update in [
            {"status": "REJECTED"},
            {"contract": "projection-receipt/v0"},
            {"sha256": "b" * 64},
            {"kind": "quotes"},
            {"records": "1"},
            {"records": True},
            {"records": -1},
            {"records": 0},
            {"kind": "fundamentals"},
        ]:
            store, _ = self.store(Response(200, receipt(**update)))
            with self.assertRaises(worker.AcquisitionError):
                store.publish(DOCUMENT)
        store, _ = self.store(Response(200, b"not-json"))
        with self.assertRaises(worker.AcquisitionError):
            store.publish(DOCUMENT)

    def test_transient_failure_retries_the_same_bytes(self):
        store, session = self.store(Response(503, b""), Response(200, receipt()))
        self.assertEqual(store.publish(DOCUMENT)["status"], "PUBLISHED")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0][1]["data"], session.calls[1][1]["data"])

    def test_repeated_network_failure_fails_closed(self):
        store, session = self.store(
            requests.ConnectionError(), requests.ConnectionError()
        )
        with self.assertRaisesRegex(
            worker.AcquisitionError, "PROJECTION_GATEWAY_UNAVAILABLE"
        ):
            store.publish(DOCUMENT)
        self.assertEqual(len(session.calls), 2)

    def test_cli_requires_configuration(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
        import publish_projection

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "document.json"
            path.write_text(DOCUMENT + "\n")
            with patch.dict("os.environ", {}, clear=True):
                with patch("builtins.print") as printed:
                    code = publish_projection.main(
                        ["--document", str(path)]
                    )
            self.assertEqual(code, 1)
            self.assertEqual(
                json.loads(printed.call_args.args[0])["code"],
                "PROJECTION_NOT_CONFIGURED",
            )


if __name__ == "__main__":
    unittest.main()

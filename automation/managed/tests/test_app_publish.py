import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app_feed
import app_publish
import market_collect
import publish_store
import run_collection
import worker
import price_refresh
from fixture_price import companies
from test_app_feed import CAPTURED, archive, config, mapping

URL = "https://" + "a" * 20 + ".supabase.co/functions/v1/private-app-publisher"
TOKEN = "app_publish_" + "a" * 64


def profile(cfg=None):
    cfg = cfg or config()
    selected = mapping()
    return {
        "contract": "private-app-publish/v1",
        "provider_namespace": cfg["provider_namespace"],
        "mapping": selected,
        "mapping_sha256": app_feed.fingerprint(selected),
        "recipe_sha256": app_feed.fingerprint(cfg["recipe"]),
    }


class Publisher:
    def __init__(self):
        self.calls = []
        self.application_rows = []

    def publish(self, candidate, selected, *, application_rows=None):
        self.calls.append((candidate, selected))
        if application_rows is not None:
            self.application_rows.append(application_rows)
        return {
            "status": "PUBLISHED",
            "sha256": "f" * 64,
            "captured_at": candidate["captured_at"],
        }


class Response:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, size=1024):
        yield self.body


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **options):
        self.calls.append((url, options))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def receipt(candidate, **update):
    value = {
        "contract": "private-app-publish-receipt/v1",
        "status": "PUBLISHED",
        "sha256": "f" * 64,
        "captured_at": candidate["captured_at"],
        "prediction_eligible": False,
        "portfolio_valuation_eligible": False,
    }
    value.update(update)
    return json.dumps(value).encode()


class PublishTests(unittest.TestCase):
    def test_full_rows_are_opt_in_and_require_matching_field_profile(self):
        digest, blob = archive()
        selected = profile(); selected['application_fields_sha256'] = app_feed.fingerprint({})
        target = Publisher()
        app_publish.publish(blob, digest, config(), selected, as_of=CAPTURED, publisher=target,
                            companies=companies(), field_bindings={})
        self.assertEqual(len(target.application_rows), 1)
        self.assertEqual(target.application_rows[0]['quote_payload_sha256'], app_feed.fingerprint(target.calls[0][0]))
        selected['application_fields_sha256'] = '0' * 64
        with self.assertRaisesRegex(app_feed.FrameError, 'APPLICATION_FIELDS_PIN_MISMATCH'):
            app_publish.publish(blob, digest, config(), selected, as_of=CAPTURED, publisher=Publisher(),
                                companies=companies(), field_bindings={})

    def candidate(self):
        digest, blob = archive()
        value = app_feed.build(blob, digest, config(), mapping(), as_of=CAPTURED)
        return digest, blob, value

    def test_verified_current_candidate_is_the_only_publishable_shape(self):
        digest, blob, expected = self.candidate()
        publisher = Publisher()
        result = app_publish.publish(
            blob,
            digest,
            config(),
            profile(),
            as_of=CAPTURED,
            publisher=publisher,
        )
        self.assertEqual(result["status"], "PUBLISHED")
        self.assertEqual(result["sha256"], "f" * 64)
        self.assertFalse(result["prediction_eligible"])
        self.assertEqual(len(publisher.calls), 1)
        published, selected = publisher.calls[0]
        self.assertEqual(published, expected)
        self.assertEqual(published["source_execution"], "CURRENT_ACQUISITION")
        self.assertEqual(published["identity_evidence"], "NORMALIZER_IDS_VERIFIED")
        self.assertEqual(selected, mapping())

    def test_replay_cannot_be_published(self):
        digest, blob = archive(execution="RECORDED_REPLAY")
        with self.assertRaisesRegex(
            app_feed.FrameError, "PUBLISH_REQUIRES_CURRENT_ACQUISITION"
        ):
            app_publish.publish(
                blob,
                digest,
                config(),
                profile(),
                as_of=CAPTURED,
                publisher=Publisher(),
            )

    def test_display_fallback_upgrade_is_explicitly_opt_in(self):
        digest, blob = archive()
        selected = profile()
        selected['display_fallbacks'] = True
        publisher = Publisher()
        app_publish.publish(blob, digest, config(), selected, as_of=CAPTURED, publisher=publisher)
        self.assertEqual(publisher.calls[0][0]['contract'], 'app-market-candidate/v2')
        selected['display_fallbacks'] = 'true'
        with self.assertRaises(app_feed.FrameError):
            app_publish.approved_mapping(selected, config())

    def test_legacy_identity_bridge_is_not_available_to_the_publisher(self):
        import gzip

        _, blob = archive(execution="RECORDED_REPLAY")
        value = json.loads(gzip.decompress(blob))
        del value["captures"][0]["capture_id"]
        for rows in value["market_frame"]["views"].values():
            for row in rows:
                del row["observation_id"]
        digest, original = worker.packed(value)
        with self.assertRaises(app_feed.FrameError):
            app_publish.publish(
                original,
                digest,
                config(),
                profile(),
                as_of=CAPTURED,
                publisher=Publisher(),
            )

    def test_unapproved_mapping_or_recipe_pins_are_refused(self):
        digest, blob = archive()
        for field, value in [
            ("mapping_sha256", "b" * 64),
            ("recipe_sha256", "b" * 64),
            ("contract", "private-app-publish/v0"),
            ("provider_namespace", "feed_1111111111111111"),
        ]:
            selected = dict(profile(), **{field: value})
            with self.assertRaises(app_feed.FrameError):
                app_publish.publish(
                    blob,
                    digest,
                    config(),
                    selected,
                    as_of=CAPTURED,
                    publisher=Publisher(),
                )
        broken = profile()
        broken["mapping"]["stocks"].pop()
        with self.assertRaisesRegex(
            app_feed.FrameError, "MAPPING_UNIVERSE_MISMATCH"
        ):
            app_publish.publish(
                blob,
                digest,
                config(),
                broken,
                as_of=CAPTURED,
                publisher=Publisher(),
            )

    def test_forged_archive_is_never_published(self):
        digest, blob = archive()
        with self.assertRaisesRegex(app_feed.FrameError, "ARCHIVE_HASH_MISMATCH"):
            app_publish.publish(
                blob,
                "b" * 64,
                config(),
                profile(),
                as_of=CAPTURED,
                publisher=Publisher(),
            )

    def test_publisher_requires_a_dedicated_credential(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                app_feed.FrameError, "PUBLISHER_NOT_CONFIGURED"
            ):
                app_publish.open_publisher(config())
        with patch.dict(
            os.environ,
            {
                "APP_PUBLISHER_URL": URL,
                "APP_PUBLISHER_TOKEN": TOKEN,
                "APP_WORKER_DATABASE_URL": "postgres://restricted",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                app_feed.FrameError, "AMBIGUOUS_PUBLISHER_CONFIGURATION"
            ):
                app_publish.open_publisher(config())

    def test_transport_binds_credentials_to_the_project_and_endpoint(self):
        project = "a" * 20
        for url, token, reference in [
            (URL.replace("https://", "http://"), TOKEN, project),
            (URL + "?x=1", TOKEN, project),
            (URL, "arc_write_" + "a" * 64, project),
            (URL, TOKEN, "b" * 20),
            (URL, TOKEN, None),
        ]:
            with self.assertRaises(worker.AcquisitionError):
                publish_store.AppPublisherStore(url, token, reference)


class TransportTests(unittest.TestCase):
    def test_application_document_hash_and_receipt_are_bound_to_the_quote_head(self):
        full = price_refresh.publication(self.blob, self.digest, config(), mapping(), companies(),
                                         self.candidate, as_of=CAPTURED, field_bindings={})
        full_sha = app_feed.fingerprint(full)
        store, session = self.store(Response(200, receipt(self.candidate, sha256=self.sha,
                                                application_rows_sha256=full_sha)))
        result = store.publish(self.candidate, mapping(), application_rows=full)
        self.assertEqual(result['application_rows_sha256'], full_sha)
        posted = json.loads(session.calls[0][1]['data'])
        self.assertEqual(posted['application_document'], app_feed.canonical(full))
        store, _ = self.store(Response(200, receipt(self.candidate, sha256=self.sha)))
        with self.assertRaises(worker.AcquisitionError):
            store.publish(self.candidate, mapping(), application_rows=full)
        full['quote_payload_sha256'] = '0' * 64
        store, session = self.store()
        with self.assertRaises(worker.AcquisitionError):
            store.publish(self.candidate, mapping(), application_rows=full)
        self.assertEqual(session.calls, [])
    def setUp(self):
        self.digest, self.blob = archive()
        self.candidate = app_feed.build(
            self.blob, self.digest, config(), mapping(), as_of=CAPTURED
        )
        self.document = app_feed.canonical(self.candidate)
        self.sha = hashlib.sha256(self.document.encode()).hexdigest()

    def store(self, *responses):
        session = Session(*responses)
        return (
            publish_store.AppPublisherStore(URL, TOKEN, "a" * 20, session=session),
            session,
        )

    def test_exact_document_and_mapping_are_sent_once(self):
        store, session = self.store(
            Response(200, receipt(self.candidate, sha256=self.sha))
        )
        result = store.publish(self.candidate, mapping())
        self.assertEqual(result["sha256"], self.sha)
        self.assertEqual(result["captured_at"], self.candidate["captured_at"])
        self.assertEqual(len(session.calls), 1)
        url, options = session.calls[0]
        self.assertEqual(url, URL)
        self.assertEqual(options["headers"]["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(options["headers"]["Content-Type"], "application/json")
        self.assertFalse(options["allow_redirects"])
        value = json.loads(options["data"])
        self.assertEqual(
            set(value),
            {"document", "mapping_document", "mapping_sha256", "sha256"},
        )
        self.assertEqual(value["document"], self.document)
        self.assertEqual(value["mapping_document"], app_feed.canonical(mapping()))
        self.assertEqual(value["mapping_sha256"], app_feed.fingerprint(mapping()))
        self.assertEqual(value["sha256"], self.sha)

    def test_only_an_exact_published_receipt_is_accepted(self):
        for update in [
            {"status": "REJECTED"},
            {"sha256": "b" * 64},
            {"contract": "private-app-publish-receipt/v0"},
            {"captured_at": "2026-10-28T00:00:00+00:00"},
            {"prediction_eligible": True},
            {"portfolio_valuation_eligible": True},
        ]:
            store, _ = self.store(
                Response(
                    200,
                    receipt(self.candidate, **{"sha256": self.sha, **update}),
                )
            )
            with self.assertRaises(worker.AcquisitionError):
                store.publish(self.candidate, mapping())
        store, _ = self.store(Response(200, b"not-json"))
        with self.assertRaises(worker.AcquisitionError):
            store.publish(self.candidate, mapping())

    def test_a_mapping_pin_mismatch_never_reaches_the_network(self):
        store, session = self.store()
        candidate = dict(self.candidate, mapping_sha256="b" * 64)
        with self.assertRaisesRegex(
            worker.AcquisitionError, "MAPPING_PIN_MISMATCH"
        ):
            store.publish(candidate, mapping())
        self.assertEqual(session.calls, [])

    def test_transient_failure_retries_the_same_bytes(self):
        store, session = self.store(
            Response(503, b""),
            Response(200, receipt(self.candidate, sha256=self.sha)),
        )
        self.assertEqual(
            store.publish(self.candidate, mapping())["sha256"], self.sha
        )
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0][1]["data"], session.calls[1][1]["data"])

    def test_repeated_network_failure_fails_closed(self):
        store, session = self.store(
            requests.ConnectionError(), requests.ConnectionError()
        )
        with self.assertRaisesRegex(
            worker.AcquisitionError, "PUBLISH_GATEWAY_UNAVAILABLE"
        ):
            store.publish(self.candidate, mapping())
        self.assertEqual(len(session.calls), 2)


class EntryPointTests(unittest.TestCase):
    def test_collection_refuses_remote_publish_from_local_replay_stores(self):
        for options in [
            ["--isolated-store", "/tmp/isolated.sqlite"],
            ["--recorded-response", "/tmp/raw", "--recorded-receipt", "/tmp/r"],
        ]:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = market_collect.main(
                    options + ["--publish-profile", "/tmp/profile.json"]
                )
            self.assertEqual(code, 1)
            self.assertEqual(
                json.loads(output.getvalue())["code"],
                "PUBLISH_REQUIRES_MANAGED_STORE",
            )

    def test_quote_dispatch_forwards_publish_profile_and_depth_does_not(self):
        with patch("market_collect.main", return_value=0) as market:
            run_collection.main(
                ["quotes", "--publish-profile", "/private/profile.json"]
            )
        market.assert_called_once_with(
            ["--publish-profile", "/private/profile.json"]
        )
        with patch("depth_collect.main", return_value=0) as depth:
            run_collection.main(["depth", "--config", "/private/depth.json"])
        depth.assert_called_once_with(["--config", "/private/depth.json"])


if __name__ == "__main__":
    unittest.main()

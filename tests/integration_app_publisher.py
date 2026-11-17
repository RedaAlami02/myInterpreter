#!/usr/bin/env python3
"""Synthetic Python builder -> HTTP -> Deno publisher; no live services."""

import hashlib
import json
from pathlib import Path
import select
import subprocess
import sys
import tempfile

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation/managed"))
sys.path.insert(0, str(ROOT / "automation/managed/tests"))
import app_feed
import market_collect
import publish_store
from test_market_frame import body, recipe, CAPTURED
import worker


def mapping():
    stocks = [
        {
            "source_identity": identity,
            "company_id": identity.lower(),
            "asset_key": "company:" + identity.lower(),
            "c_name": "Company " + identity,
            "symbol": identity,
        }
        for identity in ["A", "B"]
    ]
    return {
        "contract": "private-app-mapping/v1",
        "provider_namespace": "feed_0123456789abcdef",
        "stocks": stocks,
        "indices": [
            {
                "source_identity": "INDEX_MAIN",
                "company_id": None,
                "asset_key": "index:MASI",
                "c_name": "MASI",
                "symbol": "MASI",
            }
        ],
    }


def run():
    server = None
    try:
        server = subprocess.Popen(
            [
                "deno",
                "run",
                "--no-config",
                "--no-remote",
                "--no-npm",
                "--allow-net=127.0.0.1",
                str(ROOT / "tests/app_publisher_fixture.ts"),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if not select.select([server.stdout], [], [], 15)[0]:
            raise RuntimeError("LOCAL_FIXTURE_NOT_READY")
        port = json.loads(server.stdout.readline())["port"]
        endpoint = "http://127.0.0.1:" + str(port)

        class LoopbackTransport:
            def post(self, _validated_url, **kwargs):
                # Explicit fixture injection only; production URL checks stay intact.
                return requests.post(endpoint + "/publish", **kwargs)

        config = {
            "contract": "private-market-config/v2",
            "provider_namespace": "feed_0123456789abcdef",
            "recipe": recipe(),
        }
        value = market_collect.envelope(
            config,
            json.dumps(body()).encode(),
            CAPTURED,
            "2026-10-27T14:00:00+00:00",
            execution="CURRENT_ACQUISITION",
        )
        value["completed_at"] = CAPTURED.isoformat()
        assert value["completeness"] == "COMPLETE"
        digest, blob = worker.packed(value)
        assert digest == hashlib.sha256(blob).hexdigest()
        requests.post(endpoint + "/seed", data=blob, timeout=10).raise_for_status()

        selected = mapping()
        store = publish_store.AppPublisherStore(
            "https://" + "a" * 20 + ".supabase.co/functions/v1/private-app-publisher",
            "app_publish_" + "a" * 64,
            "a" * 20,
            session=LoopbackTransport(),
        )
        candidate = app_feed.build(
            blob, digest, config, selected, as_of=CAPTURED
        )
        result = store.publish(candidate, selected)
        document = app_feed.canonical(candidate)
        assert result["sha256"] == hashlib.sha256(document.encode()).hexdigest()
        assert result["captured_at"] == candidate["captured_at"]
        assert result["status"] == "PUBLISHED"

        # A well-formed payload whose prices were altered never publishes.
        tampered = app_feed.canonical(
            {
                **candidate,
                "rows": [
                    {
                        **candidate["rows"][0],
                        "display_price_decimal": "99.99",
                        "observed_price_decimal": "99.99",
                        "observations": [
                            {
                                **candidate["rows"][0]["observations"][0],
                                "price_decimal": "99.99",
                            }
                        ],
                    },
                    *candidate["rows"][1:],
                ],
            }
        )
        rejected = False
        try:
            sent = store.publish(json.loads(tampered), selected)
            raise AssertionError("Altered candidate accepted: " + sent["status"])
        except worker.AcquisitionError as error:
            rejected = str(error) == "PUBLISH_GATEWAY_REJECTED"
        assert rejected
        return {
            "ok": True,
            "scope": "SYNTHETIC_LOOPBACK_TRANSPORT",
            "python_builder_accepted": True,
            "exact_document_hash_verified": True,
            "altered_candidate_rejected": True,
            "live_services_accessed": False,
            "genuine_data_or_ledgers_used": False,
        }
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            if server.stdout:
                server.stdout.close()


if __name__ == "__main__":
    try:
        result = run()
    except Exception as error:
        result = {"ok": False, "error_category": type(error).__name__}
    print(json.dumps(result))
    raise SystemExit(0 if result["ok"] else 1)

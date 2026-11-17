#!/usr/bin/env python3
"""Synthetic Python projection -> HTTP -> Deno boundary; no live services."""

import json
from pathlib import Path
import select
import subprocess
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation/managed"))
sys.path.insert(0, str(ROOT / "automation/managed/tests"))
import dividend_feed
import projection_store
import worker
from test_dividend_feed import archive, config, index, page, CAPTURED


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
                str(ROOT / "tests/projection_publisher_fixture.ts"),
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

        digest, blob = archive(
            [
                (
                    2026,
                    page(
                        ("ALPHA", "175,00", "4,85 %", "25/03/2026",
                         "08/04/2026", "Ordinaire", "Annuel"),
                        ("BETA", "12,50", "2,1 %", "",
                         "23/09/2026 – 29/09/2026", "Ordinaire", "Annuel"),
                    ),
                )
            ]
        )
        requests.post(endpoint + "/seed", data=blob, timeout=10).raise_for_status()
        projection = dividend_feed.build(
            blob, digest, config(), index(), as_of=CAPTURED
        )
        document = dividend_feed.canonical(projection)
        publisher = projection_store.ProjectionPublisher(
            "https://" + "a" * 20 + ".supabase.co/functions/v1/private-projection-publisher",
            "proj_publish_" + "a" * 64,
            "a" * 20,
            session=LoopbackTransport(),
        )
        result = publisher.publish(document)
        assert result["status"] == "PUBLISHED"
        assert result["kind"] == "dividends"
        assert result["records"] == 2

        # A document the boundary itself can reject (invalid calendar date).
        broken = json.loads(document)
        broken["rows"][0]["ex_date"] = "2026-02-30"
        rejected = False
        try:
            publisher.publish(dividend_feed.canonical(broken))
            raise AssertionError("Invalid projection accepted")
        except worker.AcquisitionError as error:
            rejected = str(error) == "PROJECTION_GATEWAY_REJECTED"
        assert rejected
        return {
            "ok": True,
            "scope": "SYNTHETIC_LOOPBACK_TRANSPORT",
            "python_projection_accepted": True,
            "exact_document_hash_verified": True,
            "invalid_projection_rejected": True,
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

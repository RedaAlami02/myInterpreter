#!/usr/bin/env python3
"""Synthetic Python collector -> HTTP -> Deno gateway; no production credentials."""

import copy
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
from archive_store import ArchiveGatewayStore
import market_collect
from test_market_frame import body, recipe, CAPTURED
import worker


def run():
    server = None
    spool = tempfile.TemporaryDirectory(prefix="archive-transport-fixture-")
    try:
        server = subprocess.Popen(
            [
                "deno",
                "run",
                "--no-config",
                "--no-remote",
                "--no-npm",
                "--allow-net=127.0.0.1",
                str(ROOT / "tests/archive_gateway_fixture.ts"),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if not select.select([server.stdout], [], [], 15)[0]:
            raise RuntimeError("LOCAL_FIXTURE_NOT_READY")
        port = json.loads(server.stdout.readline())["port"]

        class LoopbackTransport:
            def post(self, _validated_url, **kwargs):
                # Explicit fixture injection only; production URL checks stay intact.
                return requests.post("http://127.0.0.1:" + str(port), **kwargs)

        store = ArchiveGatewayStore(
            "https://" + "a" * 20 + ".supabase.co/functions/v1/private-market-archive",
            "arc_write_" + "a" * 64,
            "a" * 20,
            session=LoopbackTransport(),
            spool_dir=spool.name,
        )
        config = {
            "contract": "private-market-config/v2",
            "provider_namespace": "feed_0123456789abcdef",
            "recipe": recipe(),
        }
        slot = "2026-10-27T14:00:00+00:00"
        value = market_collect.envelope(
            config,
            json.dumps(body()).encode(),
            CAPTURED,
            slot,
            execution="CURRENT_ACQUISITION",
        )
        # Fixed test clock on BOTH fixture sides. No saved/genuine observations used.
        value["completed_at"] = CAPTURED.isoformat()
        assert value["completeness"] == "COMPLETE"
        assert store.complete(config["provider_namespace"], "quotes", slot) is False
        digest = store.save(value)
        assert digest == worker.packed(value)[0]
        assert store.complete(config["provider_namespace"], "quotes", slot) is True
        assert store.save(value) == digest
        partial = body()
        partial["quotes"].pop()
        other_config = {**config, "provider_namespace": "feed_1111111111111111"}
        incomplete = market_collect.envelope(
            other_config,
            json.dumps(partial).encode(),
            CAPTURED,
            slot,
            execution="CURRENT_ACQUISITION",
        )
        incomplete["completed_at"] = CAPTURED.isoformat()
        assert incomplete["completeness"] == "INCOMPLETE"
        store.save(incomplete)
        assert (
            store.complete(other_config["provider_namespace"], "quotes", slot) is False
        )
        tampered = copy.deepcopy(value)
        tampered["captures"][0]["sha256"] = "b" * 64
        try:
            store.save(tampered)
            raise AssertionError("Tampered archive accepted")
        except worker.AcquisitionError as error:
            assert str(error) == "ARCHIVE_GATEWAY_REJECTED"
        replay = {**value, "execution": "RECORDED_REPLAY"}
        try:
            store.save(replay)
            raise AssertionError("Replay escaped isolation")
        except worker.AcquisitionError as error:
            assert str(error) == "REMOTE_ARCHIVE_REQUIRES_CURRENT_ACQUISITION"
        return {
            "ok": True,
            "scope": "SYNTHETIC_LOOPBACK_TRANSPORT",
            "complete_archive_verified": True,
            "incomplete_evidence_retained_without_complete_slot": True,
            "exact_retry_verified": True,
            "tampered_capture_rejected": True,
            "replay_rejected": True,
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
        spool.cleanup()


if __name__ == "__main__":
    try:
        result = run()
    except Exception as error:
        result = {"ok": False, "error_category": type(error).__name__}
    print(json.dumps(result))
    raise SystemExit(0 if result["ok"] else 1)

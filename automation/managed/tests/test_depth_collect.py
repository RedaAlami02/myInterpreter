import copy
from datetime import timedelta
import gzip, json
from pathlib import Path
import sys, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import depth_collect as collector
from market_frame import FrameError
import worker
from test_depth_frame import NOW, body, spec


def config():
    return {
        "contract": "private-depth-config/v2",
        "provider_namespace": "feed_0123456789abcdef",
        "expected_source_identities": ["A", "B"],
        "request_template": {"url": "https://example.invalid", "body": {"target": ""}},
        "request_identity_paths": [["target"]],
        "spec": spec(),
    }


class DepthCollectorTests(unittest.TestCase):
    def capture(self, recipe, *_):
        data = body()
        data["summary"]["symbol"] = recipe["body"]["target"]
        return json.dumps(data).encode(), NOW

    def run_batch(self, cfg=None, fetcher=None, seconds=80):
        return collector.acquire(
            cfg or config(),
            worker.scheduled_slot(NOW, "depth"),
            fetcher=fetcher or self.capture,
            clock=lambda: NOW,
            pause=lambda _: None,
            seconds=seconds,
        )

    def test_complete_batch_preserves_each_raw_response_and_identity(self):
        result = self.run_batch()
        self.assertEqual(result["completeness"], "COMPLETE")
        self.assertEqual(len(result["captures"]), 2)
        self.assertEqual(len(result["depth_frames"]), 2)
        self.assertNotEqual(
            result["captures"][0]["capture_id"], result["captures"][1]["capture_id"]
        )
        self.assertFalse(result["prediction_eligible"])

    def test_request_template_is_not_mutated_between_instruments(self):
        cfg = config()
        before = copy.deepcopy(cfg)
        self.run_batch(cfg)
        self.assertEqual(cfg, before)

    def test_failed_request_is_partial_and_successful_raw_is_preserved(self):
        def fetch(recipe, *args):
            if recipe["body"]["target"] == "B":
                raise worker.AcquisitionError("NETWORK_FAILURE")
            return self.capture(recipe, *args)

        value = self.run_batch(fetcher=fetch)
        self.assertEqual(value["completeness"], "INCOMPLETE")
        self.assertEqual(len(value["captures"]), 1)
        self.assertEqual(value["depth_manifest"]["entries"][1]["status"], "FAILED")

    def test_security_mismatch_keeps_raw_but_rejects_snapshot(self):
        value = self.run_batch(fetcher=lambda *_: (json.dumps(body()).encode(), NOW))
        self.assertEqual(len(value["captures"]), 2)
        self.assertEqual(len(value["depth_frames"]), 1)
        self.assertEqual(value["completeness"], "INCOMPLETE")

    def test_parse_failure_keeps_raw_digest_and_time_in_manifest(self):
        def malformed(recipe, *args):
            raw, captured = self.capture(recipe, *args)
            data = json.loads(raw)
            data["summary"]["last"] = "broken"
            return json.dumps(data).encode(), captured

        cfg = config()
        cfg["spec"]["summary_fields"]["last_trade_price_decimal"] = {
            "path": ["last"], "type": "decimal", "optional": True,
            "blank_is_null": True,
        }
        value = self.run_batch(cfg, fetcher=malformed)
        self.assertEqual(value["completeness"], "INCOMPLETE")
        self.assertEqual(len(value["captures"]), 2)
        self.assertEqual(value["depth_frames"], [])
        for entry, capture in zip(value["depth_manifest"]["entries"], value["captures"]):
            self.assertEqual(entry["raw_sha256"], capture["sha256"])
            self.assertEqual(entry["captured_at"], capture["received_at"])
            self.assertEqual(entry["error_code"], "INVALID_NUMBER")

    def test_deadline_does_not_forge_unattempted_snapshots(self):
        result = self.run_batch(seconds=-1)
        self.assertEqual(result["depth_manifest"]["attempted"], 0)
        self.assertEqual(len(result["depth_manifest"]["missing_identities"]), 2)
        self.assertEqual(result["completeness"], "INCOMPLETE")
        self.assertEqual(result["acquisition_summary"]["stop_reason"], "TIME_BUDGET")
        self.assertEqual(result["acquisition_summary"]["unattempted"], 2)

    def test_default_budget_covers_measured_sequential_universe(self):
        cfg = config()
        cfg['expected_source_identities'] = [str(i) for i in range(81)]
        elapsed = [0.0]
        def pause(seconds): elapsed[0] += seconds
        def fetch(recipe, *args):
            elapsed[0] += 0.75
            return self.capture(recipe, *args)
        with patch.object(collector.time, 'monotonic', side_effect=lambda: elapsed[0]):
            result = collector.acquire(cfg, worker.scheduled_slot(NOW, 'depth'),
                fetcher=fetch, clock=lambda: NOW, pause=pause)
        self.assertGreater(elapsed[0], 80)
        self.assertLess(elapsed[0], 120)
        self.assertEqual(result['completeness'], 'COMPLETE')
        self.assertEqual(result['acquisition_summary']['unattempted'], 0)
        self.assertEqual(result['acquisition_summary']['stop_reason'], 'UNIVERSE_ATTEMPTED')

    def test_transport_failure_is_counted_separately_from_unattempted(self):
        def fetch(*args): raise worker.AcquisitionError('NETWORK_FAILURE')
        result = self.run_batch(fetcher=fetch)
        self.assertEqual(result['acquisition_summary']['failed'], 2)
        self.assertEqual(result['acquisition_summary']['unattempted'], 0)
        self.assertEqual(result['completeness'], 'INCOMPLETE')

    def test_invalid_identity_path_rejected_before_any_fetch(self):
        cfg = config()
        cfg["request_identity_paths"] = [["does_not_exist"]]
        with self.assertRaises(FrameError):
            self.run_batch(cfg)

    def test_manifest_and_raw_survive_storage_and_restart(self):
        value = self.run_batch()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "isolated.sqlite"
            store = worker.SQLiteStore(path)
            digest = store.save(value)
            store.db.close()
            store = worker.SQLiteStore(path)
            saved = json.loads(
                gzip.decompress(
                    store.db.execute(
                        "SELECT raw FROM attempts WHERE digest=?", (digest,)
                    ).fetchone()[0]
                )
            )
            self.assertEqual(
                saved["depth_manifest"]["manifest_sha256"],
                value["depth_manifest"]["manifest_sha256"],
            )
            self.assertEqual(
                bytes.fromhex(saved["captures"][0]["raw_hex"]), json.dumps(body()).encode()
            )
            self.assertTrue(
                store.complete(
                    config()["provider_namespace"], "depth", worker.scheduled_slot(NOW, "depth")
                )
            )
            store.db.close()

    def test_current_acquisition_cannot_bypass_session_window(self):
        closed = NOW.replace(hour=22)
        with self.assertRaisesRegex(FrameError, "OUTSIDE_WINDOW_OR_WRONG_SLOT"):
            collector.acquire(
                config(),
                closed.isoformat(),
                clock=lambda: closed,
                fetcher=self.capture,
                pause=lambda _: None,
            )


if __name__ == "__main__":
    unittest.main()

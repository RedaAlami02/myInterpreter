import copy
from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app_feed
import market_collect
import worker
from test_market_frame import body, recipe, CAPTURED


def config():
    return {
        "contract": "private-market-config/v2",
        "provider_namespace": "feed_0123456789abcdef",
        "recipe": recipe(),
    }


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
        "provider_namespace": config()["provider_namespace"],
        "stocks": stocks,
        "indices": [
            {
                "source_identity": "INDEX_MAIN",
                "company_id": None,
                "asset_key": "index:MAIN",
                "c_name": "Main index",
                "symbol": "MAIN",
            }
        ],
    }


def archive(data=None, cfg=None, execution="CURRENT_ACQUISITION", captured=CAPTURED):
    value = market_collect.envelope(
        cfg or config(),
        json.dumps(data or body()).encode(),
        captured,
        captured.replace(minute=0, second=0, microsecond=0).isoformat(),
        execution=execution,
    )
    value["completed_at"] = captured.isoformat()
    digest, blob = worker.packed(value)
    return digest, blob


def candidate(
    data=None,
    cfg=None,
    as_of=CAPTURED,
    execution="CURRENT_ACQUISITION",
    captured=CAPTURED,
):
    digest, blob = archive(data, cfg, execution, captured)
    return app_feed.build(blob, digest, cfg or config(), mapping(), as_of=as_of)


class AppFeedTests(unittest.TestCase):
    def test_exact_decimal_mapping_and_index_remain_shadow_only(self):
        value = candidate()
        self.assertEqual(len(value["rows"]), 3)
        self.assertEqual(
            [r["asset_key"] for r in value["rows"]],
            ["company:a", "company:b", "index:MAIN"],
        )
        self.assertEqual(value["rows"][0]["display_price_decimal"], "10.50")
        self.assertEqual(value["rows"][0]["reported_time"]["timezone"], "UNKNOWN")
        self.assertEqual(value["rows"][2]["instrument_type"], "INDEX")
        self.assertEqual(value["mode"], "SHADOW_ONLY")
        self.assertFalse(value["prediction_eligible"])
        self.assertFalse(value["portfolio_valuation_eligible"])

    def test_no_stock_average_or_catalog_fallback_for_missing_index_or_stock(self):
        data = body()
        data["quotes"].pop()
        data["indices"] = []
        value = candidate(data)
        self.assertEqual(
            [r["status"] for r in value["rows"]],
            ["REPORTED_DATE_ONLY", "MISSING_QUOTE", "MISSING_QUOTE"],
        )
        self.assertIsNone(value["rows"][1]["observed_price_decimal"])
        self.assertEqual(value["rows"][1]["observations"], [])
        self.assertIsNone(value["rows"][1]["captured_at"])
        self.assertEqual(value["acquisition_completeness"], "INCOMPLETE")

    def test_past_capture_keeps_observed_values_but_never_a_current_display_price(self):
        value = candidate(as_of=CAPTURED + timedelta(days=1))
        self.assertEqual(value["coverage"], {"STALE_CAPTURE_DATE": 3})
        self.assertEqual(value["rows"][0]["observed_price_decimal"], "10.50")
        self.assertTrue(all(r["display_price_decimal"] is None for r in value["rows"]))

    def test_intraday_staleness_is_explicit(self):
        self.assertEqual(
            candidate(as_of=CAPTURED + timedelta(seconds=1201))["coverage"],
            {"STALE_CAPTURE": 3},
        )

    def test_duplicate_source_observations_retained_and_no_arbitrary_price_chosen(self):
        data = body()
        data["quotes"].append(dict(data["quotes"][0], p="11,00"))
        row = candidate(data)["rows"][0]
        self.assertEqual(row["status"], "CONFLICTING_QUOTES")
        self.assertIsNone(row["display_price_decimal"])
        self.assertEqual(
            [r["price_decimal"] for r in row["observations"]], ["10.50", "11.00"]
        )

    def test_source_day_staleness_not_hidden_by_fresh_http_receipt(self):
        data = body()
        data["quotes"][0]["time"] = "26/10/2026 14:00:00"
        self.assertEqual(
            candidate(data)["rows"][0]["status"], "STALE_OR_MISSING_SOURCE_DATE"
        )

    def test_future_cutoff_or_naive_cutoff_rejected(self):
        for stamp in [CAPTURED - timedelta(seconds=1), CAPTURED.replace(tzinfo=None)]:
            with self.assertRaisesRegex(app_feed.FrameError, "INVALID_APP_CUTOFF"):
                candidate(as_of=stamp)

    def test_no_forward_data_leak_through_source_event(self):
        cfg = config()
        cfg["recipe"]["views"]["quotes"]["fields"]["source_event_at"] = {
            "path": ["event"],
            "type": "aware_time",
        }
        data = body()
        for row in data["quotes"]:
            row["event"] = (CAPTURED + timedelta(seconds=1)).isoformat()
        value = candidate(data, cfg)
        self.assertEqual(
            [r["status"] for r in value["rows"][:2]], ["MISSING_QUOTE"] * 2
        )

    def test_old_source_event_ages_after_capture_without_becoming_fresh(self):
        cfg = config()
        cfg["recipe"]["max_event_age_seconds"] = 60
        cfg["recipe"]["views"]["quotes"]["fields"]["source_event_at"] = {
            "path": ["event"],
            "type": "aware_time",
        }
        data = body()
        for row in data["quotes"]:
            row["event"] = (CAPTURED - timedelta(seconds=50)).isoformat()
        self.assertEqual(
            candidate(data, cfg, as_of=CAPTURED + timedelta(seconds=11))["rows"][0][
                "status"
            ],
            "STALE_SOURCE_EVENT",
        )

    def test_wrong_namespace_universe_and_ambiguous_company_mapping_rejected(self):
        for mode in ["namespace", "universe", "company", "index"]:
            selected = mapping()
            if mode == "namespace":
                selected["provider_namespace"] = "feed_1111111111111111"
            if mode == "universe":
                selected["stocks"].pop()
            if mode == "company":
                selected["stocks"][1]["asset_key"] = "company:a"
            if mode == "index":
                selected["indices"][0]["company_id"] = "a"
            with self.assertRaises(app_feed.FrameError):
                app_feed.validate_mapping(selected, config())

    def test_archive_hash_raw_hash_and_forged_normalization_each_rejected(self):
        digest, blob = archive()
        with self.assertRaisesRegex(app_feed.FrameError, "ARCHIVE_HASH_MISMATCH"):
            app_feed.build(blob, "b" * 64, config(), mapping(), as_of=CAPTURED)
        import gzip

        original = json.loads(gzip.decompress(blob))
        for mode in ["raw", "normalized"]:
            value = copy.deepcopy(original)
            if mode == "raw":
                value["captures"][0]["sha256"] = "a" * 64
            else:
                value["market_frame"]["views"]["quotes"][0]["price_decimal"] = "999.99"
            altered_digest, altered = worker.packed(value)
            with self.assertRaises(app_feed.FrameError):
                app_feed.build(
                    altered, altered_digest, config(), mapping(), as_of=CAPTURED
                )

    def test_replay_keeps_execution_and_original_observation_identity(self):
        replay = candidate(execution="RECORDED_REPLAY")
        self.assertEqual(replay["source_execution"], "RECORDED_REPLAY")
        self.assertEqual(
            replay["rows"][0]["observations"], candidate()["rows"][0]["observations"]
        )

    def test_legacy_replay_requires_explicit_metadata_only_derivation(self):
        import gzip

        _, blob = archive(execution="RECORDED_REPLAY")
        value = json.loads(gzip.decompress(blob))
        del value["captures"][0]["capture_id"]
        for rows in value["market_frame"]["views"].values():
            for row in rows:
                del row["observation_id"]
        digest, original = worker.packed(value)
        with self.assertRaises(app_feed.FrameError):
            app_feed.build(original, digest, config(), mapping(), as_of=CAPTURED)
        result = app_feed.build(
            original,
            digest,
            config(),
            mapping(),
            as_of=CAPTURED,
            allow_legacy_replay_ids=True,
        )
        self.assertEqual(result["identity_evidence"], "REPLAY_IDS_EXPLICITLY_DERIVED")
        self.assertEqual(result["source_execution"], "RECORDED_REPLAY")
        self.assertEqual(json.loads(gzip.decompress(original)), value)
        value["execution"] = "CURRENT_ACQUISITION"
        digest, original = worker.packed(value)
        with self.assertRaises(app_feed.FrameError):
            app_feed.build(
                original,
                digest,
                config(),
                mapping(),
                as_of=CAPTURED,
                allow_legacy_replay_ids=True,
            )
        value["execution"] = "RECORDED_REPLAY"
        value["market_frame"]["views"]["quotes"][0]["price_decimal"] = "999.99"
        digest, altered = worker.packed(value)
        with self.assertRaises(app_feed.FrameError):
            app_feed.build(
                altered,
                digest,
                config(),
                mapping(),
                as_of=CAPTURED,
                allow_legacy_replay_ids=True,
            )

    def test_candidate_hash_stable_for_same_archive_mapping_and_cutoff(self):
        self.assertEqual(
            candidate()["candidate_sha256"], candidate()["candidate_sha256"]
        )

    def test_isolated_store_retry_restart_equal_time_conflict_and_old_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "feed.sqlite"
            store = app_feed.IsolatedFeedStore(path, {config()["provider_namespace"]})
            value = candidate()
            self.assertEqual(store.save(value), "STORED")
            self.assertEqual(store.save(value), "ALREADY_STORED")
            conflict = candidate(as_of=CAPTURED + timedelta(seconds=1))
            with self.assertRaisesRegex(
                app_feed.FrameError, "EQUAL_TIME_FEED_CONFLICT"
            ):
                store.save(conflict)
            newer = candidate(
                captured=CAPTURED + timedelta(seconds=1),
                as_of=CAPTURED + timedelta(seconds=1),
            )
            store.save(newer)
            with self.assertRaisesRegex(app_feed.FrameError, "OLDER_FEED_REJECTED"):
                store.save(value)
            store.db.close()
            restarted = app_feed.IsolatedFeedStore(
                path, {config()["provider_namespace"]}
            )
            self.assertEqual(
                restarted.db.execute("SELECT count(*) FROM shadow_feed").fetchone()[0],
                1,
            )
            self.assertEqual(
                restarted.db.execute(
                    "SELECT candidate_digest FROM shadow_feed"
                ).fetchone()[0],
                newer["candidate_sha256"],
            )
            restarted.db.close()


if __name__ == "__main__":
    unittest.main()

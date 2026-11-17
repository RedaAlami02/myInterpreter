import base64
import copy
import gzip
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import history_delta as delta
import import_versioned_history as v1
import test_import_versioned_history as fixtures


def fixture_version(parent, bars=None, completed="2026-10-27T08:00:00+00:00"):
    """Synthetic source versions only; no real market or prediction writes."""
    current = copy.deepcopy(parent)
    capture = current["captures"][0]
    raw = gzip.decompress(base64.b64decode(capture[5]))
    bars = copy.deepcopy(
        bars if bars is not None else v1.raw_rows(raw, current["manifest"]["bindings"])
    )
    raw = v1.canonical({"rows": bars})
    request = gzip.decompress(base64.b64decode(capture[6]))
    receipt = v1.read_json(gzip.decompress(base64.b64decode(capture[7])))
    receipt.update(
        sha256=v1.digest(raw), request_sha256=v1.digest(request), completed_at=completed
    )
    receipt = v1.canonical(receipt)
    capture[:] = [
        capture[0],
        completed,
        v1.digest(raw),
        v1.digest(request),
        v1.digest(receipt),
        *[
            base64.b64encode(gzip.compress(v, mtime=0)).decode()
            for v in (raw, request, receipt)
        ],
    ]
    rows = []
    for ordinal, bar in enumerate(bars):
        day, label, close, warnings = v1.native_projection(
            bar, current["manifest"]["bindings"]
        )
        identity = v1.digest(
            v1.canonical(
                [current["manifest"]["namespace"], capture[0], capture[2], ordinal]
            )
        )
        rows.append([capture[0], ordinal, identity, day, label, close, bar, warnings])
    current["rows"] = rows
    current["manifest"].update(
        row_count=len(rows),
        rows_sha256=v1.digest(v1.canonical(rows)),
        captures_sha256=v1.digest(v1.canonical(current["captures"])),
    )
    current["batch_id"] = v1.digest(v1.canonical(current["manifest"]))
    v1.validate(current)
    return current


class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HistoryImportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.parent = self.fixture.prepare()
        self.bars = [copy.deepcopy(r[6]) for r in self.parent["rows"]]
        self.new_bar = dict(
            self.bars[-1], day="2026-10-23 00:00:00", close=127, high=130
        )
        self.current = fixture_version(self.parent, self.bars + [self.new_bar])

    def test_delta_keeps_complete_raw_membership_and_only_materializes_new_value(self):
        result = delta.plan_delta(self.parent, self.current)
        self.assertEqual(result["manifest"]["counts"]["source_observations"], 3)
        self.assertEqual(result["manifest"]["counts"]["delta_projection_rows"], 1)
        self.assertEqual(
            result["manifest"]["counts"]["inherited_economic_occurrences"], 2
        )
        self.assertEqual(len(result["full_source"]["rows"]), 3)
        self.assertEqual(result["delta_rows"][0][3], "2026-10-23")
        self.assertNotEqual(self.parent["rows"][0][2], self.current["rows"][0][2])
        delta.validate_delta(result, self.parent)

    def test_price_conflicts_and_identical_occurrence_multiplicity_are_preserved(self):
        parent = fixture_version(self.parent, [self.bars[0], self.bars[0]])
        current = fixture_version(parent, [self.bars[0]] * 3)
        result = delta.plan_delta(parent, current)
        self.assertEqual(len(result["delta_rows"]), 1)
        self.assertEqual(len({r[2] for r in result["full_source"]["rows"]}), 3)
        raw = gzip.decompress(base64.b64decode(result["full_source"]["captures"][0][5]))
        self.assertEqual(len(v1.raw_rows(raw, parent["manifest"]["bindings"])), 3)

    def test_changed_ohlc_volume_or_extra_native_field_is_a_new_payload(self):
        for update in (
            {"volume": 987},
            {"high": 999},
            {"native_revision_field": "revised"},
        ):
            with self.subTest(update=update):
                bars = copy.deepcopy(self.bars)
                bars[0].update(update)
                result = delta.plan_delta(
                    self.parent, fixture_version(self.parent, bars)
                )
                self.assertEqual(len(result["delta_rows"]), 1)
                self.assertEqual(
                    result["manifest"]["counts"][
                        "changed_existing_instrument_date_keys"
                    ],
                    1,
                )
                self.assertEqual(result["delta_rows"][0][5], self.parent["rows"][0][5])

    def test_rolling_window_removal_is_not_a_delete_instruction(self):
        original = v1.canonical(self.parent)
        result = delta.plan_delta(
            self.parent, fixture_version(self.parent, [self.bars[0]])
        )
        self.assertEqual(len(result["delta_rows"]), 0)
        self.assertEqual(result["manifest"]["counts"]["absent_from_current_capture"], 1)
        self.assertEqual(v1.canonical(self.parent), original)
        self.assertFalse(delta.summary(result)["old_observations_deleted"])

    def test_same_payload_with_later_capture_is_not_a_second_economic_value(self):
        result = delta.plan_delta(self.parent, fixture_version(self.parent))
        self.assertEqual(result["delta_rows"], [])
        self.assertNotEqual(
            self.parent["captures"][0][1], result["full_source"]["captures"][0][1]
        )
        self.assertEqual(
            self.parent["captures"][0][2], result["full_source"]["captures"][0][2]
        )

    def test_delta_tampering_and_wrong_parent_are_rejected(self):
        result = delta.plan_delta(self.parent, self.current)
        altered = copy.deepcopy(result)
        altered["delta_rows"] = []
        with self.assertRaises(ValueError):
            delta.validate_delta(altered, self.parent)
        other = fixture_version(self.parent, [self.bars[0]])
        with self.assertRaises(ValueError):
            delta.validate_delta(result, other)

    def test_reconstruction_preserves_all_exact_source_ids_prices_and_bytes(self):
        result = delta.reconstruct_full(
            self.current["manifest"], self.current["captures"]
        )
        self.assertEqual(v1.canonical(result), v1.canonical(self.current))

    def test_wrong_namespace_binding_or_earlier_capture_cannot_silently_substitute(
        self,
    ):
        earlier = fixture_version(self.parent, completed="2026-10-25T08:00:00+00:00")
        with self.assertRaises(ValueError):
            delta.plan_delta(self.parent, earlier)
        altered = copy.deepcopy(self.current)
        altered["manifest"]["provider"] = "different-source"
        altered["batch_id"] = v1.digest(v1.canonical(altered["manifest"]))
        with self.assertRaises(ValueError):
            delta.plan_delta(self.parent, altered)

    def test_typed_numeric_equivalence_does_not_lose_raw_identity(self):
        a = copy.deepcopy(self.parent["rows"][0])
        b = copy.deepcopy(a)
        a[6]["volume"] = 100
        b[6]["volume"] = 100.0
        ns = self.parent["manifest"]["namespace"]
        self.assertEqual(delta.value_identity(ns, a), delta.value_identity(ns, b))
        b[6]["volume"] = "100"
        self.assertNotEqual(delta.value_identity(ns, a), delta.value_identity(ns, b))


if __name__ == "__main__":
    unittest.main()

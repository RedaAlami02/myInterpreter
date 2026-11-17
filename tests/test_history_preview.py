import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from export_history_preview import build_projection, write_projection
from import_versioned_history import canonical, digest
import test_import_versioned_history as fixtures
import serve_history_preview as server

ROOT = Path(__file__).resolve().parents[1]


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HistoryImportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.bundle = self.fixture.prepare()

    def test_conflicting_prices_preserved_with_no_plotted_selection(self):
        series = build_projection(self.bundle)["FIX"]
        (point,) = series["points"]
        self.assertEqual(point["status"], "CONFLICTING_CLOSES")
        self.assertIsNone(point["close_decimal"])
        self.assertEqual(
            {p["close_decimal"] for p in point["candidates"]},
            {"123.45000000001", "124"},
        )
        self.assertEqual(series["duplicate_days"], 1)
        self.assertTrue(series["not_live"])
        self.assertEqual(series["original_observation_times"], "UNKNOWN")

    def test_no_raw_envelope_or_native_metadata_is_exposed(self):
        raw = canonical(build_projection(self.bundle))
        for forbidden in [
            "bindings",
            "rows_path",
            "raw_row_json",
            "request_identity",
            "raw_gzip",
            "source_daily_label",
            "provider",
            "namespace",
            "source_ordinal",
            "observed_at",
        ]:
            self.assertNotIn(('"' + forbidden + '"').encode(), raw)

    def test_output_manifest_pins_all_series_and_export_refuses_overwrite(self):
        out = self.fixture.folder / "sanitized"
        result = write_projection(self.bundle, out)
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(
            result["manifest_sha256"], digest((out / "manifest.json").read_bytes())
        )
        for item in manifest["instruments"]:
            self.assertEqual(item["sha256"], digest((out / item["file"]).read_bytes()))
        with self.assertRaises(ValueError):
            write_projection(self.bundle, out)


class PhpHistoryPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "preview"
        self.directory.mkdir()
        self.ids = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(4)]

        def candidate(i, close):
            return {
                "observation_id": self.ids[i],
                "close_decimal": close,
                "quality_warnings": [],
            }

        self.series = {
            "contract": "daily-close-preview-v1",
            "version": "a" * 64,
            "symbol": "FIX",
            "kind": "SECURITY",
            "classification": "RETROSPECTIVE_SOURCE_HISTORY",
            "price_definition": "DAILY_CLOSE_CANDIDATE",
            "not_live": True,
            "original_observation_times": "UNKNOWN",
            "captured_at": "2026-10-26T08:00:00+00:00",
            "first_date": "2026-10-20",
            "last_date": "2026-10-23",
            "observation_count": 4,
            "duplicate_days": 1,
            "conflicting_days": 1,
            "points": [
                {
                    "date": "2026-10-20",
                    "status": "AVAILABLE",
                    "close_decimal": "123.45000000001",
                    "candidates": [candidate(0, "123.45000000001")],
                },
                {
                    "date": "2026-10-21",
                    "status": "CONFLICTING_CLOSES",
                    "close_decimal": None,
                    "candidates": [candidate(1, "124"), candidate(2, "125")],
                },
                {
                    "date": "2026-10-23",
                    "status": "AVAILABLE",
                    "close_decimal": "126",
                    "candidates": [candidate(3, "126")],
                },
            ],
        }
        self.filename = "s_" + digest(b"FIX")[:16] + ".json"
        self.write()

    def write(self):
        raw = canonical(self.series)
        (self.directory / self.filename).write_bytes(raw)
        item = {
            key: self.series[key]
            for key in (
                "symbol",
                "kind",
                "first_date",
                "last_date",
                "observation_count",
                "duplicate_days",
                "conflicting_days",
            )
        }
        item.update(file=self.filename, sha256=digest(raw))
        self.manifest = {
            "contract": "daily-close-preview-v1",
            "version": "a" * 64,
            "generated_at": "2026-10-26T09:00:00+00:00",
            "classification": "RETROSPECTIVE_SOURCE_HISTORY",
            "not_live": True,
            "original_observation_times": "UNKNOWN",
            "instruments": [item],
        }
        raw = canonical(self.manifest)
        (self.directory / "manifest.json").write_bytes(raw)
        self.pin = digest(raw)

    def call(self, **kwargs):
        request = dict(
            directory=str(self.directory), pin=self.pin, symbol="FIX", **kwargs
        )
        result = subprocess.run(
            ["php", str(ROOT / "tests/read_history_fixture.php")],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def render(self, query=None, configured=True):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(
                ("SUPABASE_", "APPWRITE_", "MARKET_", "MYINTERPRETER_HISTORY_")
            )
        }
        if configured:
            env.update(
                MYINTERPRETER_HISTORY_PREVIEW_DIR=str(self.directory),
                MYINTERPRETER_HISTORY_PREVIEW_SHA256=self.pin,
            )
        code = '$_SERVER["REQUEST_METHOD"]="GET"; $_GET=json_decode(stream_get_contents(STDIN),true); require "history-preview.php";'
        result = subprocess.run(
            ["php", "-d", "display_errors=1", "-r", code],
            cwd=ROOT,
            env=env,
            input=json.dumps(query or {"symbol": "FIX"}),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stderr, "")
        return result.stdout

    def api(self, query=None, configured=True, method="GET"):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(
                ("SUPABASE_", "APPWRITE_", "MARKET_", "MYINTERPRETER_HISTORY_")
            )
        }
        if configured:
            env.update(
                MYINTERPRETER_HISTORY_PREVIEW_DIR=str(self.directory),
                MYINTERPRETER_HISTORY_PREVIEW_SHA256=self.pin,
            )
        code = """
        $input=json_decode(stream_get_contents(STDIN),true);
        $_SERVER['REQUEST_METHOD']=$input['method']; $_GET=$input['query'];
        ob_start(); register_shutdown_function(function() {
            $body=ob_get_clean(); echo json_encode(['status'=>http_response_code() ?: 200,'body'=>json_decode($body,true)]);
        }); require 'handlers/recovered_history.php';
        """
        response = subprocess.run(
            ["php", "-d", "display_errors=1", "-r", code],
            cwd=ROOT,
            env=env,
            input=json.dumps({"query": query or {}, "method": method}),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(response.stderr, "")
        return json.loads(response.stdout)

    def test_exact_close_strings_unknown_times_and_date_range_survive(self):
        result = self.call()["result"]
        self.assertEqual(result["points"][0]["close_decimal"], "123.45000000001")
        self.assertEqual(result["original_observation_times"], "UNKNOWN")
        result = self.call(**{"from": "2026-10-21", "through": "2026-10-23"})["result"]
        self.assertEqual(
            [p["date"] for p in result["points"]], ["2026-10-21", "2026-10-23"]
        )

    def test_current_day_range_is_empty_without_older_price_fallback(self):
        result = self.call(**{"from": "2026-10-26", "through": "2026-10-26"})["result"]
        self.assertEqual(result["points"], [])
        self.assertEqual(result["range_status"], "NO_HISTORICAL_POINTS_IN_RANGE")

    def test_unknown_instrument_invalid_date_and_reversed_range_are_rejected(self):
        for overrides in (
            {"symbol": "../private"},
            {"from": "2026-02-30"},
            {"from": "2026-10-24", "through": "2026-10-23"},
        ):
            params = (
                dict(directory=str(self.directory), pin=self.pin, symbol="FIX")
                | overrides
            )
            result = subprocess.run(
                ["php", str(ROOT / "tests/read_history_fixture.php")],
                input=json.dumps(params),
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertFalse(json.loads(result.stdout)["ok"])

    def test_manifest_or_series_tampering_is_rejected_without_path_disclosure(self):
        (self.directory / self.filename).write_text("{}")
        result = self.call()
        self.assertFalse(result["ok"])
        self.assertNotIn(str(self.directory), json.dumps(result))
        self.write()
        (self.directory / "manifest.json").write_text("{}")
        self.assertFalse(self.call()["ok"])

    def test_native_metadata_and_incorrect_source_semantics_are_rejected(self):
        original = copy.deepcopy(self.series)
        for field, value in [
            ("provider", "private-metadata"),
            ("not_live", False),
            ("original_observation_times", "KNOWN"),
            ("version", "b" * 64),
            ("price_definition", "LIVE_PRICE"),
        ]:
            self.series = copy.deepcopy(original)
            self.series[field] = value
            self.write()
            self.assertFalse(self.call()["ok"])

    def test_duplicates_cannot_be_selected_or_changed_to_zero(self):
        self.series["points"][1]["status"] = "AVAILABLE"
        self.series["points"][1]["close_decimal"] = "124"
        self.write()
        self.assertFalse(self.call()["ok"])
        self.series["points"][1]["status"] = "CONFLICTING_CLOSES"
        self.series["points"][1]["close_decimal"] = None
        self.series["points"][0]["close_decimal"] = "0"
        self.series["points"][0]["candidates"][0]["close_decimal"] = "0"
        self.write()
        self.assertFalse(self.call()["ok"])

    def test_series_symlink_cannot_escape_export_directory(self):
        external = self.directory.parent / "outside.json"
        external.write_bytes((self.directory / self.filename).read_bytes())
        (self.directory / self.filename).unlink()
        (self.directory / self.filename).symlink_to(external)
        self.assertFalse(self.call()["ok"])

    def test_instrument_listing_does_not_expose_paths_or_file_hashes(self):
        result = self.call(operation="instruments")["result"]
        self.assertEqual(result[0]["symbol"], "FIX")
        self.assertNotIn("file", result[0])
        self.assertNotIn("sha256", result[0])

    def test_page_keeps_conflicting_day_as_chart_gap_and_labels_not_live(self):
        html = self.render()
        self.assertIn("Not live", html)
        self.assertIn("Available history through", html)
        self.assertIn("2 observations · review needed", html)
        self.assertEqual(html.count("<polyline "), 2)
        self.assertNotIn("private-metadata", html)

    def test_empty_and_unconfigured_pages_show_no_stale_price_or_secret(self):
        html = self.render(
            {"symbol": "FIX", "from": "2026-10-26", "through": "2026-10-26"}
        )
        self.assertIn("No unambiguous daily closes", html)
        self.assertNotIn("<polyline ", html)
        html = self.render(configured=False)
        self.assertIn("Historical preview is unavailable.", html)
        self.assertNotIn(str(self.directory), html)
        self.assertNotIn("Warning:", html)

    def test_inconsistent_daily_range_is_labeled_without_rewriting_the_close(self):
        self.series["points"][2]["candidates"][0]["quality_warnings"] = [
            "SOURCE_OHLC_INCONSISTENT"
        ]
        self.write()
        html = self.render()
        self.assertIn("Daily range needs review", html)
        self.assertIn("126", html)
        self.assertIn("Dates with multiple observations", html)

    def test_endpoint_is_disabled_without_explicit_pinned_configuration(self):
        result = self.api({"symbol": "FIX"}, configured=False)
        self.assertEqual(result["status"], 503)
        self.assertEqual(
            result["body"], {"error": "Historical preview is unavailable."}
        )
        self.assertNotIn(str(self.directory), json.dumps(result))

    def test_endpoint_preserves_exact_history_and_redacts_instrument_metadata(self):
        result = self.api({"symbol": "FIX"})
        self.assertEqual(result["status"], 200)
        self.assertEqual(
            result["body"]["points"][0]["close_decimal"], "123.45000000001"
        )
        result = self.api()
        self.assertTrue(result["body"]["not_live"])
        self.assertNotIn("file", result["body"]["instruments"][0])
        self.assertNotIn("sha256", result["body"]["instruments"][0])

    def test_endpoint_rejects_mutating_methods_and_unsupported_inputs(self):
        self.assertEqual(self.api(method="POST")["status"], 405)
        for query in (
            {"symbol": ["FIX"]},
            {"symbol": "FIX", "from": "invalid"},
            {"symbol": "FIX", "namespace": "unknown"},
            {"through": "2026-10-26"},
        ):
            with self.subTest(query=query):
                result = self.api(query)
                self.assertEqual(result["status"], 400)
                self.assertEqual(result["body"], {"error": "Invalid historical query."})


class LauncherTests(unittest.TestCase):
    def test_only_pinned_export_and_ordinary_settings_reach_loopback_server(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = b'{"synthetic":"export"}'
            (Path(folder) / "manifest.json").write_bytes(raw)
            argv = [
                "serve_history_preview.py",
                "--directory",
                folder,
                "--manifest-sha256",
                digest(raw),
                "--port",
                "8943",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.dict(
                    os.environ,
                    {
                        "SUPABASE_SECRET_KEY": "synthetic-secret",
                        "APPWRITE_API_KEY": "synthetic-secret",
                        "MARKET_ACTION_URL": "https://example.invalid",
                        "DATABASE_URL": "synthetic-private-dsn",
                    },
                ),
                patch.object(server.os, "execvpe") as execute,
            ):
                server.main()
            name, arguments, environment = execute.call_args.args
            self.assertEqual(name, "php")
            self.assertIn("127.0.0.1:8943", arguments)
            self.assertIn("display_errors=0", arguments)
            self.assertEqual(
                environment["MYINTERPRETER_HISTORY_PREVIEW_SHA256"], digest(raw)
            )
            self.assertFalse(
                any(
                    k in environment
                    for k in (
                        "SUPABASE_SECRET_KEY",
                        "APPWRITE_API_KEY",
                        "MARKET_ACTION_URL",
                        "DATABASE_URL",
                    )
                )
            )

    def test_bad_pin_refuses_launch_without_printing_private_path(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "manifest.json").write_text("{}")
            error = io.StringIO()
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "serve_history_preview.py",
                        "--directory",
                        folder,
                        "--manifest-sha256",
                        "0" * 64,
                    ],
                ),
                patch.object(server.os, "execvpe") as execute,
                contextlib.redirect_stderr(error),
            ):
                with self.assertRaises(SystemExit):
                    server.main()
            execute.assert_not_called()
            self.assertNotIn(folder, error.getvalue())


if __name__ == "__main__":
    unittest.main()

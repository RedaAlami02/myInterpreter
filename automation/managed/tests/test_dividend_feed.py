import gzip
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dividend_calendar
import dividend_feed
import worker

ROOT = Path(__file__).resolve().parents[3]
PROVIDER = "feed_0123456789abcdef"
CAPTURED = datetime(2026, 10, 28, 14, 10, tzinfo=timezone.utc)
HEADER = (
    "<tr><th>Émetteur</th><th>Montant (MAD)</th><th>Dividende %</th>"
    "<th>Détachement</th><th>Paiement</th><th>Type</th><th>Fréquence</th></tr>"
)


def config():
    return {"contract": "private-market-config/v2", "provider_namespace": PROVIDER}


def page(*rows):
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<html><body><table>{HEADER}{body}</table></body></html>"


def index(extra=None):
    data = {
        dividend_calendar.normalise_name("ALPHA"): "Alpha",
        dividend_calendar.normalise_name("BETA"): "Beta",
        dividend_calendar.normalise_name("GAMMA"): "Gamma",
        dividend_calendar.normalise_name("DELTA SA"): "Delta",
        dividend_calendar.normalise_name("XYZ"): "Exemple",
    }
    data.update(extra or {})
    return {
        "contract": "private-dividend-index/v1",
        "provider_namespace": PROVIDER,
        "index": data,
    }


def archive(pages, cfg=None, execution="CURRENT_ACQUISITION", completeness="COMPLETE"):
    cfg = cfg or config()
    captures, targets = [], []
    for position, (year, text) in enumerate(pages):
        raw = text.encode() if isinstance(text, str) else text
        digest = hashlib.sha256(raw).hexdigest()
        identity = hashlib.sha256(
            json.dumps(
                [cfg["provider_namespace"], digest, CAPTURED.isoformat()],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        captures.append(
            {
                "request_index": position,
                "capture_id": identity,
                "received_at": CAPTURED.isoformat(),
                "sha256": digest,
                "raw_hex": raw.hex(),
            }
        )
        targets.append(
            {"request_index": position, "year": year, "charset": "utf-8"}
        )
    value = {
        "contract": "private-acquisition/v2",
        "provider_namespace": cfg["provider_namespace"],
        "kind": "dividends",
        "slot": CAPTURED.replace(minute=0, second=0, microsecond=0).isoformat(),
        "completed_at": CAPTURED.isoformat(),
        "execution": execution,
        "completeness": completeness,
        "errors": [],
        "captures": captures,
        "targets": targets,
        "authority": "UNPROMOTED",
        "prediction_eligible": False,
    }
    return worker.packed(value)


def build(pages, idx=None, cfg=None, as_of=CAPTURED, **options):
    digest, blob = archive(pages, cfg, **options)
    return dividend_feed.build(
        blob, digest, cfg or config(), idx or index(), as_of=as_of
    )


class QualityParityTests(unittest.TestCase):
    def test_shared_php_dart_python_period_fixture(self):
        cases = json.loads(
            (ROOT / "tests/fixtures/dividend_periods.json").read_text()
        )
        for case in cases:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    dividend_calendar.quality_issue(case["row"]), case["issue"]
                )

    def test_managed_parser_matches_the_archival_parser(self):
        sys.path.insert(0, str(ROOT / "cloud_function/functions/dividends/src"))
        import div_parser

        sample = page(
            ("ALPHA", "175,00", "4,85 %", "25/03/2025", "08/04/2025", "Ordinaire", "Annuel"),
            ("BETA", "12,50", "2,1 %", "", "23/09/2026 – 29/09/2026", "Ordinaire", "Annuel"),
            ("GAMMA (GMT)", "—", "—", "", "23/09/2026", "Ordinaire", "Annuel"),
        )
        for year in (2025, 2026):
            self.assertEqual(
                dividend_calendar.parse_calendar(sample, year),
                div_parser.parse_calendar(sample, year),
            )

    def test_unrecognized_page_shape_raises_instead_of_returning_nothing(self):
        for broken in ["<html></html>", "<table><tr><td>only</td></tr></table>"]:
            with self.assertRaises(ValueError):
                dividend_calendar.parse_calendar(broken, 2026)


class CalendarProjectionTests(unittest.TestCase):
    def test_exact_amounts_dates_and_confirmation_are_preserved(self):
        value = build(
            [
                (
                    2026,
                    page(
                        ("ALPHA", "175,00", "4,85 %", "25/03/2026",
                         "08/04/2026", "Ordinaire", "Annuel"),
                        ("BETA", "12,50", "2,1 %", "",
                         "23/09/2026 – 29/09/2026", "Ordinaire", "Annuel"),
                        ("SOCIETE EXEMPLE (XYZ)", "—", "—", "", "01/10/2026",
                         "Exceptionnel", "Unique"),
                    ),
                )
            ]
        )
        self.assertEqual(value["contract"], "dividend-projection/v1")
        self.assertEqual(value["mode"], "PROJECTION_ONLY")
        self.assertEqual(value["years"], [2026])
        rows = {row["c_name"]: row for row in value["rows"]}
        self.assertEqual(
            (rows["Alpha"]["amount"], rows["Alpha"]["ex_date"],
             rows["Alpha"]["pay_date"], rows["Alpha"]["confirmed"]),
            (175.0, "2026-03-25", "2026-04-08", True),
        )
        self.assertEqual(
            (rows["Beta"]["amount"], rows["Beta"]["ex_date"],
             rows["Beta"]["pay_date"], rows["Beta"]["pay_date_end"],
             rows["Beta"]["confirmed"]),
            (12.5, None, "2026-09-23", "2026-09-29", False),
        )
        # A dash is missing evidence, never a zero or an invented amount.
        self.assertIsNone(rows["Exemple"]["amount"])
        self.assertEqual(rows["Exemple"]["type"], "Exceptionnel")
        self.assertFalse(value["prediction_eligible"])
        self.assertFalse(value["portfolio_valuation_eligible"])
        self.assertEqual(value["completeness"], "COMPLETE")
        self.assertEqual(
            value["candidate_sha256"], dividend_feed.fingerprint(
                {k: v for k, v in value.items() if k != "candidate_sha256"}
            )
        )

    def test_conflicting_periods_are_excluded_and_retained(self):
        value = build(
            [
                (
                    2027,
                    page(
                        ("ALPHA", "175,00", "1%", "25/03/2025",
                         "08/04/2025", "Ordinaire", "Annuel"),
                    ),
                )
            ]
        )
        self.assertEqual(value["rows"], [])
        self.assertEqual(len(value["excluded"]), 1)
        held = value["excluded"][0]
        self.assertEqual(held["issue"], "payment_year_mismatch")
        self.assertEqual(
            (held["c_name"], held["issuer"], held["amount"], held["ex_date"]),
            ("Alpha", "ALPHA", 175.0, "2025-03-25"),
        )

    def test_unmatched_issuers_are_retained_and_never_guessed(self):
        value = build(
            [
                (
                    2026,
                    page(
                        ("INCONNU", "9,00", "1%", "10/06/2026",
                         "20/06/2026", "Ordinaire", "Annuel"),
                    ),
                )
            ]
        )
        self.assertEqual(value["rows"], [])
        self.assertEqual(len(value["unmatched"]), 1)
        self.assertIsNone(value["unmatched"][0]["c_name"])
        self.assertEqual(value["unmatched"][0]["amount"], 9.0)
        self.assertEqual(value["coverage"]["by_year"]["2026"]["unmatched"], 1)

    def test_duplicate_spellings_collapse_to_the_most_complete_row(self):
        value = build(
            [
                (
                    2026,
                    page(
                        ("ALPHA", "54,00", "1%", "", "", "Ordinaire", "Annuel"),
                        ("ALPHA SA", "54,00", "1%", "12/07/2026",
                         "30/07/2026", "Ordinaire", "Annuel"),
                    ),
                )
            ]
        )
        self.assertEqual(len(value["rows"]), 1)
        row = value["rows"][0]
        self.assertEqual((row["c_name"], row["ex_date"], row["confirmed"]),
                         ("Alpha", "2026-07-12", True))

    def test_ticker_fallback_and_alias_resolution(self):
        value = build(
            [
                (
                    2026,
                    page(
                        ("SOCIETE INCONNUE (XYZ)", "8,00", "1%", "01/07/2026",
                         "10/07/2026", "Ordinaire", "Annuel"),
                        ("MAROC TELECOM (IAM)", "5,00", "1%", "02/07/2026",
                         "12/07/2026", "Ordinaire", "Annuel"),
                    ),
                )
            ]
        )
        names = {row["c_name"] for row in value["rows"]}
        self.assertEqual(names, {"Exemple", "IAM"})

    def test_archive_hash_capture_contract_and_replay_are_enforced(self):
        digest, blob = archive([(2026, page(
            ("ALPHA", "5,00", "1%", "01/07/2026", "10/07/2026", "Ordinaire", "Annuel"),
        ))])
        with self.assertRaisesRegex(ValueError, "ARCHIVE_HASH_MISMATCH"):
            dividend_feed.build(blob, "b" * 64, config(), index(), as_of=CAPTURED)
        original = json.loads(gzip.decompress(blob))
        for mode in ["raw", "capture", "target", "replay", "kind"]:
            value = json.loads(json.dumps(original))
            if mode == "raw":
                value["captures"][0]["sha256"] = "c" * 64
            if mode == "capture":
                value["captures"][0]["capture_id"] = "c" * 64
            if mode == "target":
                value["targets"][0]["request_index"] = 5
            if mode == "replay":
                value["execution"] = "RECORDED_REPLAY"
            if mode == "kind":
                value["kind"] = "quotes"
            altered_digest, altered = worker.packed(value)
            with self.assertRaises(ValueError):
                dividend_feed.build(
                    altered, altered_digest, config(), index(), as_of=CAPTURED
                )

    def test_invalid_index_and_cutoff_are_refused(self):
        digest, blob = archive([(2026, page())])
        for selected in [
            {**index(), "contract": "private-dividend-index/v0"},
            {**index(), "provider_namespace": "feed_1111111111111111"},
            {**index(), "index": {}},
            {**index(), "index": {"ALPHA": 5}},
        ]:
            with self.assertRaisesRegex(ValueError, "INVALID_DIVIDEND_INDEX"):
                dividend_feed.build(blob, digest, config(), selected, as_of=CAPTURED)
        with self.assertRaisesRegex(ValueError, "INVALID_PROJECTION_CUTOFF"):
            dividend_feed.build(
                blob, digest, config(), index(), as_of=CAPTURED - timedelta(seconds=1)
            )

    def test_undecodable_page_is_reported_not_guessed(self):
        value = build(
            [(2026, b"<table><tr><th>\xff</th></tr></table>")],
        )
        self.assertEqual(value["rows"], [])
        self.assertEqual(len(value["errors"]), 1)
        self.assertEqual(value["completeness"], "INCOMPLETE")
        self.assertEqual(value["coverage"]["by_year"]["2026"]["rows"], 0)

    def test_incomplete_acquisition_never_claims_completeness(self):
        value = build(
            [(2026, page(
                ("ALPHA", "5,00", "1%", "01/07/2026", "10/07/2026", "Ordinaire", "Annuel"),
            ))],
            completeness="INCOMPLETE",
        )
        self.assertEqual(len(value["rows"]), 1)
        self.assertEqual(value["completeness"], "INCOMPLETE")

    def test_multiple_years_are_kept_separate(self):
        value = build(
            [
                (2025, page(
                    ("ALPHA", "4,00", "1%", "01/07/2025", "10/07/2025",
                     "Ordinaire", "Annuel"),
                )),
                (2026, page(
                    ("ALPHA", "5,00", "1%", "01/07/2026", "10/07/2026",
                     "Ordinaire", "Annuel"),
                )),
            ]
        )
        self.assertEqual(value["years"], [2025, 2026])
        self.assertEqual(
            [(row["year"], row["amount"]) for row in value["rows"]],
            [(2025, 4.0), (2026, 5.0)],
        )


if __name__ == "__main__":
    unittest.main()

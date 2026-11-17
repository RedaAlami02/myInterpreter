"""Rollback-only projection publication SQL; requires an explicit /tmp socket."""

import hashlib
import json
import os
from pathlib import Path
import unittest

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = "feed_0123456789abcdef"
DIVIDEND_INDEX = "a" * 64
FUNDAMENTAL_INDEX = "b" * 64
DIVIDEND_DIGEST = "1" * 64
FUNDAMENTAL_DIGEST = "2" * 64


def dividend_row(**overrides):
    row = {
        "c_name": "Alpha",
        "issuer": "ALPHA",
        "year": 2026,
        "amount": 175.0,
        "ex_date": "2026-03-25",
        "pay_date": "2026-04-08",
        "pay_date_end": None,
        "confirmed": True,
        "type": "Ordinaire",
        "frequency": "Annuel",
    }
    row.update(overrides)
    return row


def dividend_document(rows=None, **overrides):
    value = {
        "contract": "dividend-projection/v1",
        "mode": "PROJECTION_ONLY",
        "provider_namespace": PROVIDER,
        "archive_sha256": DIVIDEND_DIGEST,
        "index_sha256": DIVIDEND_INDEX,
        "built_at": "2026-10-29T10:00:00Z",
        "source_execution": "CURRENT_ACQUISITION",
        "years": [2026],
        "rows": rows if rows is not None else [dividend_row()],
        "excluded": [],
        "unmatched": [],
        "errors": [],
        "coverage": {},
        "completeness": "COMPLETE",
        "prediction_eligible": False,
        "portfolio_valuation_eligible": False,
        "candidate_sha256": "c" * 64,
    }
    value.update(overrides)
    return value


def fundamental_fields(**overrides):
    fields = {
        "ext_name": "Alpha SA",
        "sector": "Banks",
        "description": "Fixture description",
        "shareholders": None,
        "bpa": 16.67,
        "dpa": 0.5,
        "tc5": 8.45,
        "roe": 16.67,
        "na": 1200000.0,
        "cp": 120000000.0,
        "beta_3y": 0.8,
        "beta_5y": 0.9,
        "revenue": 140.0,
        "ebitda": 60.0,
        "ebit": 50.0,
        "net_profit": 20.0,
        "fcf": 25.0,
        "net_debt": 40.0,
        "net_cash": 5.0,
        "total_assets": 900.0,
        "rev_growth_5y": 8.45,
        "rnpg_growth_5y": 7.1,
        "profit_margin": 14.29,
        "fiscal_year": 2023,
        "fy_est": 2025,
        "rnpg_est": 30.0,
    }
    fields.update(overrides)
    return fields


def fundamental_document(fields=None, **overrides):
    value = {
        "contract": "fundamental-projection/v1",
        "mode": "PROJECTION_ONLY",
        "provider_namespace": PROVIDER,
        "archive_sha256": FUNDAMENTAL_DIGEST,
        "index_sha256": FUNDAMENTAL_INDEX,
        "built_at": "2026-10-29T10:00:00Z",
        "source_execution": "CURRENT_ACQUISITION",
        "symbol": "AAA",
        "c_name": "Alpha",
        "fields": fields if fields is not None else fundamental_fields(),
        "errors": [],
        "completeness": "COMPLETE",
        "prediction_eligible": False,
        "portfolio_valuation_eligible": False,
        "candidate_sha256": "d" * 64,
    }
    value.update(overrides)
    return value


@unittest.skipUnless(
    os.environ.get("APP_TEST_DATABASE"), "Isolated database not configured"
)
class ProjectionSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = conninfo_to_dict(os.environ["APP_TEST_DATABASE"])
        if not options.get("host", "").startswith("/tmp/"):
            raise RuntimeError("Only an isolated local Unix socket is permitted")
        cls.db = psycopg.connect(**options)
        for schema in ["app_projection", "app_archive"]:
            if (
                cls.db.execute("SELECT to_regnamespace(%s)", (schema,)).fetchone()[0]
                is not None
            ):
                cls.db.rollback()
                cls.db.close()
                raise RuntimeError("Test database contains existing schemas")
        for role in ["anon", "authenticated", "service_role"]:
            if not cls.db.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
            ).fetchone():
                cls.db.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
        for name in [
            "002_public_market.sql",
            "009_private_object_archive.sql",
            "013_projection_publication.sql",
        ]:
            cls.db.execute((ROOT / "migrations/supabase" / name).read_text())
        cls.db.execute("UPDATE app_archive.control SET enabled=true")
        cls.db.execute(
            "INSERT INTO app_archive.providers VALUES(%s,true)", (PROVIDER,)
        )
        cls.db.execute(
            "INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,"
            " completeness,compressed_bytes,object_path,state,verified_at) VALUES"
            " (%s,%s,'dividends',now()-interval '2 hours',now()-interval '1 hour',"
            "  'COMPLETE',100,'sha256/'||left(%s,2)||'/'||%s||'.json.gz','STORED',now()),"
            " (%s,%s,'fundamentals',now()-interval '2 hours',now()-interval '1 hour',"
            "  'COMPLETE',100,'sha256/'||left(%s,2)||'/'||%s||'.json.gz','STORED',now())",
            (DIVIDEND_DIGEST, PROVIDER, DIVIDEND_DIGEST, DIVIDEND_DIGEST,
             FUNDAMENTAL_DIGEST, PROVIDER, FUNDAMENTAL_DIGEST, FUNDAMENTAL_DIGEST),
        )
        cls.db.execute(
            "UPDATE app_projection.control SET enabled=true, provider_namespace=%s,"
            " dividend_index_sha256=%s, fundamental_index_sha256=%s",
            (PROVIDER, DIVIDEND_INDEX, FUNDAMENTAL_INDEX),
        )
        cls.db.execute(
            "INSERT INTO public.company(id,name,bpa,fiscal_year) VALUES"
            " ('c1','Alpha',5,2023),('c2','Beta',NULL,NULL)"
        )
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.rollback()
        cls.db.close()

    def setUp(self):
        self.db.execute("SAVEPOINT projection_case")

    def tearDown(self):
        self.db.execute("ROLLBACK TO SAVEPOINT projection_case")

    def publish_dividends(self, document):
        text = json.dumps(document)

        return self.db.execute(
            "SELECT public.publish_dividend_projection(%s,%s)",
            (text, hashlib.sha256(text.encode()).hexdigest()),
        ).fetchone()[0]

    def publish_fundamentals(self, document):
        text = json.dumps(document)

        return self.db.execute(
            "SELECT public.publish_fundamental_projection(%s,%s)",
            (text, hashlib.sha256(text.encode()).hexdigest()),
        ).fetchone()[0]

    def newer_archive(self, kind='dividends', digest='3' * 64):
        original = DIVIDEND_DIGEST if kind == 'dividends' else FUNDAMENTAL_DIGEST
        self.db.execute(
            "INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,"
            " completeness,compressed_bytes,object_path,state,verified_at)"
            " SELECT %s,provider,kind,slot+interval '30 minutes',completed_at+interval '30 minutes',"
            " completeness,compressed_bytes,'sha256/'||left(%s,2)||'/'||%s||'.json.gz',state,verified_at"
            " FROM app_archive.objects WHERE digest=%s", (digest,digest,digest,original))
        return digest

    def rejects(self, operation, code="22023"):
        with self.assertRaises(psycopg.Error) as raised:
            operation()
        self.assertEqual(raised.exception.sqlstate, code)
        self.db.execute("ROLLBACK TO SAVEPOINT projection_case")

    # ── dividends ────────────────────────────────────────────────────────────

    def test_dividends_are_published_idempotently_and_updated_on_change(self):
        first = self.publish_dividends(dividend_document())
        self.assertEqual(
            first, {"status": "PUBLISHED", "rows": 1, "created": 1, "updated": 0}
        )
        row = self.db.execute(
            "SELECT c_name,issuer,year,amount,ex_date,pay_date,pay_date_end,"
            " confirmed,type,frequency FROM public.dividends"
        ).fetchone()
        self.assertEqual(
            (row[0], row[2], float(row[3]), row[4].isoformat(), row[7], row[8]),
            ("Alpha", 2026, 175.0, "2026-03-25", True, "Ordinaire"),
        )
        self.assertEqual(
            self.publish_dividends(dividend_document()),
            {"status": "PUBLISHED", "rows": 1, "created": 0, "updated": 0},
        )
        changed = self.publish_dividends(
            dividend_document([dividend_row(amount=180.0)], archive_sha256=self.newer_archive())
        )
        self.assertEqual(changed["updated"], 1)
        self.assertEqual(
            float(self.db.execute(
                "SELECT amount FROM public.dividends"
            ).fetchone()[0]),
            180.0,
        )

    def test_dividend_quality_and_shape_are_enforced(self):
        cases = [
            dividend_row(c_name="Unknown"),
            dividend_row(confirmed=True, ex_date=None),
            dividend_row(pay_date="2027-01-05"),
            dividend_row(pay_date_end="2026-03-01"),
            dividend_row(amount=0),
            dividend_row(amount="175"),
            dividend_row(ex_date="2026-02-30"),
            dividend_row(type="x" * 101),
        ]
        for row in cases:
            document = dividend_document([row])
            self.rejects(lambda document=document: self.publish_dividends(document))

    def test_duplicate_dividend_keys_are_refused(self):
        self.rejects(lambda: self.publish_dividends(
            dividend_document([dividend_row(), dividend_row(amount=180.0)])
        ))

    def test_null_type_is_grouped_and_duplicated_safely(self):
        self.publish_dividends(
            dividend_document([dividend_row(type=None, amount=5.0)])
        )
        again = self.publish_dividends(
            dividend_document([dividend_row(type=None, amount=6.0)], archive_sha256=self.newer_archive())
        )
        self.assertEqual(again["updated"], 1)
        self.rejects(lambda: self.publish_dividends(
            dividend_document([
                dividend_row(type=None, amount=5.0),
                dividend_row(type=None, amount=6.0),
            ])
        ))

    def test_dividend_pins_archive_and_disabled_control_are_enforced(self):
        self.rejects(
            lambda: self.publish_dividends(
                dividend_document(index_sha256="c" * 64)
            )
        )
        self.rejects(
            lambda: self.publish_dividends(
                dividend_document(archive_sha256="9" * 64)
            ), "42501"
        )
        self.rejects(
            lambda: self.publish_dividends(
                dividend_document(contract="dividend-projection/v0")
            )
        )
        self.rejects(
            lambda: self.publish_dividends(
                dividend_document(source_execution="RECORDED_REPLAY")
            )
        )
        self.rejects(
            lambda: self.publish_dividends(
                dividend_document(excluded={})
            )
        )
        self.db.execute("UPDATE app_projection.control SET enabled=false")
        self.rejects(lambda: self.publish_dividends(dividend_document()), "22023")
        self.db.execute("ROLLBACK TO SAVEPOINT projection_case")
        self.db.execute(
            "UPDATE app_archive.objects SET slot=now()-interval '41 days',"
            " completed_at=now()-interval '40 days' WHERE digest=%s",
            (DIVIDEND_DIGEST,),
        )
        self.rejects(lambda: self.publish_dividends(dividend_document()), "42501")

    # ── fundamentals ────────────────────────────────────────────────────────

    def test_fundamentals_fill_only_missing_fields_for_the_same_year(self):
        result = self.publish_fundamentals(fundamental_document())
        self.assertEqual(result["status"], "UPDATED")
        self.assertFalse(result["refreshed"])
        row = self.db.execute(
            "SELECT bpa,fiscal_year,roe,ext_name FROM public.company WHERE name='Alpha'"
        ).fetchone()
        self.assertEqual(float(row[0]), 5.0)  # populated value survives same-year run
        self.assertEqual(row[1], 2023)
        self.assertEqual(float(row[2]), 16.67)
        self.assertEqual(row[3], "Alpha SA")
        # bpa and fiscal_year are already populated for the same year, and nulls
        # (shareholders here) are never written.
        self.assertEqual(result["fields"], 23)
        again = self.publish_fundamentals(fundamental_document())
        self.assertEqual(again["fields"], 0)

    def test_fundamentals_refresh_on_a_newer_fiscal_year(self):
        result = self.publish_fundamentals(
            fundamental_document(fundamental_fields(fiscal_year=2024, bpa=99.5))
        )
        self.assertTrue(result["refreshed"])
        row = self.db.execute(
            "SELECT bpa,fiscal_year FROM public.company WHERE name='Alpha'"
        ).fetchone()
        self.assertEqual(float(row[0]), 99.5)
        self.assertEqual(row[1], 2024)

    def test_null_never_overwrites_and_missing_company_is_reported(self):
        result = self.publish_fundamentals(
            fundamental_document(fundamental_fields(roe=None, ext_name=None,
                                                     fiscal_year=2024))
        )
        self.assertEqual(
            self.db.execute(
                "SELECT roe,ext_name FROM public.company WHERE name='Alpha'"
            ).fetchone(),
            (None, None),
        )
        self.assertEqual(result["status"], "UPDATED")
        self.assertEqual(
            self.publish_fundamentals(
                fundamental_document(c_name="Unknown")),
            {"status": "MISSING", "name": "Unknown"},
        )

    def test_fundamental_field_contract_is_enforced(self):
        fields = fundamental_fields()
        fields.pop("beta_5y")
        cases = [
            fundamental_document(fields=fields),
            fundamental_document(fields={**fundamental_fields(), "id": "x"}),
            fundamental_document(fields=fundamental_fields(fiscal_year=1800)),
            fundamental_document(fields=fundamental_fields(bpa="16.67")),
            fundamental_document(fields=fundamental_fields(shareholders="{broken")),
            fundamental_document(fields=fundamental_fields(ext_name="")),
            fundamental_document(index_sha256="c" * 64),
            fundamental_document(symbol=""),
        ]
        for document in cases:
            self.rejects(lambda document=document: self.publish_fundamentals(document))
        self.rejects(
            lambda: self.publish_fundamentals(
                fundamental_document(archive_sha256="9" * 64)
            ),
            "42501",
        )

    def test_service_only_grants(self):
        for function in [
            "public.publish_dividend_projection(text,text)",
            "public.publish_fundamental_projection(text,text)",
        ]:
            self.assertTrue(
                self.db.execute(
                    "SELECT has_function_privilege('service_role',%s,'EXECUTE')",
                    (function,),
                ).fetchone()[0]
            )
            for role in ["anon", "authenticated"]:
                self.assertFalse(
                    self.db.execute(
                        "SELECT has_function_privilege(%s,%s,'EXECUTE')",
                        (role, function),
                    ).fetchone()[0]
                )
        self.assertFalse(
            self.db.execute(
                "SELECT has_table_privilege('service_role',"
                "'app_projection.control','SELECT')"
            ).fetchone()[0]
        )


    def test_both_publication_kinds_obey_capacity_guard(self):
        self.db.execute('UPDATE app_projection.control SET max_database_bytes=0')
        for statement in [
            ('SELECT public.publish_dividend_projection(%s,%s)', dividend_document()),
            ('SELECT public.publish_fundamental_projection(%s,%s)', fundamental_document()),
        ]:
            text = json.dumps(statement[1])
            with self.assertRaises(psycopg.errors.ProgramLimitExceeded), self.db.transaction():
                self.db.execute(statement[0], (text, hashlib.sha256(text.encode()).hexdigest()))
        self.assertEqual(self.db.execute('SELECT count(*) FROM app_projection.accepted_rows').fetchone()[0], 0)

    def test_older_and_equal_time_conflicting_dividends_cannot_regress_latest(self):
        self.publish_dividends(dividend_document())
        digest = self.newer_archive()
        self.publish_dividends(dividend_document([dividend_row(amount=180.0)], archive_sha256=digest))
        with self.assertRaises(psycopg.errors.InvalidParameterValue), self.db.transaction():
            self.publish_dividends(dividend_document())
        self.db.execute("INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,completeness,compressed_bytes,object_path,state,verified_at) SELECT '" + '4' * 64 + "',provider,kind,slot,completed_at,completeness,compressed_bytes,"
                        "'sha256/44/" + '4' * 64 + ".json.gz',state,verified_at FROM app_archive.objects WHERE digest=%s", (digest,))
        with self.assertRaises(psycopg.errors.InvalidParameterValue), self.db.transaction():
            self.publish_dividends(dividend_document([dividend_row(amount=190.0)], archive_sha256='4' * 64))
        self.assertEqual(float(self.db.execute('SELECT amount FROM public.dividends').fetchone()[0]), 180.0)
        self.assertEqual(self.db.execute('SELECT archive_digest FROM app_projection.accepted_rows').fetchone()[0], digest)

    def test_same_archive_changed_values_require_review_and_exact_retry_has_no_new_head(self):
        self.publish_dividends(dividend_document())
        before = self.db.execute('SELECT archive_digest,completed_at,row_sha256,xmin::text FROM app_projection.accepted_rows').fetchone()
        timestamp = self.db.execute('SELECT updated_at FROM public.dividends').fetchone()[0]
        again = self.publish_dividends(dividend_document())
        self.assertEqual(again['updated'], 0)
        self.assertEqual(self.db.execute('SELECT archive_digest,completed_at,row_sha256,xmin::text FROM app_projection.accepted_rows').fetchone(), before)
        self.assertEqual(self.db.execute('SELECT updated_at FROM public.dividends').fetchone()[0], timestamp)
        with self.assertRaises(psycopg.errors.InvalidParameterValue), self.db.transaction():
            self.publish_dividends(dividend_document([dividend_row(amount=180.0)]))

    def test_fundamental_heads_reject_stale_and_equal_time_value_conflicts(self):
        self.publish_fundamentals(fundamental_document())
        digest = self.newer_archive('fundamentals')
        self.publish_fundamentals(fundamental_document(fundamental_fields(fiscal_year=2024, bpa=99.5), archive_sha256=digest))
        for doc in [fundamental_document(), fundamental_document(fundamental_fields(fiscal_year=2024, bpa=90), archive_sha256=digest)]:
            with self.assertRaises(psycopg.errors.InvalidParameterValue), self.db.transaction():
                self.publish_fundamentals(doc)
        self.assertEqual(float(self.db.execute("SELECT bpa FROM public.company WHERE name='Alpha'").fetchone()[0]), 99.5)

    def test_acceptance_heads_and_helper_remain_private(self):
        for role in ['anon','authenticated','service_role']:
            self.assertFalse(self.db.execute("SELECT has_table_privilege(%s,'app_projection.accepted_rows','SELECT,INSERT,UPDATE,DELETE')", (role,)).fetchone()[0])
            self.assertFalse(self.db.execute("SELECT has_function_privilege(%s,'app_projection.accept_row(text,text,jsonb,text,timestamptz,jsonb)','EXECUTE')", (role,)).fetchone()[0])


if __name__ == "__main__":
    unittest.main()

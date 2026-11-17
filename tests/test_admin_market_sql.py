"""Rollback-only admin maintenance SQL; requires an explicit /tmp test socket."""

import json
import os
from pathlib import Path
import sys
import unittest

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


@unittest.skipUnless(
    os.environ.get("APP_TEST_DATABASE"), "Isolated database not configured"
)
class AdminMaintenanceSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = conninfo_to_dict(os.environ["APP_TEST_DATABASE"])
        if not options.get("host", "").startswith("/tmp/"):
            raise RuntimeError("Only an isolated local Unix socket is permitted")
        cls.db = psycopg.connect(**options)
        for schema in ["market_admin", "auth"]:
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
        cls.db.execute(
            "CREATE SCHEMA auth;"
            " CREATE TABLE auth.users(id uuid PRIMARY KEY);"
            " CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$"
            " SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;"
            " CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql AS $$"
            " SELECT coalesce(nullif(current_setting('request.jwt.claim.role',true),''),'anon') $$"
        )
        cls.db.execute(
            (ROOT / "migrations/supabase/002_public_market.sql").read_text()
        )
        cls.db.execute(
            (ROOT / "migrations/supabase/011_admin_market_maintenance.sql").read_text()
        )
        cls.db.execute(
            "INSERT INTO auth.users VALUES(%s),(%s),('33333333-3333-4333-8333-333333333333')",
            (ADMIN, OTHER),
        )
        cls.db.execute("INSERT INTO market_admin.admins(user_id) VALUES(%s)", (ADMIN,))
        cls.db.execute(
            "INSERT INTO public.company(id,name,bpa,cp,date,sector) VALUES"
            " ('c1','Alpha',1.5,9,'2026-10-01T00:00:00Z','Industrials'),"
            " ('c2','Beta',2.5,10,'2026-10-02T00:00:00Z',NULL)"
        )
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.rollback()
        cls.db.close()

    def setUp(self):
        self.as_user(None, "anon")
        self.db.execute("SAVEPOINT admin_case")

    def tearDown(self):
        self.db.execute("ROLLBACK TO SAVEPOINT admin_case")

    def as_user(self, user_id=None, role="authenticated"):
        self.claims = (user_id, role)
        self.db.execute(
            "SELECT set_config('request.jwt.claim.sub',%s,true),"
            " set_config('request.jwt.claim.role',%s,true)",
            (user_id or "", role),
        )

    def update(self, name, fields):
        return self.db.execute(
            "SELECT public.admin_update_company(%s,%s)",
            (name, None if fields is None else json.dumps(fields)),
        ).fetchone()[0]

    def snapshot(self, fields):
        return self.db.execute(
            "SELECT public.admin_record_operator_snapshot(%s)",
            (json.dumps(fields),),
        ).fetchone()[0]

    def rejects(self, operation, code="22023"):
        with self.assertRaises(psycopg.Error) as raised:
            operation()
        self.assertEqual(raised.exception.sqlstate, code)
        # Rolling back to the savepoint also reverts local claim settings.
        self.db.execute("ROLLBACK TO SAVEPOINT admin_case")
        self.as_user(*self.claims)

    def test_requires_an_authenticated_seeded_administrator(self):
        for user, role in [
            (None, "authenticated"),
            (OTHER, "authenticated"),
            (ADMIN, "anon"),
        ]:
            self.as_user(user, role)
            self.rejects(lambda: self.update("Alpha", {"bpa": 2}), "42501")
            self.rejects(lambda: self.snapshot({"c_name": "Alpha", "pa": 12}), "42501")

    def test_updates_only_supplied_fields(self):
        self.as_user(ADMIN)
        result = self.update("Alpha", {"bpa": 12.5, "sector": "Banks"})
        self.assertEqual(result, {"status": "UPDATED", "name": "Alpha", "fields": 2})
        row = self.db.execute(
            "SELECT bpa,cp,date,sector FROM public.company WHERE name='Alpha'"
        ).fetchone()
        self.assertEqual(float(row[0]), 12.5)
        self.assertEqual(float(row[1]), 9)
        self.assertEqual(row[2].isoformat(), "2026-10-01T00:00:00+00:00")
        self.assertEqual(row[3], "Banks")
        self.as_user(ADMIN)
        self.assertEqual(
            self.update("Beta", {"description": "Fixture"})["fields"], 1
        )

    def test_clears_a_field_only_when_explicitly_null(self):
        self.as_user(ADMIN)
        self.update("Alpha", {"sector": None})
        self.assertIsNone(
            self.db.execute(
                "SELECT sector FROM public.company WHERE name='Alpha'"
            ).fetchone()[0]
        )

    def test_rejects_unknown_mistyped_and_out_of_range_fields(self):
        self.as_user(ADMIN)
        for fields in [
            {"id": "forged"},
            {"name": "Renamed"},
            {"date": "2026-10-28T00:00:00Z"},
            {"bpa": "12.5"},
            {"bpa": True},
            {"bpa": 1000000000000001},
            {"bpa": 0.1234567},
            {"fiscal_year": 1800},
            {"fiscal_year": 2024.5},
            {"description": 5},
            {"description": ""},
            {},
            {"bpa": {"nested": 1}},
        ]:
            self.rejects(lambda fields=fields: self.update("Alpha", fields))
        self.rejects(lambda: self.update(" Alpha", {"bpa": 2}))
        self.rejects(lambda: self.update("Alpha", None))

    def test_rejects_percentage_fractions(self):
        self.as_user(ADMIN)
        for fields in [{"tc5": 0.28}, {"roe": -0.5}, {"tc5": 0.999999}]:
            self.rejects(lambda fields=fields: self.update("Alpha", fields))
        self.assertEqual(self.update("Alpha", {"roe": 0})["status"], "UPDATED")
        self.assertEqual(self.update("Alpha", {"tc5": 28.4})["status"], "UPDATED")
        self.assertEqual(self.update("Alpha", {"roe": -12.5})["status"], "UPDATED")

    def test_unknown_company_is_reported_without_creating_a_row(self):
        self.as_user(ADMIN)
        self.assertEqual(
            self.update("Gamma", {"bpa": 3}),
            {"status": "MISSING", "name": "Gamma"},
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM public.company").fetchone()[0], 2
        )

    def test_operator_snapshot_is_explicit_and_exact(self):
        self.as_user(ADMIN)
        snapshot_id = self.snapshot(
            {
                "c_name": "Alpha",
                "pa": 12.34,
                "cb": 1200.5,
                "per": 8.2,
                "peg": 0.91,
                "pr": 1.4,
                "pb": 2.2,
            }
        )
        self.assertRegex(snapshot_id, r"^[a-f0-9]{32}$")
        row = self.db.execute(
            "SELECT c_name,pa,cb,per,peg,pr,pb,source,symbol,date"
            " FROM public.data WHERE id=%s",
            (snapshot_id,),
        ).fetchone()
        self.assertEqual(
            (row[0], *(round(float(value), 6) for value in row[1:7]), row[7]),
            ("Alpha", 12.34, 1200.5, 8.2, 0.91, 1.4, 2.2, "OPERATOR_ENTRY"),
        )
        self.assertIsNone(row[8])
        self.assertIsNotNone(row[9])
        self.assertEqual(
            self.db.execute(
                "SELECT source FROM public.data WHERE id=%s", (snapshot_id,)
            ).fetchone()[0],
            "OPERATOR_ENTRY",
        )

    def test_snapshot_rejects_invalid_input(self):
        self.as_user(ADMIN)
        for fields in [
            {"c_name": "Gamma", "pa": 1},
            {"c_name": "Alpha"},
            {"c_name": "Alpha", "pa": 0},
            {"c_name": "Alpha", "pa": -1},
            {"c_name": "Alpha", "pa": 1000000000001},
            {"c_name": "Alpha", "pa": "12.5"},
            {"c_name": "Alpha ", "pa": 12},
            {"c_name": "Alpha", "pa": 12, "symbol": "A"},
            {"c_name": "Alpha", "pa": 12, "per": "8"},
            {"c_name": "Alpha", "pa": 12, "per": 1000000000000001},
            {"pa": 12},
        ]:
            self.rejects(lambda fields=fields: self.snapshot(fields))
        self.as_user(ADMIN)
        self.snapshot({"c_name": "Alpha", "pa": 12, "per": None})

    def test_recovered_rows_keep_null_provenance(self):
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM public.data WHERE source IS NOT NULL"
            ).fetchone()[0],
            0,
        )
        with self.assertRaises(psycopg.Error) as raised:
            self.db.execute(
                "INSERT INTO public.data(id,c_name,date,pa,source)"
                " VALUES('forged','Alpha',now(),1,'MARKET_CAP')"
            )
        self.assertEqual(raised.exception.sqlstate, "23514")
        self.db.execute("ROLLBACK TO SAVEPOINT admin_case")

    def test_maintenance_api_is_not_reachable_without_authorization(self):
        for function in [
            "public.admin_update_company(text,jsonb)",
            "public.admin_record_operator_snapshot(jsonb)",
        ]:
            self.assertFalse(
                self.db.execute(
                    "SELECT has_function_privilege('anon',%s,'EXECUTE')",
                    (function,),
                ).fetchone()[0]
            )
            self.assertTrue(
                self.db.execute(
                    "SELECT has_function_privilege('authenticated',%s,'EXECUTE')",
                    (function,),
                ).fetchone()[0]
            )
        self.assertFalse(
            self.db.execute(
                "SELECT has_table_privilege('authenticated',"
                "'market_admin.admins','SELECT')"
            ).fetchone()[0]
        )


if __name__ == "__main__":
    unittest.main()

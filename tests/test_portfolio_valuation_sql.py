"""Rollback-only daily valuation SQL; requires an explicit /tmp test socket."""

import os
from pathlib import Path
import unittest

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
OWNER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
HEAVY = "33333333-3333-4333-8333-333333333333"
# Local wall-clock times; the database derives the instant with its own tz data.
NOW = "2026-10-26 16:30"


@unittest.skipUnless(
    os.environ.get("APP_TEST_DATABASE"), "Isolated database not configured"
)
class PortfolioValuationSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = conninfo_to_dict(os.environ["APP_TEST_DATABASE"])
        if not options.get("host", "").startswith("/tmp/"):
            raise RuntimeError("Only an isolated local Unix socket is permitted")
        cls.db = psycopg.connect(**options)
        for schema in ["portfolio_private", "auth"]:
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
        for name in [
            "002_public_market.sql",
            "003_private_portfolio.sql",
            "012_portfolio_valuation.sql",
        ]:
            cls.db.execute((ROOT / "migrations/supabase" / name).read_text())
        cls.db.execute(
            "INSERT INTO auth.users VALUES(%s),(%s),(%s)", (OWNER, OTHER, HEAVY)
        )
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.rollback()
        cls.db.close()

    def setUp(self):
        self.as_user(None, "anon")
        self.db.execute("SAVEPOINT valuation_case")
        self.seed()

    def seed(self):
        self.db.execute(
            "INSERT INTO public.portefeuille(user_id,c_name,quantity,total_cost) VALUES"
            " (%s,'X',10,100),(%s,'Y',2,50),(%s,'X',5,10)",
            (OWNER, OWNER, OTHER),
        )
        self.db.execute(
            "INSERT INTO public.latest_prices(id,c_name,pa,date,origin_collection) VALUES"
            " ('lx','X',12.5,('2026-10-26 16:00'::timestamp AT TIME ZONE 'Africa/Casablanca'),'latest_prices'),"
            " ('ly','Y',30,('2026-10-26 16:05'::timestamp AT TIME ZONE 'Africa/Casablanca'),'latest_prices')"
        )

    def reset(self):
        self.db.execute("ROLLBACK TO SAVEPOINT valuation_case")
        self.as_user(*self.claims)
        self.seed()

    def tearDown(self):
        self.db.execute("ROLLBACK TO SAVEPOINT valuation_case")

    def as_user(self, user_id=None, role="authenticated"):
        self.claims = (user_id, role)
        self.db.execute(
            "SELECT set_config('request.jwt.claim.sub',%s,true),"
            " set_config('request.jwt.claim.role',%s,true)",
            (user_id or "", role),
        )

    def value(self, owner=OWNER, now=NOW):
        return self.db.execute(
            "SELECT portfolio_private.daily_valuation("
            "%s,(%s::timestamp AT TIME ZONE 'Africa/Casablanca'))",
            (owner, now),
        ).fetchone()[0]

    def benefits(self, owner=OWNER):
        return self.db.execute(
            "SELECT date,value FROM public.benefits WHERE user_id=%s", (owner,)
        ).fetchall()

    def test_public_rpc_requires_authentication(self):
        for user, role in [(None, "authenticated"), (OWNER, "anon")]:
            self.as_user(user, role)
            with self.assertRaises(psycopg.Error) as raised:
                self.db.execute("SELECT public.record_daily_valuation()")
            self.assertEqual(raised.exception.sqlstate, "42501")
            self.db.execute("ROLLBACK TO SAVEPOINT valuation_case")
            self.as_user(*self.claims)

    def test_valuation_is_exact_idempotent_and_owner_scoped(self):
        result = self.value()
        self.assertEqual(result, {"status": "CREATED", "date": "2026-10-26", "value": 35.0})
        self.assertEqual(float(self.benefits()[0][1]), 35.0)
        self.assertEqual(
            self.value(), {"status": "EXISTING", "date": "2026-10-26", "value": 35.0}
        )
        self.assertEqual(len(self.benefits()), 1)
        # Another owner's holdings never enter this valuation.
        self.assertEqual(self.benefits(OTHER), [])
        self.assertEqual(float(self.value(OTHER)["value"]), 52.5)

    def test_closing_window_is_required(self):
        for moment in ["2026-10-25 16:30", "2026-10-26 13:00"]:
            self.assertEqual(self.value(now=moment)["status"], "OUTSIDE_WINDOW")
        self.assertEqual(self.benefits(), [])

    def test_existing_receipt_returns_saved_value_after_holdings_and_prices_change(self):
        first = self.value()
        self.db.execute("UPDATE public.portefeuille SET quantity=quantity*2 WHERE user_id=%s", (OWNER,))
        self.db.execute("UPDATE public.latest_prices SET pa=pa*3")
        again = self.value()
        self.assertEqual(again['status'], 'EXISTING')
        self.assertEqual(again['value'], first['value'])
        self.assertEqual(float(self.benefits()[0][1]), again['value'])

    def test_existing_receipt_is_available_without_revaluing_stale_prices(self):
        first = self.value()
        self.db.execute('DELETE FROM public.latest_prices')
        again = self.value(now='2026-10-26 13:00')
        self.assertEqual(again['status'], 'EXISTING')
        self.assertEqual(again['value'], first['value'])

    def test_unusable_prices_are_never_valued(self):
        cases = [
            "UPDATE public.latest_prices SET date=('2026-10-25 16:00'::timestamp"
            " AT TIME ZONE 'Africa/Casablanca') WHERE c_name='X'",
            "UPDATE public.latest_prices SET date=('2026-10-26 15:30'::timestamp"
            " AT TIME ZONE 'Africa/Casablanca') WHERE c_name='X'",
            "UPDATE public.latest_prices SET date=('2026-10-26 17:00'::timestamp"
            " AT TIME ZONE 'Africa/Casablanca') WHERE c_name='X'",
            "UPDATE public.latest_prices SET pa=0 WHERE c_name='X'",
            "DELETE FROM public.latest_prices WHERE c_name='Y'",
        ]
        for change in cases:
            self.db.execute(change)
            self.assertEqual(self.value()["status"], "PRICE_UNAVAILABLE")
            self.assertEqual(self.benefits(), [])
            self.reset()
        self.assertEqual(self.value()["status"], "CREATED")

    def test_empty_portfolio_only_writes_zero_when_history_exists(self):
        self.db.execute("DELETE FROM public.portefeuille WHERE user_id=%s", (OWNER,))
        self.assertEqual(self.value()["status"], "EMPTY")
        self.assertEqual(self.benefits(), [])
        self.db.execute(
            "INSERT INTO public.benefits(user_id,date,value) VALUES(%s,'2026-10-23',5)",
            (OWNER,),
        )
        self.assertEqual(self.value()["status"], "CREATED")
        self.assertEqual(sum(float(row[1]) for row in self.benefits()), 5.0)

    def test_position_bound_and_grants(self):
        self.db.execute("DELETE FROM public.portefeuille WHERE user_id=%s", (OWNER,))
        self.db.execute(
            "INSERT INTO public.portefeuille(user_id,c_name,quantity,total_cost)"
            " SELECT %s,'P'||g,1,1 FROM generate_series(1,501) g",
            (OWNER,),
        )
        with self.assertRaises(psycopg.Error) as raised:
            self.value()
        self.assertEqual(raised.exception.sqlstate, "54000")
        self.reset()
        self.assertFalse(
            self.db.execute(
                "SELECT has_function_privilege('anon',"
                "'public.record_daily_valuation()','EXECUTE')"
            ).fetchone()[0]
        )
        self.assertTrue(
            self.db.execute(
                "SELECT has_function_privilege('authenticated',"
                "'public.record_daily_valuation()','EXECUTE')"
            ).fetchone()[0]
        )
        self.assertFalse(
            self.db.execute(
                "SELECT has_function_privilege('authenticated',"
                "'portfolio_private.daily_valuation(uuid,timestamptz)','EXECUTE')"
            ).fetchone()[0]
        )

    def test_public_rpc_reports_a_bounded_status_for_the_owner(self):
        self.as_user(OWNER)
        result = self.db.execute("SELECT public.record_daily_valuation()").fetchone()[0]
        self.assertIn(
            result["status"],
            {"CREATED", "EXISTING", "EMPTY", "PRICE_UNAVAILABLE", "OUTSIDE_WINDOW"},
        )


if __name__ == "__main__":
    unittest.main()

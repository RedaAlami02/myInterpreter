"""Privacy migration regression: isolated local PostgreSQL only, rollback always."""

import os
from pathlib import Path
import unittest

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("APP_TEST_DATABASE"), "Isolated database not configured")
class AuthenticatedMarketAccessTests(unittest.TestCase):
    def test_anonymous_denied_owner_isolated_and_rows_unchanged(self):
        options = conninfo_to_dict(os.environ["APP_TEST_DATABASE"])
        if not options.get("host", "").startswith("/tmp/"):
            raise RuntimeError("Only isolated Unix sockets permitted")
        with psycopg.connect(**options) as db:
            try:
                for role in ["anon", "authenticated", "service_role"]:
                    if not db.execute(
                        "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
                    ).fetchone():
                        db.execute(
                            psycopg.sql.SQL("CREATE ROLE {}").format(psycopg.sql.Identifier(role))
                        )
                db.execute("CREATE TABLE public.privacy_market_fixture (id int, price numeric)")
                db.execute("INSERT INTO public.privacy_market_fixture VALUES (1,12.34)")
                db.execute("GRANT SELECT ON public.privacy_market_fixture TO anon,authenticated")
                db.execute("ALTER TABLE public.privacy_market_fixture ENABLE ROW LEVEL SECURITY")
                db.execute(
                    "CREATE POLICY market_public_read ON public.privacy_market_fixture FOR SELECT TO anon,authenticated USING(true)"
                )
                db.execute(
                    "CREATE TABLE public.privacy_owner_fixture (user_id text, value numeric)"
                )
                db.execute("INSERT INTO public.privacy_owner_fixture VALUES ('a',10),('b',20)")
                db.execute("ALTER TABLE public.privacy_owner_fixture ENABLE ROW LEVEL SECURITY")
                db.execute("GRANT SELECT ON public.privacy_owner_fixture TO authenticated")
                db.execute(
                    "CREATE POLICY owner_only ON public.privacy_owner_fixture TO authenticated USING(user_id=current_setting('test.user_id',true))"
                )
                db.execute(
                    (ROOT / "migrations/supabase/008_authenticated_market_access.sql").read_text()
                )
                db.execute("SET LOCAL ROLE anon")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with db.transaction():
                        db.execute("SELECT * FROM public.privacy_market_fixture")
                db.execute("RESET ROLE")
                db.execute("SET LOCAL ROLE authenticated")
                self.assertEqual(
                    db.execute("SELECT price::text FROM public.privacy_market_fixture").fetchall(),
                    [("12.34",)],
                )
                db.execute("SET LOCAL test.user_id='a'")
                self.assertEqual(
                    db.execute("SELECT user_id FROM public.privacy_owner_fixture").fetchall(),
                    [("a",)],
                )
                db.execute("SET LOCAL test.user_id='b'")
                self.assertEqual(
                    db.execute("SELECT user_id FROM public.privacy_owner_fixture").fetchall(),
                    [("b",)],
                )
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with db.transaction():
                        db.execute("DELETE FROM public.privacy_owner_fixture")
                db.execute("RESET ROLE")
                self.assertEqual(
                    db.execute("SELECT count(*) FROM public.privacy_owner_fixture").fetchone()[0], 2
                )
                self.assertEqual(
                    db.execute("SELECT price::text FROM public.privacy_market_fixture").fetchone()[
                        0
                    ],
                    "12.34",
                )
            finally:
                db.rollback()


if __name__ == "__main__":
    unittest.main()

"""Packaged SQL009-013 together on synthetic data; /tmp-only PostgreSQL required."""
import hashlib
import os
from pathlib import Path
import sys
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_deployment_review as package

OWNER = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
TABLES = ('company', 'format', 'data', 'dividends', 'latest_prices',
          'achats', 'ventes', 'portefeuille', 'benefits')


def baseline(db):
    for role in ('anon', 'authenticated', 'service_role'):
        if not db.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
            db.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
    db.execute("""CREATE SCHEMA auth;
        CREATE TABLE auth.users(id uuid PRIMARY KEY);
        CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$
            SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
        CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql AS $$
            SELECT coalesce(nullif(current_setting('request.jwt.claim.role',true),''),'anon') $$;
        GRANT USAGE ON SCHEMA auth TO anon,authenticated,service_role;
        GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA auth TO anon,authenticated,service_role;
        CREATE SCHEMA storage;
        CREATE TABLE storage.buckets(id text PRIMARY KEY,public boolean NOT NULL);
        CREATE TABLE storage.objects(bucket_id text,name text,metadata jsonb,PRIMARY KEY(bucket_id,name));
    """)
    for name in ('002_public_market', '003_private_portfolio', '004_nonpersonal_archive',
                 '005_daily_reference', '006_versioned_history', '008_authenticated_market_access'):
        db.execute((ROOT / f'migrations/supabase/{name}.sql').read_text())
    db.execute('INSERT INTO auth.users VALUES(%s),(%s)', (OWNER, OTHER))
    db.execute("INSERT INTO public.company(id,name,bpa,cp,date) VALUES('company-fixture','Alpha',2,10,'2000-01-03T12:00Z')")
    db.execute("INSERT INTO public.format VALUES('format-fixture','Alpha','AAA')")
    db.execute("INSERT INTO public.data(id,c_name,pa,date) VALUES('original-tick','Alpha',25,'2000-01-03T12:00Z')")
    db.execute("INSERT INTO public.dividends(id,c_name,year,amount,confirmed) VALUES('original-dividend','Alpha',2000,1.5,true)")
    db.execute("INSERT INTO public.latest_prices VALUES('latest-fixture','Alpha',25,'2000-01-03T12:00Z','data')")
    db.execute('INSERT INTO public.portefeuille(user_id,c_name,quantity,total_cost) VALUES(%s,\'Alpha\',2,20),(%s,\'Alpha\',5,50)', (OWNER, OTHER))
    db.execute("INSERT INTO public.benefits(user_id,date,value) VALUES(%s,'2000-01-03',30)", (OWNER,))
    db.commit()


def snapshot(db):
    return {name: db.execute(sql.SQL("SELECT coalesce(jsonb_agg(to_jsonb(t)-'source' ORDER BY id),'[]'::jsonb) FROM public.{} t").format(sql.Identifier(name))).fetchone()[0]
            for name in TABLES}


@unittest.skipUnless(os.environ.get('APP_TEST_DATABASE') and os.environ.get('APP_REVIEW_BUNDLE'),
                     'Isolated database and explicit review bundle required')
class CombinedDeploymentSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = conninfo_to_dict(os.environ['APP_TEST_DATABASE'])
        if not cls.options.get('host', '').startswith('/tmp/'):
            raise RuntimeError('Only an isolated /tmp Unix socket is permitted')
        cls.bundle = Path(os.environ['APP_REVIEW_BUNDLE'])
        if not cls.bundle.resolve().is_relative_to((ROOT / 'private').resolve()):
            raise RuntimeError('Explicit private review bundle required')
        pin = os.environ.get('APP_REVIEW_MANIFEST_SHA256')
        if not pin:
            raise RuntimeError('External review manifest pin required')
        package.verify(cls.bundle, pin)
        cls.db = psycopg.connect(**cls.options)
        for name in ('auth', 'storage', 'app_archive', 'app_feed', 'market_admin', 'app_projection'):
            if cls.db.execute('SELECT to_regnamespace(%s)', (name,)).fetchone()[0] is not None:
                cls.db.close()
                raise RuntimeError('Existing test schema; refusing overwrite')
        baseline(cls.db)
        cls.before = snapshot(cls.db)
        for name in package.MIGRATIONS:
            cls.db.execute((cls.bundle / f'migrations/supabase/{name}.sql').read_text())
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.rollback()
        cls.db.close()

    def setUp(self):
        self.db.execute('SAVEPOINT deployment_case')

    def tearDown(self):
        self.db.execute('RESET ROLE')
        self.db.execute('ROLLBACK TO SAVEPOINT deployment_case')
        self.db.execute('RELEASE SAVEPOINT deployment_case')

    def as_user(self, user):
        self.db.execute('SET LOCAL ROLE authenticated')
        self.db.execute("SELECT set_config('request.jwt.claim.sub',%s,true),set_config('request.jwt.claim.role','authenticated',true)", (user,))

    def test_original_values_and_timestamps_remain_unchanged(self):
        self.assertEqual(snapshot(self.db), self.before)
        self.assertIsNone(self.db.execute("SELECT source FROM public.data WHERE id='original-tick'").fetchone()[0])

    def test_all_control_switches_start_disabled_and_private_rows_are_unseeded(self):
        for name in ('app_archive.control', 'app_feed.control', 'app_projection.control'):
            schema, table = name.split('.')
            self.assertEqual(self.db.execute(sql.SQL('SELECT enabled FROM {}.{}').format(sql.Identifier(schema), sql.Identifier(table))).fetchall(), [(False,)])
        for statement in ('SELECT count(*) FROM market_admin.admins', 'SELECT count(*) FROM app_archive.providers',
                          'SELECT count(*) FROM storage.buckets', 'SELECT count(*) FROM storage.objects'):
            self.assertEqual(self.db.execute(statement).fetchone()[0], 0)

    def test_no_anonymous_public_table_or_rpc_permissions_are_introduced(self):
        self.assertEqual(self.db.execute("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m')
            AND has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')""").fetchone()[0], 0)
        self.assertEqual(self.db.execute("""SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='public' AND has_function_privilege('anon',p.oid,'EXECUTE')""").fetchone()[0], 0)

    def test_authenticated_owner_rls_survives_combined_migrations(self):
        self.as_user(OWNER)
        rows = self.db.execute('SELECT user_id,quantity FROM public.portefeuille').fetchall()
        self.assertEqual([(str(owner), int(quantity)) for owner, quantity in rows], [(OWNER, 2)])
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
            self.db.execute('UPDATE public.portefeuille SET quantity=999')

    def test_authenticated_preview_is_disabled_without_private_details(self):
        self.as_user(OWNER)
        value = self.db.execute('SELECT public.read_shadow_market_feed()').fetchone()[0]
        self.assertEqual(value['status'], 'DISABLED')
        self.assertEqual(value['rows'], [])
        self.assertEqual(value['mode'], 'SHADOW_ONLY')
        self.assertNotIn('provider_namespace', value)

    def test_service_boundaries_reject_unconfigured_publication_and_reservation(self):
        self.db.execute('SET LOCAL ROLE service_role')
        statements = [
            ("SELECT public.reserve_market_archive(%s,'feed_0123456789abcdef','quotes',now(),now(),'COMPLETE',10)", ('a' * 64,)),
            ('SELECT public.publish_shadow_market_candidate(%s,%s)', ('{}', hashlib.sha256(b'{}').hexdigest())),
            ('SELECT public.publish_dividend_projection(%s,%s)', ('{}', hashlib.sha256(b'{}').hexdigest())),
            ('SELECT public.publish_fundamental_projection(%s,%s)', ('{}', hashlib.sha256(b'{}').hexdigest())),
        ]
        for statement, args in statements:
            with self.assertRaises(psycopg.Error), self.db.transaction():
                self.db.execute(statement, args)

    def test_non_admin_cannot_write_companies_or_operator_snapshots(self):
        self.as_user(OWNER)
        for statement in ("SELECT public.admin_update_company('Alpha','{\"bpa\":99}'::jsonb)",
                          "SELECT public.admin_record_operator_snapshot('{}'::jsonb)"):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.db.transaction():
                self.db.execute(statement)

    def test_stale_recovered_prices_cannot_create_current_valuation(self):
        value = self.db.execute("SELECT portfolio_private.daily_valuation(%s,'2026-10-29T18:00Z')", (OWNER,)).fetchone()[0]
        self.assertEqual(value['status'], 'PRICE_UNAVAILABLE')
        self.assertEqual(snapshot(self.db), self.before)

    def test_reapplying_non_idempotent_migration_fails_without_replacing_evidence(self):
        with self.assertRaises(psycopg.errors.DuplicateSchema), self.db.transaction():
            self.db.execute((self.bundle / 'migrations/supabase/009_private_object_archive.sql').read_text())
        self.assertEqual(snapshot(self.db), self.before)

    def test_interrupted_installation_rolls_back_all_five_staged_migrations(self):
        name = 'deployment_atomicity_' + uuid4().hex
        control = psycopg.connect(**self.options, autocommit=True)
        db = None
        try:
            control.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            options = {**self.options, 'dbname': name}
            db = psycopg.connect(**options)
            baseline(db)
            before = snapshot(db)
            db.commit()
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                with db.transaction():
                    for migration in package.MIGRATIONS:
                        db.execute((self.bundle / f'migrations/supabase/{migration}.sql').read_text())
                    raise RuntimeError('interrupted after final staged migration')
            for schema in ('app_archive', 'app_feed', 'market_admin', 'app_projection'):
                self.assertIsNone(db.execute('SELECT to_regnamespace(%s)', (schema,)).fetchone()[0])
            self.assertEqual(snapshot(db), before)
        finally:
            if db:
                db.close()
            control.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(name)))
            control.close()


if __name__ == '__main__':
    unittest.main()

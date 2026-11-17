#!/usr/bin/env python3
"""Install fresh-account portfolio tables; never import legacy private data."""

import argparse
import json

import psycopg

from stage_supabase import ROOT, connection_options, local_config


MARKER = "myInterpreter private portfolio v1"
TABLES = ("public.achats", "public.ventes", "public.portefeuille", "public.benefits",
          "portfolio_private.trade_requests")
FUNCTIONS = ("public.record_trade(uuid,text,text,numeric,numeric)",
             "portfolio_private.record_trade(uuid,text,text,numeric,numeric)")
MIGRATION = ROOT / "migrations/supabase/003_private_portfolio.sql"


def apply(config):
    with psycopg.connect(**connection_options(config)) as connection:
        if not connection.pgconn.ssl_in_use:
            raise ValueError("TLS is required")
        connection.execute("SET LOCAL lock_timeout='10s'")
        connection.execute("SELECT pg_advisory_xact_lock(182736451,3)")
        for table in TABLES:
            row = connection.execute("SELECT obj_description(to_regclass(%s),'pg_class')",
                                     (table,)).fetchone()
            exists = connection.execute("SELECT to_regclass(%s) IS NOT NULL", (table,)).fetchone()[0]
            if exists and row != (MARKER,):
                raise ValueError("Refusing to modify an unrelated portfolio table")
        for function in FUNCTIONS:
            row = connection.execute("SELECT obj_description(to_regprocedure(%s),'pg_proc')",
                                     (function,)).fetchone()
            exists = connection.execute("SELECT to_regprocedure(%s) IS NOT NULL", (function,)).fetchone()[0]
            if exists and row != (MARKER,):
                raise ValueError("Refusing to modify an unrelated portfolio function")
        namespace = connection.execute("SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname='portfolio_private'").fetchone()
        if namespace is not None and namespace != (MARKER,):
            raise ValueError("Refusing to modify an unrelated private schema")
        connection.execute(MIGRATION.read_text(), prepare=False)
        connection.execute("COMMENT ON SCHEMA portfolio_private IS 'myInterpreter private portfolio v1'")
        connection.execute("NOTIFY pgrst,'reload schema'")
    return {"status": "applied", "private_tables": 4, "legacy_private_rows_imported": 0,
            "client_settings_changed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = apply(local_config(ROOT / ".supabase-migration.env")) if args.apply else {
            "status": "prepared", "migration": str(MIGRATION.relative_to(ROOT)),
            "writes_require_apply": True}
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({"status": "failed", "error_category": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

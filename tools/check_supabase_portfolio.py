#!/usr/bin/env python3
"""Run private portfolio regression/role probes and roll back every fixture."""

import json

import psycopg

from stage_supabase import ROOT, connection_options, local_config


def check(config):
    with psycopg.connect(**connection_options(config)) as connection:
        if not connection.pgconn.ssl_in_use:
            raise ValueError("TLS is required")
        try:
            connection.execute("SET LOCAL statement_timeout='30s'")
            connection.execute((ROOT / "tests/supabase_portfolio.sql").read_text(), prepare=False)
        finally:
            connection.rollback()
        remaining = connection.execute("SELECT count(*) FROM auth.users WHERE id IN ('d75b3ae7-c67c-4cd9-b56b-bb28119b29a1','d75b3ae7-c67c-4cd9-b56b-bb28119b29a2')").fetchone()[0]
        connection.rollback()
        if remaining:
            raise ValueError("Unexpected pre-existing test identity")
    return {"ok": True, "owner_isolation": True, "anonymous_denied": True,
            "direct_mutations_denied": True, "atomic_trades_and_retries": True,
            "average_cost_preserved": True, "fixtures_rolled_back": True}


if __name__ == "__main__":
    try:
        print(json.dumps(check(local_config(ROOT / ".supabase-migration.env"))))
    except Exception as error:
        print(json.dumps({"ok": False, "error_category": type(error).__name__}))
        raise SystemExit(1)

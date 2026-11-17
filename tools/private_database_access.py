#!/usr/bin/env python3
"""Audit and optionally close anonymous SQL/API access without changing data.

Only permissions, RLS policies and future object defaults in the app's exposed
public schema change. Auth signup/login endpoints remain available. No row data
or credentials are printed. Receipts stay in an ignored local directory.
"""

import argparse
import json
from pathlib import Path

import psycopg
from psycopg import sql

from stage_supabase import ROOT, connection_options, local_config


def inventory(db):
    tables = db.execute("""SELECT c.relname, c.relkind, c.relrowsecurity,
        has_table_privilege('anon',c.oid,'SELECT'),
        has_table_privilege('anon',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') ORDER BY c.relname""").fetchall()
    result = []
    for name, kind, rls, anonymous_read, anonymous_write in tables:
        count = db.execute(
            sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(name))
        ).fetchone()[0]
        result.append(
            dict(
                name=name,
                kind=kind,
                rows=count,
                rls=rls,
                anonymous_read=anonymous_read,
                anonymous_write=anonymous_write,
            )
        )
    return {
        "tables": result,
        "anonymous_column_grants": db.execute("""SELECT count(*) FROM information_schema.column_privileges
                WHERE table_schema='public' AND grantee IN ('PUBLIC','anon')""").fetchone()[0],
        "anonymous_executable_rpc": db.execute("""SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='public' AND p.prokind='f' AND has_function_privilege('anon',p.oid,'EXECUTE')""").fetchone()[
            0
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    receipt = {"applied": False, "data_modified": False}
    try:
        with psycopg.connect(
            **connection_options(local_config(ROOT / ".supabase-migration.env"))
        ) as db:
            db.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
                + ("" if args.apply else " READ ONLY")
            )
            receipt["before"] = inventory(db)
            expected = set()
            for file in ["market_contract.json", "supplemental_contract.json"]:
                expected.update(
                    json.loads((ROOT / "migrations/supabase" / file).read_text())["tables"]
                )
            expected.update(
                ["achats", "ventes", "portefeuille", "benefits", "daily_price_reference"]
            )
            if {row["name"] for row in receipt["before"]["tables"]} - expected:
                raise RuntimeError("Unexpected public relations require review")
            if args.apply:
                db.execute(
                    (ROOT / "migrations/supabase/008_authenticated_market_access.sql").read_text()
                )
                receipt["after"] = inventory(db)
                if any(
                    row["anonymous_read"] or row["anonymous_write"]
                    for row in receipt["after"]["tables"]
                ):
                    raise RuntimeError("Anonymous relation privilege remains")
                if (
                    receipt["after"]["anonymous_column_grants"]
                    or receipt["after"]["anonymous_executable_rpc"]
                ):
                    raise RuntimeError("Anonymous column or RPC privilege remains")
                before = [(r["name"], r["rows"]) for r in receipt["before"]["tables"]]
                after = [(r["name"], r["rows"]) for r in receipt["after"]["tables"]]
                if before != after:
                    raise RuntimeError("Row count changed during permission migration")
                receipt["applied"] = True
        target = ROOT / "private/app-cutover-20261027/database-access.private.json"
        target.write_text(json.dumps(receipt, indent=2) + "\n")
        view = receipt.get("after", receipt["before"])
        print(
            json.dumps(
                {
                    "applied": receipt["applied"],
                    "data_modified": False,
                    "relations_checked": len(view["tables"]),
                    "anonymous_readable_relations": sum(
                        r["anonymous_read"] for r in view["tables"]
                    ),
                    "anonymous_writable_relations": sum(
                        r["anonymous_write"] for r in view["tables"]
                    ),
                    "anonymous_executable_rpc": view["anonymous_executable_rpc"],
                }
            )
        )
        return 0
    except Exception as error:
        print(json.dumps({"applied": False, "error_category": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

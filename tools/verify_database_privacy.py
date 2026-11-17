#!/usr/bin/env python3
"""Verify anonymous API denial and actual owner-only RLS, without data output."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg
from psycopg import sql

from stage_supabase import ROOT, connection_options, local_config


def verify_api_access(config, tables, opener=urlopen):
    """A bad API key must never count as successful privacy verification."""

    def status(path, schema=None):
        headers = {"apikey": config["SUPABASE_PUBLISHABLE_KEY"], "Accept": "application/json"}
        if schema is not None:
            headers["Accept-Profile"] = schema
        request = Request(config["SUPABASE_PROJECT_URL"].rstrip("/") + path, headers=headers)
        try:
            with opener(request, timeout=15) as response:
                return response.status
        except HTTPError as error:
            code = error.code
            error.close()
            return code

    gate_status = status("/auth/v1/settings")
    if gate_status != 200:
        return {
            "api_key_accepted": False,
            "api_privacy_verified": False,
            "api_check_blocker": "API_KEY_REJECTED"
            if gate_status in (401, 403)
            else "API_UNAVAILABLE",
            "auth_settings_status": gate_status,
            "anonymous_api_checks": [],
            "internal_schemas_not_exposed": None,
        }
    checks = []
    for table in tables:
        code = status("/rest/v1/" + table + "?select=*&limit=1")
        checks.append({"table": table, "status": code, "denied": code in (401, 403)})
    internal = all(
        status("/rest/v1/" + table + "?select=*&limit=0", schema) == 406
        for schema, table in [("realtime", "subscription"), ("extensions", "pg_stat_statements")]
    )
    verified = bool(checks) and all(item["denied"] for item in checks) and internal
    return {
        "api_key_accepted": True,
        "api_privacy_verified": verified,
        "api_check_blocker": None if verified else "ACCESS_CHECK_FAILED",
        "auth_settings_status": gate_status,
        "anonymous_api_checks": checks,
        "internal_schemas_not_exposed": internal,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = {"read_only": True, "anonymous_api_checks": []}
    try:
        config = local_config(ROOT / ".supabase-migration.env")
        with psycopg.connect(**connection_options(config)) as db:
            db.execute("SET TRANSACTION READ ONLY")
            tables = db.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') ORDER BY c.relname""").fetchall()
            # Check all non-system schemas for anonymous relation privileges.
            report["anonymous_readable_user_relations"] = (
                db.execute("""SELECT count(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema'
                AND n.nspname NOT IN ('extensions','storage','realtime','auth','graphql','graphql_public','supabase_functions','supabase_migrations')
                AND c.relkind IN ('r','p','v','m','f')
                AND has_table_privilege('anon',c.oid,'SELECT')""").fetchone()[0]
            )
            managed = db.execute("""SELECT n.nspname,c.relname,c.relrowsecurity FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname IN ('storage','realtime') AND c.relkind IN ('r','p')
                AND has_table_privilege('anon',c.oid,'SELECT') ORDER BY 1,2""").fetchall()
            report["managed_anonymous_visible_rows"] = 0
            report["storage_tables_rls_enabled"] = all(
                rls for schema, _, rls in managed if schema == "storage"
            )
            report["internal_managed_tables_without_rls"] = sum(not rls for _, _, rls in managed)
            report["public_storage_buckets"] = db.execute(
                "SELECT count(*) FROM storage.buckets WHERE public"
            ).fetchone()[0]
            db.execute("SET LOCAL ROLE anon")
            for schema, table, _ in managed:
                count = db.execute(
                    sql.SQL("SELECT count(*) FROM {}.{}").format(
                        sql.Identifier(schema), sql.Identifier(table)
                    )
                ).fetchone()[0]
                report["managed_anonymous_visible_rows"] += count
            db.execute("RESET ROLE")
            policies = db.execute("""SELECT tablename,qual FROM pg_policies WHERE schemaname='public'
                AND policyname='portfolio_owner_read' ORDER BY tablename""").fetchall()
            report["portfolio_owner_policies_intact"] = len(policies) == 4 and all(
                "auth.uid()" in expression and "user_id" in expression for _, expression in policies
            )
            report["portfolio_rls_enabled"] = (
                db.execute("""SELECT count(*)=4 AND bool_and(relrowsecurity)
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname IN ('achats','ventes','portefeuille','benefits')""").fetchone()[
                    0
                ]
            )
        report.update(verify_api_access(config, [table for (table,) in tables]))
        report["sql_privacy_verified"] = (
            report["anonymous_readable_user_relations"] == 0
            and report["portfolio_owner_policies_intact"]
            and report["portfolio_rls_enabled"]
            and report["storage_tables_rls_enabled"]
            and report["managed_anonymous_visible_rows"] == 0
            and report["public_storage_buckets"] == 0
        )
        report["ok"] = report["sql_privacy_verified"] and report["api_privacy_verified"]
        target = args.output or ROOT / "private" / (
            "database-privacy-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + ".private.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "ok": report["ok"],
                    "read_only": True,
                    "sql_privacy_verified": report["sql_privacy_verified"],
                    "api_privacy_verified": report["api_privacy_verified"],
                    "api_check_blocker": report["api_check_blocker"],
                    "anonymous_api_relations_denied": sum(
                        item["denied"] for item in report["anonymous_api_checks"]
                    ),
                    "anonymous_readable_user_relations": report[
                        "anonymous_readable_user_relations"
                    ],
                    "portfolio_owner_policies_intact": report["portfolio_owner_policies_intact"],
                    "portfolio_rls_enabled": report["portfolio_rls_enabled"],
                    "managed_anonymous_visible_rows": report["managed_anonymous_visible_rows"],
                    "storage_tables_rls_enabled": report["storage_tables_rls_enabled"],
                    "public_storage_buckets": report["public_storage_buckets"],
                    "internal_schemas_not_exposed": report["internal_schemas_not_exposed"],
                }
            )
        )
        return 0 if report["ok"] else 1
    except Exception as error:
        print(json.dumps({"ok": False, "error_category": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

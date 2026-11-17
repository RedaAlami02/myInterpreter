#!/usr/bin/env python3
"""Read-only Supabase connection checks with credential-free output."""

import json
from pathlib import Path

import psycopg
import requests

from stage_supabase import connection_options, local_config


ROOT = Path(__file__).resolve().parents[1]


def check():
    result = {"database": {}, "api": {}, "read_only_checks": True}
    try:
        config = local_config(ROOT / ".supabase-migration.env")
        options = connection_options(config)
    except Exception as error:
        return {"ok": False, "configuration_error_category": type(error).__name__}
    try:
        with psycopg.connect(**options) as connection:
            with connection.cursor() as cursor:
                # Pooler startup options do not necessarily reach the backend.
                # Set read-only explicitly before issuing verification queries.
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SELECT 1, current_setting('transaction_read_only')")
                value, read_only = cursor.fetchone()
                cursor.execute("SELECT pg_database_size(current_database())")
                size = cursor.fetchone()[0]
                cursor.execute("SELECT has_database_privilege(current_user,current_database(),'CREATE')")
                can_create_schema = cursor.fetchone()[0]
                result["database"] = {
                    "connected": value == 1,
                    "read_only_transaction": read_only == "on",
                    # pg_stat_ssl describes the pooler/backend leg. libpq
                    # reports the actual client connection used by this tool.
                    "tls_active": bool(connection.pgconn.ssl_in_use),
                    "database_bytes": size,
                    "migration_schema_permission": can_create_schema,
                }
            connection.rollback()
    except Exception as error:
        # Exception strings can contain connection details. Never emit them.
        result["database"] = {"connected": False, "error_category": type(error).__name__}
    base_url = config["SUPABASE_PROJECT_URL"].rstrip("/")
    for label, field in (("publishable", "SUPABASE_PUBLISHABLE_KEY"),
                         ("secret", "SUPABASE_SECRET_KEY")):
        key = config.get(field, "")
        if not key:
            result["api"][label] = {"configured": False}
            continue
        expected_prefix = "sb_publishable_" if label == "publishable" else "sb_secret_"
        if not key.startswith(expected_prefix):
            result["api"][label] = {"configured": True, "accepted": False,
                                      "key_kind_matches_field": False}
            continue
        try:
            with requests.get(base_url + "/auth/v1/settings", headers={"apikey": key},
                              timeout=(10, 30), allow_redirects=False) as response:
                result["api"][label] = {
                    "configured": True, "accepted": response.status_code == 200,
                    "key_kind_matches_field": True,
                    "http_status": response.status_code,
                }
        except Exception as error:
            result["api"][label] = {"configured": True, "accepted": False,
                                      "error_category": type(error).__name__}
    result["ok"] = (
        result["database"].get("connected", False)
        and result["database"].get("read_only_transaction", False)
        and result["database"].get("tls_active", False)
        and all(result["api"].get(key, {}).get("accepted", False)
                for key in ("publishable", "secret"))
    )
    return result


if __name__ == "__main__":
    report = check()
    print(json.dumps(report), flush=True)
    raise SystemExit(0 if report.get("ok") else 1)

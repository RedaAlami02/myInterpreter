#!/usr/bin/env python3
"""Read-only archive prerequisites; project SQL cannot establish organization quota."""

import json

import psycopg

from stage_supabase import ROOT, connection_options, local_config


def check():
    try:
        with psycopg.connect(
            **connection_options(local_config(ROOT / ".supabase-migration.env"))
        ) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            size, readonly = connection.execute(
                "SELECT pg_database_size(current_database()),current_setting('transaction_read_only')"
            ).fetchone()
            objects, unknown, storage_bytes = connection.execute("""
                SELECT count(*),count(*) FILTER (WHERE metadata->>'size' IS NULL
                    OR metadata->>'size' !~ '^[0-9]{1,12}$'),
                    coalesce(sum(CASE WHEN metadata->>'size' ~ '^[0-9]{1,12}$'
                        THEN (metadata->>'size')::numeric ELSE 0 END),0)
                FROM storage.objects
            """).fetchone()
            buckets, public_buckets, target, private = connection.execute("""
                SELECT count(*),count(*) FILTER (WHERE public),
                    count(*) FILTER (WHERE id='private-market-evidence'),
                    count(*) FILTER (WHERE id='private-market-evidence' AND NOT public)
                FROM storage.buckets
            """).fetchone()
            schema = connection.execute(
                "SELECT to_regnamespace('app_archive') IS NOT NULL"
            ).fetchone()[0]
            connection.rollback()
            return {
                "ok": True,
                "read_only": readonly == "on",
                "tls_active": bool(connection.pgconn.ssl_in_use),
                "database_bytes": size,
                "storage_objects": objects,
                "unknown_object_sizes": unknown,
                "known_project_storage_bytes": int(storage_bytes),
                "storage_buckets": buckets,
                "public_storage_buckets": public_buckets,
                "target_bucket_exists": bool(target),
                "target_bucket_private": bool(private),
                "archive_schema_exists": schema,
                "organization_storage_quota_verified": False,
                "activation_ready": False,
                "live_resources_changed": False,
            }
    except Exception as error:
        return {
            "ok": False,
            "error_category": type(error).__name__,
            "activation_ready": False,
        }


if __name__ == "__main__":
    report = check()
    print(json.dumps(report))
    raise SystemExit(0 if report.get("ok") else 1)

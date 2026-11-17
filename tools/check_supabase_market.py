#!/usr/bin/env python3
"""Check actual role isolation and PHP REST reads; print aggregates only."""

from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
import subprocess

import psycopg
from psycopg import sql

from stage_supabase import ROOT, connection_options, local_config
from migrate_supabase_market import TABLES


class CheckFailure(ValueError):
    def __init__(self, code, details=None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


def json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError("Unsupported SQL result type")


def query(method, attribute=None, value=None):
    result = {"method": method}
    if attribute is not None:
        result["attribute"] = attribute
    if method not in ("orderAsc", "orderDesc"):
        result["values"] = [value]
    return json.dumps(result)


def case(connection, name, table, order, limit=100, offset=0, filters=None, ranges=None):
    filters = filters or {}
    ranges = ranges or {}
    columns = ["id", *TABLES[table]["fields"]]
    clauses = [sql.SQL("{}=%s").format(sql.Identifier(field)) for field in filters]
    operators = {"gte": ">=", "gt": ">"}
    clauses += [sql.SQL("{} {} %s").format(sql.Identifier(field), sql.SQL(operators[operator]))
                for field, (operator, _) in ranges.items()]
    where = sql.SQL(" AND ").join(clauses)
    condition = sql.SQL(" WHERE ") + where if clauses else sql.SQL("")
    values = (*filters.values(), *(value for _, value in ranges.values()))
    base = sql.SQL(" FROM public.{}{}").format(sql.Identifier(table), condition)
    count = connection.execute(sql.SQL("SELECT count(*)") + base, values).fetchone()[0]
    ordering = sql.SQL(",").join(sql.SQL("{} {}").format(sql.Identifier(field), sql.SQL(direction)) for field, direction in order)
    rows = connection.execute(sql.SQL("SELECT {}{}").format(sql.SQL(",").join(map(sql.Identifier, columns)), base)
                              + sql.SQL(" ORDER BY {} LIMIT %s OFFSET %s").format(ordering),
                              (*values, limit, offset)).fetchall()
    expected = []
    for values in rows:
        row = dict(zip(columns, values))
        row["$id"] = row.pop("id")
        expected.append(row)
    queries = [query("equal", field, value) for field, value in filters.items()]
    queries += [query("greaterThanEqual" if operator == "gte" else "greaterThan", field, value)
                for field, (operator, value) in ranges.items()]
    queries += [query("orderAsc" if direction == "ASC" else "orderDesc", field) for field, direction in order if field != "id"]
    queries += [query("limit", value=limit), query("offset", value=offset)]
    return {"name": name, "collection": table, "queries": queries,
            "expected_count": count, "expected_rows": expected}


def check(access_token=None):
    config = local_config(ROOT / ".supabase-migration.env")
    with psycopg.connect(**connection_options(config)) as connection:
        connection.execute("SET LOCAL statement_timeout='30s'")
        connection.execute("SET LOCAL lock_timeout='5s'")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        # Each role and forbidden write is contained in a savepoint that is
        # rolled back unconditionally, even if a privilege regression exists.
        role_results = []
        if connection.execute("SELECT has_table_privilege('anon','public.company','SELECT')").fetchone()[0]:
            raise CheckFailure('anonymous_market_access')
        role_results.append({'role':'anon','public_read':False,'writes_denied':True})
        for role in ("authenticated", "service_role"):
            connection.execute("SAVEPOINT role_probe")
            try:
                connection.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                if connection.execute("SELECT count(*) FROM public.company").fetchone()[0] != 81:
                    raise CheckFailure("public_role_read")
                denied = 0
                for statement in (
                    "INSERT INTO public.company(id,name) VALUES('_permission_probe','_permission_probe')",
                    "UPDATE public.company SET name=name WHERE false",
                    "DELETE FROM public.company WHERE false",
                    "SELECT count(*) FROM migration_stage.documents",
                ):
                    connection.execute("SAVEPOINT denied_probe")
                    try:
                        connection.execute(statement)
                    except psycopg.errors.InsufficientPrivilege:
                        denied += 1
                    finally:
                        connection.execute("ROLLBACK TO SAVEPOINT denied_probe")
                        connection.execute("RELEASE SAVEPOINT denied_probe")
                if denied != 4:
                    raise CheckFailure("unexpected_role_access")
                role_results.append({"role": role, "public_read": True, "writes_denied": True,
                                     "private_staging_denied": True})
            finally:
                connection.execute("ROLLBACK TO SAVEPOINT role_probe")
                connection.execute("RELEASE SAVEPOINT role_probe")
        name = connection.execute("SELECT name FROM public.company ORDER BY name LIMIT 1").fetchone()[0]
        cases = [
            case(connection, "company_directory", "company", [("name", "ASC"), ("id", "DESC")]),
            case(connection, "symbol_lookup", "format", [("name", "ASC"), ("id", "DESC")]),
            case(connection, "recent_history", "data", [("date", "DESC"), ("id", "DESC")], 500),
            case(connection, "history_second_page", "data", [("date", "DESC"), ("id", "DESC")], 5, 500),
            case(connection, "company_history", "data", [("date", "DESC"), ("id", "DESC")], 100, filters={"c_name": name}),
            case(connection, "dividend_calendar", "dividends", [("c_name", "ASC"), ("id", "DESC")], 200, filters={"year": 2026}),
            case(connection, "latest_quotes", "latest_prices", [("c_name", "ASC"), ("id", "DESC")], 200),
            case(connection, "history_date_filter", "data", [("date", "DESC"), ("id", "DESC")], 5,
                 filters={"c_name": name}, ranges={"date": ("gte", "2026-01-01T00:00:00Z")}),
        ]
        size = connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        connection.rollback()
    # Credentials are passed over a private pipe, never command arguments,
    # process environment, logs, exception strings, or the returned report.
    if access_token is None:
        return {"ok": True, "sql_role_checks":role_results,"anonymous_access_denied":True,
                "authenticated_php_api_verified":False,
                "php_api_status":"requires_in_memory_authenticated_token", "database_bytes":size}
    payload = {"access_token":access_token, "project_url": config["SUPABASE_PROJECT_URL"],
               "publishable_key": config["SUPABASE_PUBLISHABLE_KEY"], "cases": cases}
    result = subprocess.run(["php", str(ROOT / "tools/check_supabase_market.php")],
                            input=json.dumps(payload, default=json_value), text=True,
                            capture_output=True, timeout=240, check=False)
    if result.returncode != 0:
        try:
            diagnostic = json.loads(result.stdout)
            details = {key: value for key, value in diagnostic.items()
                       if key in ("phase", "case_index", "error_category")}
        except (ValueError, AttributeError):
            details = {}
        raise CheckFailure("php_public_api", details)
    php_report = json.loads(result.stdout)
    if php_report.get("ok") is not True:
        raise CheckFailure("php_public_api")
    return {"ok": True, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "database_bytes": size, "sql_role_checks": role_results,
            "php_public_api_checks": php_report["php_public_api_checks"],
            "authenticated_php_api_verified":True, "anonymous_access_denied":True, "credential_values_printed": False, "permission_probes_rolled_back": True}


if __name__ == "__main__":
    os.umask(0o077)
    try:
        report = check()
        (ROOT / "backup_live_recovery_20261022/supabase_market_access_report.json").write_text(
            json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
    except Exception as error:
        diagnostic = {"ok": False, "error_category": type(error).__name__}
        if isinstance(error, CheckFailure):
            diagnostic.update({"check": error.code, "details": error.details})
        print(json.dumps(diagnostic), flush=True)
        raise SystemExit(1)

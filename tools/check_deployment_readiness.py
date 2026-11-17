#!/usr/bin/env python3
"""Read-only hosted deployment facts. This tool never installs or enables services."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from psycopg import sql

from stage_supabase import ROOT, connection_options, local_config

ZONE = 'Africa/Casablanca'
DATABASE_GUARD = 350_000_000
PRIVATE_SCHEMAS = ('app_archive', 'app_feed', 'market_admin', 'app_projection')
CONTROL_TABLES = ('app_archive.control', 'app_feed.control', 'app_projection.control')
RPCS = (
    'public.reserve_market_archive(text,text,text,timestamptz,timestamptz,text,bigint)',
    'public.finalize_market_archive(text)',
    'public.market_archive_slot_complete(text,text,timestamptz)',
    'public.read_shadow_market_feed()',
    'public.publish_shadow_market_candidate(text,text)',
    'public.record_daily_valuation()',
    'public.admin_update_company(text,jsonb)',
    'public.admin_record_operator_snapshot(jsonb)',
    'public.publish_dividend_projection(text,text)',
    'public.publish_fundamental_projection(text,text)',
)


def sample_instants(moment):
    """Replay dates, near-term day boundaries and monthly future gate samples."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError('An aware UTC anchor is required')
    anchor = moment.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = {datetime(2026, 9, 30, 12, tzinfo=timezone.utc),
              datetime(2026, 10, 9, 12, tzinfo=timezone.utc)}
    for offset in range(-2, 63):
        day = anchor + timedelta(days=offset)
        result.update((day + timedelta(minutes=30), day + timedelta(hours=15, minutes=45)))
    for offset in range(13):
        year, month = divmod(anchor.year * 12 + anchor.month - 1 + offset, 12)
        result.add(datetime(year, month + 1, 15, 12, tzinfo=timezone.utc))
    return sorted(result)


def compare_clocks(rows):
    zone = ZoneInfo(ZONE)
    mismatches = []
    for stamp, hosted in rows:
        expected = stamp.astimezone(zone).replace(tzinfo=None)
        if hosted != expected:
            mismatches.append({'utc': stamp.astimezone(timezone.utc).isoformat(),
                               'hosted_local': hosted.isoformat(),
                               'python_local': expected.isoformat()})
    return {'zone': ZONE, 'samples': len(rows), 'passed': bool(rows) and not mismatches,
            'mismatch_count': len(mismatches), 'mismatches': mismatches,
            'scope': 'SAMPLED_INSTANTS_NOT_ALL_FUTURE_TIMEZONE_RULES'}


def collect(db, moment):
    # This must precede every catalog or application query, including read-only probes.
    db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    db.execute("SET LOCAL statement_timeout = '15000ms'")
    size, readonly = db.execute(
        "SELECT pg_database_size(current_database()),current_setting('transaction_read_only')"
    ).fetchone()
    if readonly != 'on':
        raise RuntimeError('Read-only transaction was not established')
    objects, unknown, total = db.execute("""
        SELECT count(*), count(*) FILTER (WHERE metadata->>'size' IS NULL
            OR metadata->>'size' !~ '^[0-9]{1,12}$'),
            coalesce(sum(CASE WHEN metadata->>'size' ~ '^[0-9]{1,12}$'
                THEN (metadata->>'size')::numeric ELSE 0 END),0)
        FROM storage.objects
    """).fetchone()
    buckets, public_buckets, target, private_target = db.execute("""
        SELECT count(*),count(*) FILTER (WHERE public),
            count(*) FILTER (WHERE id='private-market-evidence'),
            count(*) FILTER (WHERE id='private-market-evidence' AND NOT public)
        FROM storage.buckets
    """).fetchone()
    schemas = {name: bool(db.execute('SELECT to_regnamespace(%s) IS NOT NULL', (name,)).fetchone()[0])
               for name in PRIVATE_SCHEMAS}
    rpcs = {name: bool(db.execute('SELECT to_regprocedure(%s) IS NOT NULL', (name,)).fetchone()[0])
            for name in RPCS}
    controls = {}
    for table in CONTROL_TABLES:
        exists = db.execute('SELECT to_regclass(%s) IS NOT NULL', (table,)).fetchone()[0]
        if not exists:
            controls[table] = {'state': 'NOT_INSTALLED'}
            continue
        schema, name = table.split('.')
        rows = db.execute(sql.SQL('SELECT enabled FROM {}.{}').format(
            sql.Identifier(schema), sql.Identifier(name))).fetchall()
        controls[table] = {'state': ('INVALID_CONTROL_ROWS' if len(rows) != 1 else
                                    'ENABLED' if rows[0][0] else 'DISABLED'),
                           'rows': len(rows)}
    stamps = sample_instants(moment)
    rows = db.execute(
        'SELECT stamp, stamp AT TIME ZONE %s FROM unnest(%s::timestamptz[]) AS samples(stamp) ORDER BY stamp',
        (ZONE, stamps),
    ).fetchall()
    clocks = compare_clocks(rows)
    if len(rows) != len(stamps):
        raise RuntimeError('Incomplete timezone evidence')
    db.rollback()
    blockers = []
    if not db.pgconn.ssl_in_use:
        blockers.append('SQL_TLS_NOT_ACTIVE')
    if size >= DATABASE_GUARD:
        blockers.append('DATABASE_AT_OR_OVER_STAGED_GUARD')
    if unknown:
        blockers.append('UNKNOWN_OBJECT_SIZES')
    if public_buckets:
        blockers.append('PUBLIC_STORAGE_BUCKET_EXISTS')
    if not private_target:
        blockers.append('PRIVATE_ARCHIVE_BUCKET_NOT_READY')
    if not all(schemas.values()) or not all(rpcs.values()):
        blockers.append('STAGED_SERVICES_NOT_FULLY_INSTALLED')
    if any(control['state'] == 'INVALID_CONTROL_ROWS' for control in controls.values()):
        blockers.append('INVALID_CONTROL_ROWS')
    if not clocks['passed']:
        blockers.append('HOSTED_PYTHON_TIMEZONE_MISMATCH')
    return {
        'ok': True, 'checked_at': moment.astimezone(timezone.utc).isoformat(),
        'read_only': True, 'tls_active': bool(db.pgconn.ssl_in_use),
        'database_bytes': size, 'staged_database_guard_bytes': DATABASE_GUARD,
        'database_guard_headroom_bytes': max(0, DATABASE_GUARD - size),
        'storage_objects': objects, 'unknown_object_sizes': unknown,
        'known_project_storage_bytes': int(total), 'storage_buckets': buckets,
        'public_storage_buckets': public_buckets, 'target_bucket_exists': bool(target),
        'target_bucket_private': bool(private_target), 'schemas': schemas,
        'rpcs': rpcs, 'controls': controls, 'timezone': clocks,
        'confirmed_blockers': blockers,
        'not_assessed': ['INDEPENDENT_REVIEW', 'SCOPED_DEPLOYMENT_AUTHORIZATION',
                         'MANAGEMENT_DEPLOYMENT_ACCESS', 'ORGANIZATION_STORAGE_HEADROOM',
                         'PRIVATE_ACTIONS_AND_ARTIFACT_HEADROOM', 'SMTP_DELIVERY',
                         'ANDROID_DEVICE_ACCEPTANCE', 'HOSTED_COLLECTION_ACCEPTANCE'],
        'activation_ready': False, 'live_resources_changed': False,
    }


def check(connect=None, config=None, moment=None):
    try:
        values = local_config(ROOT / '.supabase-migration.env') if config is None else config
        with (connect or psycopg.connect)(**connection_options(values)) as db:
            return collect(db, moment or datetime.now(timezone.utc))
    except Exception as error:
        # Exception text can include database host/user/URI; report the type only.
        return {'ok': False, 'error_category': type(error).__name__,
                'activation_ready': False, 'live_resources_changed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        target = args.output.absolute()
        if not target.resolve().is_relative_to((ROOT / 'private').resolve()):
            raise ValueError('Reports must remain in the private directory')
        if target.exists() or target.is_symlink():
            raise FileExistsError('Preserve the earlier receipt')
        report = check()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x') as stream:
            stream.write(json.dumps(report, indent=2) + '\n')
        safe = {name: report.get(name) for name in (
            'ok', 'read_only', 'tls_active', 'database_bytes', 'database_guard_headroom_bytes',
            'public_storage_buckets', 'target_bucket_private', 'confirmed_blockers', 'error_category')}
        safe['timezone_samples_match'] = report.get('timezone', {}).get('passed')
        safe['activation_ready'] = False
        print(json.dumps(safe))
        return 0 if report['ok'] else 1
    except Exception as error:
        print(json.dumps({'ok': False, 'error_category': type(error).__name__, 'activation_ready': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

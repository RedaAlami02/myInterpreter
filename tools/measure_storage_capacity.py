#!/usr/bin/env python3
"""Read-only capacity snapshot. Never enables jobs or modifies remote tables.

Run again after representative collection to measure a real interval; changes
from migration, deleted accounts, maintenance and bloat are not ingestion rates.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import psycopg
from psycopg import sql
from stage_supabase import local_config, connection_options


def measure(db):
    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    db.execute("SET LOCAL statement_timeout='30s'")
    result = {'contract': 'storage-capacity-snapshot/v1',
              'measured_at': datetime.now(timezone.utc).isoformat(),
              'read_only': True,
              'database_bytes': db.execute('SELECT pg_database_size(current_database())').fetchone()[0],
              'tables': []}
    tables = db.execute("""SELECT n.nspname,c.relname,pg_total_relation_size(c.oid),
        pg_relation_size(c.oid),pg_indexes_size(c.oid)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind='r' AND n.nspname NOT LIKE 'pg_%'
        AND n.nspname<>'information_schema' ORDER BY 3 DESC""").fetchall()
    for schema, name, total, heap, indexes in tables:
        result['tables'].append({'schema': schema, 'table': name,
                                'total_bytes': total, 'heap_bytes': heap, 'index_bytes': indexes})
    result['archive_objects'] = [dict(zip(('kind', 'state', 'count', 'compressed_bytes'), row))
        for row in db.execute('SELECT kind,state,count(*),sum(compressed_bytes) '
                              'FROM app_archive.objects GROUP BY kind,state').fetchall()]
    result['storage'] = [dict(zip(('bucket', 'objects', 'bytes'), row))
        for row in db.execute("""SELECT bucket_id,count(*),sum(CASE
            WHEN metadata->>'size' ~ '^[0-9]+$' THEN (metadata->>'size')::bigint ELSE 0 END)
            FROM storage.objects GROUP BY bucket_id""").fetchall()]
    return result


def capacity_status(database_bytes, guard_bytes, warning_bytes):
    if guard_bytes <= 0 or warning_bytes < 0:
        raise ValueError('INVALID_CAPACITY_LIMITS')
    remaining = guard_bytes - database_bytes
    return {'guard_bytes': guard_bytes, 'headroom_bytes': remaining,
            'status': 'BLOCKED' if remaining <= 0 else
                      'WARNING' if remaining <= warning_bytes else 'OK',
            'limit_source': 'OPERATOR_SUPPLIED_NOT_LIVE_GUARD_VERIFICATION'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('.supabase-migration.env'))
    parser.add_argument('--ca', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--guard-bytes', type=int, default=350_000_000)
    parser.add_argument('--warning-bytes', type=int, default=20_000_000)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Preserve the existing snapshot; choose a new output path')
    opts = connection_options(local_config(args.config))
    opts.update(sslmode='verify-full', sslrootcert=str(args.ca.resolve()), connect_timeout=15)
    try:
        with psycopg.connect(**opts) as db:
            result = measure(db)
        result['capacity'] = capacity_status(result['database_bytes'], args.guard_bytes, args.warning_bytes)
        if args.previous:
            prior = json.loads(args.previous.read_text())
            previous_time = datetime.fromisoformat(prior['measured_at'])
            elapsed = (datetime.fromisoformat(result['measured_at']) - previous_time).total_seconds()
            if previous_time.tzinfo is None or elapsed <= 0:
                raise ValueError('INVALID_PRIOR_SNAPSHOT')
            result['comparison'] = {'elapsed_seconds': elapsed,
                'database_delta_bytes': result['database_bytes'] - prior['database_bytes'],
                'interpretation': 'OBSERVED_DELTA_NOT_A_CERTIFIED_INGESTION_RATE'}
        with args.output.open('x') as handle:
            json.dump(result, handle, indent=2, default=str)
            handle.write('\n')
        print(json.dumps({'ok': True, 'database_bytes': result['database_bytes'],
                          'read_only': True, 'capacity': result['capacity'], 'comparison': result.get('comparison')}))
    except Exception:
        # Database exceptions may contain credentials or private source details.
        print(json.dumps({'ok': False, 'code': 'CAPACITY_SNAPSHOT_FAILED'}))
        return 1
    return 0 if result['capacity']['status'] == 'OK' else 2


if __name__ == '__main__':
    raise SystemExit(main())

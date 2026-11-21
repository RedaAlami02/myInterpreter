#!/usr/bin/env python3
"""Read-only public-market RPC and history-stage latency comparison.

No HTTP sessions or real user claims are used. No rows or tokens are logged.
"""
import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from stage_supabase import connection_options, local_config

ROOT = Path(__file__).resolve().parents[1]
DAILY_HISTORY = """SELECT * FROM (
    SELECT DISTINCT ON ((date AT TIME ZONE 'UTC')::date) *
    FROM public.data WHERE c_name=%s
    ORDER BY (date AT TIME ZONE 'UTC')::date DESC,date DESC,id DESC
) d ORDER BY date DESC"""
HISTORY = """SELECT * FROM public.data WHERE c_name=%s
    ORDER BY date DESC,id DESC LIMIT 500 OFFSET %s"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    day = datetime.now(timezone.utc).strftime('%Y%m%d')
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'docs/performance' / f'detail_measurement_{day}.json')
    args = parser.parse_args()
    report = {
        'as_of_utc': datetime.now(timezone.utc).isoformat(),
        'mode': 'read-only SQL; authenticated role; synthetic non-user claim for '
                'public market RPCs; no HTTP session impersonation',
        'queries': {},
    }
    with psycopg.connect(**connection_options(local_config(ROOT / '.supabase-migration.env'))) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        db.execute("SET LOCAL statement_timeout='15s'")
        db.execute('SET LOCAL ROLE authenticated')
        claims = {'role': 'authenticated', 'sub': '00000000-0000-0000-0000-000000000001'}
        db.execute("SELECT set_config('request.jwt.claims',%s,true)", (json.dumps(claims),))
        queries = [
            ('market_feed_rpc', 'SELECT public.read_shadow_application_feed_recurring_v1()', ()),
            ('latest_price_rpc', 'SELECT * FROM public.read_latest_price_references_v1() WHERE c_name=%s', ('ADDOHA',)),
            ('recent_sessions_rpc', 'SELECT public.read_recent_market_sessions(%s,5)', ('ADH',)),
            ('daily_history_candidate', DAILY_HISTORY, ('ADDOHA',)),
        ]
        for label, query, params in queries:
            db.execute('SAVEPOINT probe')
            try:
                elapsed = []
                for _ in range(5):
                    start = time.perf_counter()
                    rows = db.execute(query, params).fetchall()
                    elapsed.append((time.perf_counter() - start) * 1000)
                plan = db.execute('EXPLAIN (ANALYZE,FORMAT JSON) ' + query, params).fetchone()[0][0]
                entry = {
                    'n': 5, 'median_roundtrip_ms': round(statistics.median(elapsed), 1),
                    'min_ms': round(min(elapsed), 1), 'max_ms': round(max(elapsed), 1),
                    'rows': len(rows), 'server_execution_ms': plan['Execution Time'],
                }
                if label == 'market_feed_rpc':
                    entry['feed_status'] = rows[0][0].get('status')
                report['queries'][label] = entry
            except Exception as error:
                report['queries'][label] = {'error': type(error).__name__}
            db.execute('ROLLBACK TO SAVEPOINT probe')

        expected = db.execute("""SELECT DISTINCT ON ((date AT TIME ZONE 'UTC')::date) id
            FROM public.data WHERE c_name=%s
            ORDER BY (date AT TIME ZONE 'UTC')::date DESC,date DESC,id DESC""", ('ADDOHA',)).fetchall()
        seen = set()
        deduplicated = []
        for identifier, stamp in db.execute(
            'SELECT id,date FROM public.data WHERE c_name=%s ORDER BY date DESC,id DESC',
            ('ADDOHA',),
        ).fetchall():
            date_key = stamp.astimezone(timezone.utc).isoformat()[:10]
            if date_key not in seen:
                seen.add(date_key)
                deduplicated.append((identifier,))
        report['daily_history_equivalent_ids_and_order'] = expected == deduplicated

        baseline = []
        for _ in range(5):
            start = time.perf_counter()
            offset = count = requests = 0
            while True:
                rows = db.execute(HISTORY, ('ADDOHA', offset)).fetchall()
                requests += 1
                count += len(rows)
                offset += 500
                if len(rows) < 500:
                    break
            baseline.append((time.perf_counter() - start) * 1000)
        report['full_history_baseline'] = {
            'n': 5, 'requests_per_load': requests, 'rows': count,
            'median_ms': round(statistics.median(baseline), 1),
            'min_ms': round(min(baseline), 1), 'max_ms': round(max(baseline), 1),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['daily_history_equivalent_ids_and_order'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # Database exception text can identify private infrastructure.
        print('Read-only measurement failed: ' + type(error).__name__)
        raise SystemExit(1)

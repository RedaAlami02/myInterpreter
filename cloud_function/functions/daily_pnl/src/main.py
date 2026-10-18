"""Private, idempotent weekday portfolio valuations. No schema changes."""
import hashlib
import math
import os
from importlib.resources import files
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from appwrite.client import Client
from appwrite.exception import AppwriteException
from appwrite.query import Query
from appwrite.services.databases import Databases

# Use packaged IANA data: some runtimes ship truncated/stale host timezone files.
with files('tzdata').joinpath('zoneinfo/Africa/Casablanca').open('rb') as zone_file:
    ZONE = ZoneInfo.from_file(zone_file, key='Africa/Casablanca')
DB_ID = 'myinterpreter'


def unpack(doc):
    if isinstance(doc, dict):
        return doc
    return {'$id': doc.id, **doc._data}


def all_docs(db, collection, queries=None):
    cursor = None
    while True:
        query = list(queries or []) + [Query.limit(100), Query.order_asc('$id')]
        if cursor:
            query.append(Query.cursor_after(cursor))
        result = db.list_documents(DB_ID, collection, queries=query)
        rows = result['documents'] if isinstance(result, dict) else result.documents
        for row in rows:
            yield unpack(row)
        if len(rows) < 100:
            break
        cursor = unpack(rows[-1])['$id']


def number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Non-finite valuation input')
    return result


def valuation(holdings, prices, now):
    total = Decimal(0)
    for holding in holdings:
        quantity, cost = number(holding['quantity']), number(holding['total_cost'])
        if quantity < 0 or cost < 0:
            raise ValueError('Invalid position')
        if quantity == 0:
            if cost != 0:
                raise ValueError('Cost without quantity')
            continue
        price = prices[holding['c_name']]
        observed = datetime.fromisoformat(price['date'].replace('Z', '+00:00'))
        if observed.tzinfo is None:
            raise ValueError('Missing price timezone')
        local = observed.astimezone(ZONE)
        # Require this day's closing-window observation, not a stale morning price.
        if local.date() != now.date() or local.time() < time(15, 45) or observed > now:
            raise ValueError('No closing-window price')
        amount = number(price['pa'])
        if amount <= 0:
            raise ValueError('Missing price')
        total += quantity * amount - cost
    result = float(total.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    if not math.isfinite(result):
        raise ValueError('Invalid valuation')
    return result


def run(db, now):
    now = now.astimezone(ZONE)
    if now.weekday() >= 5 or not time(17) <= now.time() < time(19):
        return {'status': 'outside_window', 'created': 0}
    day = now.date().isoformat()
    next_day = (now.date() + timedelta(days=1)).isoformat()
    positions = defaultdict(list)
    for row in all_docs(db, 'portefeuille'):
        if row.get('user_id'):
            positions[row['user_id']].append(row)
    # A previously tracked portfolio that has sold all positions has zero unrealized P&L.
    for row in all_docs(db, 'benefits', [Query.select(['$id', 'user_id'])]):
        if row.get('user_id'):
            positions.setdefault(row['user_id'], [])
    prices = {}
    for row in all_docs(db, 'latest_prices'):
        name = row.get('c_name')
        if name in prices:
            # Ambiguous quotes must not silently produce a financial record.
            prices[name] = None
        else:
            prices[name] = row
    counts = {'status': 'complete', 'date': day, 'created': 0, 'existing': 0, 'skipped': 0, 'failed': 0}
    for uid, holdings in positions.items():
        try:
            existing = db.list_documents(DB_ID, 'benefits', queries=[
                Query.equal('user_id', uid),
                Query.greater_than_equal('date', day + 'T00:00:00.000+00:00'),
                Query.less_than('date', next_day + 'T00:00:00.000+00:00'),
                Query.limit(1),
            ])
            rows = existing['documents'] if isinstance(existing, dict) else existing.documents
            if rows:
                counts['existing'] += 1
                continue
            try:
                value = valuation(holdings, prices, now)
            except (KeyError, TypeError, ValueError, InvalidOperation):
                counts['skipped'] += 1
                continue
            doc_id = 'pnl_' + hashlib.sha256((uid + ':' + day).encode()).hexdigest()[:32]
            db.create_document(DB_ID, 'benefits', doc_id, {
                'user_id': uid, 'date': day + 'T00:00:00.000+00:00', 'value': value,
            }, permissions=[f'read("user:{uid}")', f'write("user:{uid}")'])
            counts['created'] += 1
        except AppwriteException as exc:
            if exc.code == 409:
                counts['existing'] += 1  # Concurrent retry already created this date.
            else:
                counts['failed'] += 1
    if counts['failed'] or counts['skipped']:
        counts['status'] = 'partial'
    return counts


def main(context):
    # Dynamic execution key only. No stored credentials or public execution access.
    key = (context.req.headers or {}).get('x-appwrite-key')
    if not key:
        return context.res.json({'status': 'unauthorized'}, 401)
    try:
        client = (Client().set_endpoint(os.environ['APPWRITE_ENDPOINT'])
                  .set_project(os.environ['APPWRITE_PROJECT_ID']).set_key(key))
        result = run(Databases(client), datetime.now(timezone.utc))
    except Exception:
        context.error('Daily P&L failed; inspect configuration and database availability.')
        return context.res.json({'status': 'failed'}, 500)
    # Counts only: never log account identifiers, holdings, values or raw SDK errors.
    context.log(str(result))
    return context.res.json(result, 200 if result['status'] != 'partial' else 503)

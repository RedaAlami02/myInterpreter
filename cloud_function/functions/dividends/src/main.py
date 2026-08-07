"""Dividend calendar scraper.

Fetches the upstream dividend calendar for the current and next year and
upserts it into the `dividends` collection.

Why weekly rather than yearly: the calendar fills in progressively as each AGM
votes, from roughly March to July. On 7 August 2026, twelve issuers still had no
confirmed ex-date. A yearly poll would be months stale for a large minority of
the market; a weekly one costs ~52 executions a year.

Why we do not predict dates ourselves: measured across 197 company-pairs from
the 2022-2026 calendars, the year-over-year drift of the ex-date has a 7-day
median and a 26% tail beyond two weeks. The source already publishes its own
estimate — as a payment *range* with no ex-date — and flagging theirs is more
honest than inventing ours. `confirmed` carries that distinction to the UI.

Amounts are never predicted: 51% of dividends move more than 10% year over year
and only 25% are unchanged, so last year's figure is history, not a forecast.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from appwrite.id import ID

# The runtime imports this file as `function.src.main`, so a sibling module is
# not importable by bare name — the old `parser` only resolved because Python
# 3.9 still ships a built-in of that name, which shadowed our file and broke the
# import a different way. Put this directory on the path and be explicit.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from div_parser import CAL_URL, parse_calendar, normalise_name, resolve, dedupe  # noqa: E402

try:
    from sources import CALENDAR_SOURCE_NAME, FUNDAMENTALS_SUPABASE, FUNDAMENTALS_ORIGIN
except ImportError:  # no sources.py — copy sources.example.py, or set these in
    # the function's environment variables (Console → Settings → Variables).
    CALENDAR_SOURCE_NAME  = os.environ.get("CALENDAR_SOURCE_NAME", "calendar")
    FUNDAMENTALS_SUPABASE = os.environ.get("FUNDAMENTALS_SUPABASE", "")
    FUNDAMENTALS_ORIGIN   = os.environ.get("FUNDAMENTALS_ORIGIN", "")

DB_ID = "myinterpreter"
SOURCE = CALENDAR_SOURCE_NAME

# Non-secret defaults; the API key comes from the per-execution dynamic key.
DEFAULT_ENDPOINT = "https://fra.cloud.appwrite.io/v1"
DEFAULT_PROJECT = "6a12447800077d5113ae"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
}
TIMEOUT = 30
ATTEMPTS = 3

# The fundamentals feed publishes the same figure a year earlier in its own
# units: the dividend paid during calendar year Y comes out of fiscal year
# Y-1, and dpa-corpo[Y-1] matches the calendar's Y amount. Divergence beyond
# this tolerance means one of the two sources has changed something.
IDB_URL = FUNDAMENTALS_SUPABASE
CROSSCHECK_TOLERANCE = 0.02   # 2%


def log_error(db, source, level, message, ctx=None, context=None):
    """Record a problem in the 'errors' collection. Never raises."""
    try:
        db.create_document(DB_ID, "errors", ID.unique(), {
            'ts':      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
            'source':  source[:40],
            'level':   level[:16],
            'message': str(message)[:1000],
            'context': (str(ctx)[:2000] if ctx else None),
        })
    except Exception as e:
        if context:
            context.log(f"could not record error: {e}")


def fetch_calendar(year, context=None):
    """The calendar page for one year, or None if that year has none yet."""
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            r = requests.get(CAL_URL.format(year=year), headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
        except Exception as exc:
            last = exc
            if context:
                context.log(f"{year} calendar attempt {attempt}/{ATTEMPTS}: {exc}")
    raise last


def build_index(db):
    """Normalised name -> stored company name, from `company` and `format`."""
    index = {}
    for coll, keys in (("company", ("name", "ext_name")), ("format", ("name", "symbol"))):
        # SDK v22 returns a typed DocumentList, not a dict; row fields live
        # under ._data. Same unwrapping getprice and onboard_company use.
        page = db.list_documents(DB_ID, coll, queries=[Query.limit(200)])
        for d in [x._data for x in page.documents]:
            stored = d.get("name")
            if not stored:
                continue
            for k in keys:
                if d.get(k):
                    index.setdefault(normalise_name(d[k]), stored)
    return index


def idb_dpa(soc, year):
    """The fundamentals feed's dividend-per-share for a year, for cross-checking."""
    try:
        body = json.dumps({"table": "dpa-corpo",
                           "options": {"filter": {"column": "Société", "value": soc},
                                       "single": True}})
        r = requests.post(IDB_URL, data=body, timeout=15, headers={
            **HEADERS, "Content-Type": "application/json",
            "Referer": FUNDAMENTALS_ORIGIN + "/", "Origin": FUNDAMENTALS_ORIGIN})
        if not r.ok:
            return None
        d = (r.json() or {}).get("data")
        return float(d[str(year)]) if isinstance(d, dict) and d.get(str(year)) is not None else None
    except Exception:
        return None


def _api_key(context):
    """Prefer Appwrite's per-execution dynamic key; fall back to a standard key env."""
    try:
        k = (context.req.headers or {}).get('x-appwrite-key', '') or ''
        if k:
            return k
    except Exception:
        pass
    return os.environ.get('APPWRITE_API_KEY', '')


def main(context):
    # Defaults rather than os.environ[...]: this function has no configured
    # variables, and a missing key should not be a KeyError before any work
    # starts. Mirrors onboard_company.
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', DEFAULT_ENDPOINT)) \
          .set_project(os.environ.get('APPWRITE_PROJECT_ID', DEFAULT_PROJECT)) \
          .set_key(_api_key(context))
    db = Databases(client)

    this_year = datetime.now(timezone.utc).year
    index = build_index(db)
    context.log(f"resolved {len(index)} company name forms")

    stored = updated = created = 0
    unmatched, mismatches = [], []

    for year in (this_year, this_year + 1):
        try:
            page = fetch_calendar(year, context)
        except Exception as exc:
            log_error(db, "dividends", "error",
                      f"could not fetch the {year} dividend calendar",
                      f"{type(exc).__name__}: {exc}", context)
            continue
        if page is None:
            context.log(f"{year}: no calendar published yet")
            continue

        try:
            rows = parse_calendar(page, year)
        except ValueError as exc:
            # The page shape changed. Loud, because the alternative is quietly
            # storing nothing and looking like a market that pays no dividends.
            log_error(db, "dividends", "critical",
                      f"the {year} dividend calendar could not be parsed",
                      str(exc), context)
            continue

        for r in rows:
            r['c_name'] = resolve(r['key'], index, r.get('ticker'))
        matched = [r for r in rows if r['c_name']]
        unmatched += [r['issuer'] for r in rows if not r['c_name']]
        matched = dedupe(matched)

        # The document id lives on the model as `.id`, not inside `._data`, so
        # it has to be carried alongside the fields to update the row later.
        existing_page = db.list_documents(
            DB_ID, "dividends",
            queries=[Query.equal("year", year), Query.limit(500)])
        by_key = {}
        for d in existing_page.documents:
            row = d._data
            by_key[(row.get("c_name"), row.get("type"))] = (d.id, row)

        for r in matched:
            doc = {
                'c_name':       r['c_name'],
                'issuer':       r['issuer'],
                'year':         year,
                'amount':       r['amount'],
                'ex_date':      r['ex_date'],
                'pay_date':     r['pay_date'],
                'pay_date_end': r['pay_date_end'],
                'confirmed':    bool(r['confirmed']),
                'type':         r['type'],
                'frequency':    r['frequency'],
                'source':       SOURCE,
                'updated_at':   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
            }
            prev = by_key.get((r['c_name'], r['type']))
            try:
                if prev:
                    prev_id, prev_row = prev
                    # Only write when something actually changed, so `updated_at`
                    # stays meaningful instead of moving every single week.
                    if any(prev_row.get(k) != v for k, v in doc.items() if k != 'updated_at'):
                        db.update_document(DB_ID, "dividends", prev_id, doc)
                        updated += 1
                else:
                    db.create_document(DB_ID, "dividends", ID.unique(), doc)
                    created += 1
                stored += 1
            except Exception as exc:
                log_error(db, "dividends", "error",
                          f"could not store the dividend for {r['c_name']} ({year})",
                          f"{type(exc).__name__}: {exc}", context)

        # Cross-check the current year against the fundamentals feed. Two sources
        # agreeing is the strongest signal we have that neither has drifted.
        if year == this_year:
            for r in matched[:25]:
                if not r['amount']:
                    continue
                other = idb_dpa(r['issuer'], year - 1)
                if other and abs(other - r['amount']) / r['amount'] > CROSSCHECK_TOLERANCE:
                    mismatches.append(f"{r['c_name']}: calendar {r['amount']} vs fundamentals {other}")

    if unmatched:
        log_error(db, "dividends", "warning",
                  f"{len(unmatched)} issuers in the calendar match no company row",
                  ", ".join(sorted(set(unmatched))[:40]), context)

    if mismatches:
        log_error(db, "dividends", "warning",
                  f"{len(mismatches)} dividend amounts disagree between sources",
                  " | ".join(mismatches[:20]), context)

    if stored == 0:
        log_error(db, "dividends", "critical",
                  "the dividend run stored nothing",
                  "Either both calendar pages failed or every issuer was unmatched.",
                  context)

    summary = (f"{stored} dividends stored ({created} new, {updated} updated), "
               f"{len(unmatched)} unmatched, {len(mismatches)} cross-check mismatches")
    context.log(summary)
    return context.res.json({"ok": stored > 0, "summary": summary})

#!/usr/bin/env python3
"""Private, provider-configured acquisition. Never promotes source authority.

Native requests/field names live in a secret JSON configuration, not this file.
No raw response, endpoint or exception detail is printed to runner logs.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import gzip
import io
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests

KINDS = {"quotes", "depth", "fundamentals", "dividends"}
ZONE = ZoneInfo("Africa/Casablanca")
MAX_BODY = 4 * 1024 * 1024
MAX_BATCH = 8 * 1024 * 1024


class AcquisitionError(Exception):
    """Only this non-identifying code may leave the worker."""

    def __init__(self, code, http_status=None):
        super().__init__(code)
        self.http_status = http_status


def decode(raw):
    def invalid(_):
        raise AcquisitionError("INVALID_JSON")

    try:
        return json.loads(raw, parse_constant=invalid)
    except (ValueError, UnicodeError):
        raise AcquisitionError("INVALID_JSON") from None


def utc(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (AttributeError, ValueError):
        raise AcquisitionError("INVALID_TIMESTAMP") from None


def path_value(value, path):
    try:
        for key in path:
            value = value[key]
        return value
    except (KeyError, IndexError, TypeError):
        raise AcquisitionError("MISSING_FIELD") from None


class NoAmbientAuth(requests.auth.AuthBase):
    def __call__(self, request):
        return request  # Do not discover unrelated machine credentials in .netrc.


def fetch(recipe, deadline, max_body=MAX_BODY):
    """Use the existing collector's HTTP client, with bounded retries and bytes."""
    url = urlsplit(recipe["url"])
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.fragment
    ):
        raise AcquisitionError("INVALID_ENDPOINT")
    headers = dict(recipe.get("headers", {}))
    headers.setdefault("Accept-Encoding", "identity")
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            raise AcquisitionError("DEADLINE")
        try:
            with requests.request(
                recipe.get("method", "POST"),
                recipe["url"],
                json=recipe.get("body"),
                headers=headers,
                auth=NoAmbientAuth(),
                timeout=(min(8, remaining), min(10, remaining)),
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code != 200:
                    if (
                        response.status_code in {429, 500, 502, 503, 504}
                        and attempt == 0
                    ):
                        time.sleep(min(1, max(0, deadline - time.monotonic())))
                        continue
                    raise AcquisitionError(
                        "HTTP_FAILURE", http_status=response.status_code
                    )
                blocks, size = [], 0
                for block in response.iter_content(chunk_size=4096):
                    if time.monotonic() >= deadline:
                        raise AcquisitionError("DEADLINE")
                    size += len(block)
                    if size > max_body:
                        raise AcquisitionError("RESPONSE_TOO_LARGE")
                    blocks.append(block)
                if time.monotonic() > deadline:
                    raise AcquisitionError("DEADLINE")
                return b"".join(blocks), datetime.now(timezone.utc)
        except requests.RequestException:
            if attempt == 1:
                raise AcquisitionError("NETWORK_FAILURE") from None
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    raise AcquisitionError("NETWORK_FAILURE")


def normalized(document, recipe, captured, kind):
    records = path_value(document, recipe["rows_path"])
    if not isinstance(records, list) or not records or len(records) > 5000:
        raise AcquisitionError("INVALID_ROWS")
    rows = []
    identities = set()
    for original in records:
        row = {
            key: path_value(original, path) for key, path in recipe["fields"].items()
        }
        row.update(recipe.get("constants", {}))
        identity = row.get("source_identity")
        if not isinstance(identity, str) or not 1 <= len(identity) <= 200:
            raise AcquisitionError("INVALID_IDENTITY")
        if identity in identities:
            raise AcquisitionError("CONFLICTING_IDENTITIES")
        identities.add(identity)
        if kind == "quotes":
            price = row.get("price")
            if (
                isinstance(price, bool)
                or not isinstance(price, (int, float))
                or not math.isfinite(price)
                or not 0 < price <= 1e12
            ):
                raise AcquisitionError("INVALID_PRICE")
            if row.get("instrument_type") not in {"STOCK", "INDEX"}:
                raise AcquisitionError("INVALID_INSTRUMENT_TYPE")
            # Source session date is mandatory. Receipt time alone is not freshness.
            if row.get("session_date") != captured.astimezone(ZONE).date().isoformat():
                raise AcquisitionError("WRONG_SESSION_DATE")
            event = row.get("source_event_at")
            if event is not None:
                event = utc(event)
                age = captured - event
                if age < timedelta(0) or age > timedelta(
                    seconds=recipe.get("max_age_seconds", 3600)
                ):
                    raise AcquisitionError("STALE_OR_FUTURE_EVENT")
                row["source_event_at"] = event.isoformat()
            row["price_basis"] = "REPORTED_QUOTE"
            row["freshness"] = "SOURCE_EVENT_VERIFIED" if event else "SESSION_DATE_ONLY"
        row["captured_at"] = captured.isoformat()
        # Native source fields stay in raw evidence, not anonymous normalized output.
        rows.append(row)
    expected = recipe.get("expected_identities")
    if expected is not None and identities != set(expected):
        raise AcquisitionError("INCOMPLETE_IDENTITIES")
    return rows


def config_check(config):
    provider = config.get("provider_namespace", "")
    if not re.fullmatch(r"feed_[a-f0-9]{16}", provider):
        raise AcquisitionError("INVALID_NAMESPACE")
    jobs = config.get("jobs", {})
    if not jobs or set(jobs) - KINDS:
        raise AcquisitionError("INVALID_JOBS")
    for kind, recipes in jobs.items():
        if not isinstance(recipes, list) or not recipes or len(recipes) > 100:
            raise AcquisitionError("INVALID_RECIPES")
        for recipe in recipes:
            fields, constants = recipe.get("fields", {}), recipe.get("constants", {})
            if (
                not isinstance(fields, dict)
                or not isinstance(constants, dict)
                or set(fields) & set(constants)
                or set(constants) - {"source_identity", "instrument_type"}
            ):
                raise AcquisitionError("INVALID_FIELD_BINDINGS")
            if kind == "quotes" and not {"price", "session_date"}.issubset(fields):
                raise AcquisitionError("MISSING_SOURCE_PRICE_OR_DATE")
        if kind == "quotes":
            # Quotes require a complete configured universe, not just a nonempty list.
            if any(not recipe.get("expected_identities") for recipe in recipes):
                raise AcquisitionError("MISSING_UNIVERSE")


def scheduled_slot(now, kind):
    contract = os.environ.get('APP_SCHEDULE_CONTRACT')
    if contract:
        import recurring_schedule
        if contract != recurring_schedule.CONTRACT:
            raise AcquisitionError('UNKNOWN_SCHEDULE_CONTRACT')
        return recurring_schedule.slot(now, kind)
    local = now.astimezone(ZONE)
    if local.weekday() >= 5:
        return None
    if kind in {"quotes", "depth"}:
        if not 9 <= local.hour < 17 or (kind == "depth" and local.minute >= 15):
            return None
        minute = 0 if kind == "depth" else local.minute // 15 * 15
        return (
            local.replace(minute=minute, second=0, microsecond=0)
            .astimezone(timezone.utc)
            .isoformat()
        )
    if kind == "fundamentals" and not 17 <= local.hour < 19:
        return None
    if kind == "dividends" and (local.weekday() != 4 or not 18 <= local.hour < 20):
        return None
    return local.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def acquire(config, kind, slot, *, fetcher=fetch, seconds=80):
    config_check(config)
    recipes = config["jobs"].get(kind)
    if kind not in KINDS or not recipes:
        raise AcquisitionError("JOB_NOT_CONFIGURED")
    utc(slot)
    deadline = time.monotonic() + seconds
    captures, observations, errors = [], [], []
    for index, recipe in enumerate(recipes):
        remaining_bytes = MAX_BATCH - sum(
            len(item["raw_hex"]) // 2 for item in captures
        )
        if remaining_bytes <= 0:
            errors.append({"request_index": index, "code": "BATCH_LIMIT"})
            break
        try:
            raw, captured = fetcher(recipe, deadline, min(MAX_BODY, remaining_bytes))
            if captured.tzinfo is None:
                raise AcquisitionError("INVALID_TIMESTAMP")
            captures.append(
                {
                    "request_index": index,
                    "received_at": captured.isoformat(),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "raw_hex": raw.hex(),
                }
            )
            observations.extend(normalized(decode(raw), recipe, captured, kind))
        except AcquisitionError as error:
            errors.append({"request_index": index, "code": str(error)})
    identities = [row["source_identity"] for row in observations]
    if len(identities) != len(set(identities)):
        errors.append({"code": "CROSS_REQUEST_IDENTITY_CONFLICT"})
    if kind == "quotes" and not any(
        row.get("instrument_type") == "INDEX" for row in observations
    ):
        errors.append({"code": "MISSING_INDEX"})
    envelope = {
        "contract": "private-acquisition/v1",
        "provider_namespace": config["provider_namespace"],
        "kind": kind,
        "slot": slot,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "completeness": "INCOMPLETE" if errors else "COMPLETE",
        "errors": errors,
        "captures": captures,
        "observations": observations,
        "authority": "UNPROMOTED",
        "prediction_eligible": False,
    }
    return envelope


def packed(envelope, *, max_batch=MAX_BATCH):
    raw = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    compressed = gzip.compress(raw, mtime=0)
    if len(raw) > 24 * 1024 * 1024 or len(compressed) > max_batch:
        raise AcquisitionError("BATCH_TOO_LARGE")
    return hashlib.sha256(compressed).hexdigest(), compressed


def unpacked(digest, blob, *, max_batch=MAX_BATCH):
    """Verify a bounded saved transmission copy without changing its bytes."""
    if len(blob) > max_batch or hashlib.sha256(blob).hexdigest() != digest:
        raise AcquisitionError("ARCHIVE_HASH_MISMATCH")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
            raw = stream.read(24 * 1024 * 1024 + 1)
        if len(raw) > 24 * 1024 * 1024:
            raise AcquisitionError("BATCH_TOO_LARGE")
        value = decode(raw)
        if not isinstance(value, dict):
            raise AcquisitionError("INVALID_ARCHIVE")
        return value
    except (OSError, EOFError):
        raise AcquisitionError("INVALID_ARCHIVE") from None


class SQLiteStore:
    """Isolated local tests. No genuine app or prediction tables are touched."""

    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS attempts (digest TEXT PRIMARY KEY, provider TEXT, kind TEXT, slot TEXT, complete INTEGER, raw BLOB)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS slots (provider TEXT, kind TEXT, slot TEXT, digest TEXT, PRIMARY KEY(provider,kind,slot))"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS subject_slots (provider TEXT, kind TEXT, slot TEXT, subject TEXT, digest TEXT, PRIMARY KEY(provider,kind,slot,subject))"
        )

    def subject_complete(self, provider, kind, slot, subject):
        return self.db.execute('SELECT 1 FROM subject_slots WHERE provider=? AND kind=? AND slot=? AND subject=?',
                               (provider, kind, slot, subject)).fetchone() is not None

    def admit_subject(self, provider, subject, *, projection=False):
        return True  # Isolated test storage has no remote lease or source authority.

    def admit(self, provider, kind, slot, *, shadow=False, projection=False):
        return True  # Only the explicit isolated store has this local exemption.

    def complete(self, provider, kind, slot):
        return (
            self.db.execute(
                "SELECT 1 FROM slots WHERE provider=? AND kind=? AND slot=?",
                (provider, kind, slot),
            ).fetchone()
            is not None
        )

    def save(self, envelope):
        digest, blob = packed(envelope)
        return self.save_blob(digest, blob)

    def save_blob(self, digest, blob):
        envelope = unpacked(digest, blob)
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO attempts VALUES (?,?,?,?,?,?)",
                (
                    digest,
                    envelope["provider_namespace"],
                    envelope["kind"],
                    envelope["slot"],
                    envelope["completeness"] == "COMPLETE",
                    blob,
                ),
            )
            scoped = envelope.get('contract') == 'private-acquisition/v3'
            if scoped and (envelope.get('kind') != 'fundamentals' or
                           not isinstance(envelope.get('symbol'), str) or
                           not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,31}', envelope['symbol']) or
                           envelope.get('subject_key') != 'symbol:' + str(envelope.get('symbol'))):
                raise AcquisitionError('INVALID_ARCHIVE_SUBJECT')
            if envelope["completeness"] == "COMPLETE" and scoped:
                self.db.execute('INSERT OR IGNORE INTO subject_slots VALUES (?,?,?,?,?)',
                    (envelope['provider_namespace'], envelope['kind'], envelope['slot'], envelope['subject_key'], digest))
            elif envelope["completeness"] == "COMPLETE":
                self.db.execute(
                    "INSERT OR IGNORE INTO slots VALUES (?,?,?,?)",
                    (
                        envelope["provider_namespace"],
                        envelope["kind"],
                        envelope["slot"],
                        digest,
                    ),
                )
        return digest


class PostgresStore:
    def __init__(self, uri, project_reference):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict

        options = conninfo_to_dict(uri)
        # Worker credentials can only be the restricted role, never postgres/admin.
        if (
            not isinstance(project_reference, str)
            or not re.fullmatch(r"[a-z0-9]{10,40}", project_reference)
            or options.get("user") != "app_collector." + project_reference
            or not re.fullmatch(
                r"[a-z0-9-]+\.pooler\.supabase\.com", options.get("host", "")
            )
            or options.get("dbname") != "postgres"
            or options.get("port", "5432") not in {"5432", "6543"}
            or options.get("sslmode") != "verify-full"
            or not options.get("password")
            or set(options)
            - {"host", "port", "dbname", "user", "password", "sslmode", "sslrootcert"}
            or options.get("sslrootcert", "system") != "system"
        ):
            raise AcquisitionError("INVALID_WORKER_CREDENTIAL")
        options["sslrootcert"] = "system"
        options.update(connect_timeout=10, application_name="private-app-collector")
        self.db = psycopg.connect(**options)

    def complete(self, provider, kind, slot):
        with self.db.transaction():
            return self.db.execute(
                "SELECT app_ingest.slot_complete(%s,%s,%s)", (provider, kind, slot)
            ).fetchone()[0]

    def save(self, envelope):
        digest, blob = packed(envelope)
        with self.db.transaction():
            self.db.execute(
                "SELECT app_ingest.save_attempt(%s,%s,%s,%s,%s,%s,%s)",
                (
                    digest,
                    envelope["provider_namespace"],
                    envelope["kind"],
                    envelope["slot"],
                    envelope["completed_at"],
                    envelope["completeness"],
                    blob,
                ),
            )
        return digest


def open_store(isolated_path, config):
    if isolated_path is not None:
        return SQLiteStore(isolated_path)
    gateway = os.environ.get("APP_ARCHIVE_GATEWAY_URL")
    token = os.environ.get("APP_ARCHIVE_WRITE_TOKEN")
    if gateway is not None or token is not None:
        if not gateway or not token or os.environ.get("APP_WORKER_DATABASE_URL"):
            raise AcquisitionError("AMBIGUOUS_ARCHIVE_CONFIGURATION")
        from archive_store import ArchiveGatewayStore

        return ArchiveGatewayStore(
            gateway, token, config.get("archive_project_reference")
        )
    # Retained for explicitly configured legacy local/manual callers only.
    if not os.environ.get("APP_WORKER_DATABASE_URL"):
        raise AcquisitionError("ARCHIVE_NOT_CONFIGURED")
    return PostgresStore(
        os.environ["APP_WORKER_DATABASE_URL"], config.get("database_project_reference")
    )


def resume_store(store):
    flush = getattr(store, "flush_pending", None)
    return flush() if callable(flush) else 0


def require_acquisition_admission(store, provider, kind, slot, *, shadow=False, projection=False):
    """A missing/expired lease is distinct from an incomplete archive slot."""
    require_checkpoint_acquisition_headroom(kind)
    admit = getattr(store, 'admit', None)
    if not callable(admit) or admit(provider, kind, slot, shadow=shadow, projection=projection) is not True:
        raise AcquisitionError('ACQUISITION_NOT_ADMITTED')


def require_checkpoint_acquisition_headroom(kind):
    root=os.environ.get('APP_CHECKPOINT_ROOT')
    if root is None:return
    import runner_checkpoint as checkpoint
    additions={'archive':1};reserve=MAX_BATCH
    if kind in ['quotes','fundamentals','dividends']:
        channel={'quotes':'quotes','fundamentals':'enrichment','dividends':'dividends'}[kind]
        additions[channel]=1;reserve+=24*1024*1024
        if kind!='fundamentals':additions[channel+'.accepted']=1;reserve+=4096
    checkpoint.require_headroom(root,reserve_bytes=reserve,additions=additions)


def require_checkpoint_delivery_headroom(kind, store, digest, blob):
    root=os.environ.get('APP_CHECKPOINT_ROOT')
    if root is None:return
    import runner_checkpoint as checkpoint
    additions={};reserve=0
    raw=getattr(store,'outbox',None)
    if raw is not None and not any(p.name==digest+'.json.gz' for p in raw.entries()):
        additions['archive']=1;reserve=len(blob)
    if kind in ['quotes','dividends']:
        additions[kind+'.accepted']=1;reserve+=4096
    checkpoint.require_headroom(root,reserve_bytes=reserve,additions=additions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=sorted(KINDS))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--isolated-store", type=Path)
    args = parser.parse_args()
    try:
        config = decode(
            args.config.read_bytes() if args.config else os.environ["APP_SOURCE_CONFIG"]
        )
        config_check(config)
        slot = scheduled_slot(datetime.now(timezone.utc), args.kind)
        if slot is None:
            print(json.dumps({"status": "OUTSIDE_WINDOW"}))
            return 0
        if not args.isolated_store:
            raise AcquisitionError('LEGACY_REQUIRES_ISOLATED_STORE')
        store = SQLiteStore(args.isolated_store)
        if store.complete(config["provider_namespace"], args.kind, slot):
            print(json.dumps({"status": "ALREADY_COMPLETE"}))
            return 0
        envelope = acquire(config, args.kind, slot)
        store.save(envelope)
        print(
            json.dumps(
                {
                    "status": envelope["completeness"],
                    "requests": len(envelope["captures"]),
                    "rows": len(envelope["observations"]),
                    "prediction_eligible": False,
                }
            )
        )
        return 0 if envelope["completeness"] == "COMPLETE" else 1
    except Exception as error:
        code = str(error) if isinstance(error, AcquisitionError) else "WORKER_FAILURE"
        print(json.dumps({"status": "FAILED", "code": code}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

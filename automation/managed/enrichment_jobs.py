#!/usr/bin/env python3
"""Opt-in original enrichment rotation with durable archive + projection retry.

Only known, privately mapped companies are dispatched. Raw archives and prepared
documents stay in a private Outbox until both acknowledgements match. This does
not enable schedules, create company identities or promote prediction authority.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat

import fundamental_collect
import fundamental_feed
from outbox import Outbox
import price_jobs
from projection_store import ProjectionPublisher
import worker

CONTRACT = "private-enrichment-job/v1"
MAX_JOB = 24 * 1024 * 1024


class IsolatedPublisher:
    """Local test output; never loads a remote URL, token or project key."""
    def __init__(self, store):
        if not isinstance(store, worker.SQLiteStore):
            raise worker.AcquisitionError("ISOLATED_STORE_REQUIRED")
        self.store = store
        store.db.execute('CREATE TABLE IF NOT EXISTS enrichment_projections (digest TEXT PRIMARY KEY, document TEXT)')

    def publish(self, document):
        digest = hashlib.sha256(document.encode()).hexdigest()
        with self.store.db:
            self.store.db.execute('INSERT OR IGNORE INTO enrichment_projections VALUES (?,?)', (digest, document))
        return {"status": "PUBLISHED", "sha256": digest}


@contextmanager
def run_lock(outbox):
    outbox._check_directory()
    path = outbox.directory.with_name(outbox.directory.name + ".runner.lock")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise worker.AcquisitionError("ENRICHMENT_LOCK_NOT_PRIVATE")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise worker.AcquisitionError("ENRICHMENT_ALREADY_RUNNING") from None
        yield
    finally:
        os.close(descriptor)


def prepare(value, config, index, now):
    digest, blob = worker.packed(value)
    document, error = None, None
    try:
        candidate = fundamental_feed.build(blob, digest, config, index, as_of=now)
        document = fundamental_feed.canonical(candidate)
    except Exception:
        # Raw evidence survives a derivation failure; it requires explicit review.
        error = "FUNDAMENTAL_PREPARATION_FAILED"
    return {"contract": CONTRACT, "archive_sha256": digest,
            "archive_hex": blob.hex(), "document": document,
            "preparation_error": error,
            "index_sha256": fundamental_feed.fingerprint(index)}


def checked(job, config, index):
    if (not isinstance(job, dict) or job.get("contract") != CONTRACT
            or job.get("index_sha256") != fundamental_feed.fingerprint(index)):
        raise worker.AcquisitionError("ENRICHMENT_CONTEXT_CHANGED")
    try:
        blob = bytes.fromhex(job["archive_hex"])
        value, _ = fundamental_feed.verified_archive(blob, job["archive_sha256"], config)
        if value.get("contract") != "private-acquisition/v3":
            raise ValueError()
        document = job["document"]
        if document is not None:
            parsed = json.loads(document)
            # Re-derive at the original *actual preparation time*, never at retry.
            expected = fundamental_feed.build(blob, job["archive_sha256"], config, index,
                as_of=worker.utc(parsed["built_at"]))
            if fundamental_feed.canonical(expected) != document:
                raise ValueError()
        elif job.get("preparation_error") != "FUNDAMENTAL_PREPARATION_FAILED":
            raise ValueError()
    except Exception:
        raise worker.AcquisitionError("INVALID_ENRICHMENT_JOB") from None
    return value, blob


def deliver(job, config, index, store, publisher):
    value, blob = checked(job, config, index)
    digest = job["archive_sha256"]
    worker.require_checkpoint_delivery_headroom('fundamentals',store,digest,blob)
    if store.save_blob(digest, blob) != digest:
        raise worker.AcquisitionError("INVALID_ARCHIVE_RECEIPT")
    if job["document"] is None:
        raise worker.AcquisitionError("FUNDAMENTAL_PREPARATION_FAILED")
    if value["completeness"] != "COMPLETE" or json.loads(job["document"])["completeness"] != "COMPLETE":
        return "incomplete"  # Raw incomplete attempt is archived; no company merge.
    result = publisher.publish(job["document"])
    if (not isinstance(result, dict) or result.get("status") != "PUBLISHED"
            or result.get("sha256") != hashlib.sha256(job["document"].encode()).hexdigest()):
        raise worker.AcquisitionError("INVALID_PROJECTION_RECEIPT")
    return "complete"


def run(config, index, companies, store, publisher, outbox, *, max_jobs=5,
        clock=lambda: datetime.now(timezone.utc), fetcher=worker.fetch, target_symbol=None):
    fundamental_collect.config_check(config)
    symbols = fundamental_feed.validate_index(index, config["provider_namespace"])
    if (type(max_jobs) is not int or not 1 <= max_jobs <= 5
            or not callable(getattr(store, "subject_complete", None))
            or not callable(getattr(store, "admit_subject", None))
            or not callable(getattr(store, "save_blob", None))):
        raise worker.AcquisitionError("INVALID_ENRICHMENT_EXECUTOR")
    if isinstance(store, worker.SQLiteStore) and isinstance(publisher, ProjectionPublisher):
        raise worker.AcquisitionError("ISOLATED_PUBLISHER_REQUIRED")
    # Larger only for this private wrapper, never for source archives/gateways.
    outbox = Outbox(outbox.directory, outbox.limit, entry_limit=MAX_JOB)
    archive_spool = getattr(store, "outbox", None)
    if archive_spool is not None:
        source_path, job_path = archive_spool.directory.resolve(), outbox.directory.resolve()
        if source_path.is_relative_to(job_path) or job_path.is_relative_to(source_path):
            raise worker.AcquisitionError("ENRICHMENT_SPOOLS_MUST_BE_SEPARATE")
    now = clock()
    if target_symbol is not None:
        name = symbols.get(target_symbol)
        if name not in companies or sum(value == name for value in symbols.values()) != 1 or max_jobs != 1:
            raise worker.AcquisitionError('INVALID_REQUESTED_ENRICHMENT_TARGET')
        plan = [{'name': name, 'symbol': target_symbol, 'reason': 'EXPLICIT_TARGET'}]
    else:
        plan = price_jobs.enrichment_jobs(companies, symbols, now)
    summary = {"status": "COMPLETE", "planned": len(plan), "attempted": 0,
               "resumed": 0, "skipped": 0, "complete": 0, "incomplete": 0,
               "failed": 0, "deferred": 0, "pending": 0,
               "prediction_eligible": False}
    with run_lock(outbox):
        blocked = set()
        for path in outbox.entries():
            if summary["attempted"] >= max_jobs:
                break
            summary["attempted"] += 1
            summary["resumed"] += 1
            try:
                job = worker.unpacked(path.name[:64], outbox.read(path), max_batch=MAX_JOB)
                value, _ = checked(job, config, index)
                if target_symbol is not None and value['symbol'] != target_symbol:
                    raise worker.AcquisitionError('PENDING_ENRICHMENT_TARGET_CHANGED')
                blocked.add(value["symbol"])
                outcome = deliver(job, config, index, store, publisher)
                outbox.acknowledge(path.name[:64])
                summary[outcome] += 1
            except Exception:
                summary["failed"] += 1
        # Never refetch while an unprocessed/failed publication remains pending.
        pending = outbox.entries()
        if pending:
            summary["deferred"] = sum(job["symbol"] not in blocked for job in plan)
        else:
            for item in plan:
                if item["symbol"] in blocked:
                    continue
                if summary["attempted"] >= max_jobs:
                    summary["deferred"] += 1
                    continue
                summary["attempted"] += 1
                try:
                    if sum(path.stat().st_size for path in outbox.entries()) + MAX_JOB > outbox.limit:
                        raise worker.AcquisitionError("OUTBOX_CAPACITY")
                    slot = clock().replace(minute=0, second=0, microsecond=0).isoformat()
                    if store.subject_complete(config["provider_namespace"], "fundamentals", slot,
                                              "symbol:" + item["symbol"]):
                        summary["skipped"] += 1
                        if os.environ.get('APP_SCHEDULE_CONTRACT') == 'recurring-casablanca/v1':
                            summary["attempted"] -= 1
                        continue
                    worker.require_checkpoint_acquisition_headroom('fundamentals')
                    if not store.admit_subject(config["provider_namespace"], "symbol:" + item["symbol"], projection=True):
                        raise worker.AcquisitionError("SUBJECT_ACQUISITION_NOT_ADMITTED")
                    value = fundamental_collect.acquire(config, item["symbol"], fetcher=fetcher,
                                                        subject_scoped=True)
                    job = prepare(value, config, index, clock())
                    queued_digest, queued_blob = worker.packed(job, max_batch=MAX_JOB)
                    outbox.put(queued_digest, queued_blob)
                    outcome = deliver(job, config, index, store, publisher)
                    outbox.acknowledge(queued_digest)
                    summary[outcome] += 1
                except Exception:
                    summary["failed"] += 1
            # A failure does not erase the original independently capped plan.
        summary["pending"] = len(outbox.entries())
    if summary["failed"] or summary["incomplete"] or summary["deferred"] or summary["pending"]:
        summary["status"] = "PARTIAL"
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--spool", type=Path, required=True)
    parser.add_argument("--isolated-store", type=Path)
    parser.add_argument("--max-jobs", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        result = execute(args.config, args.index, args.spool, context_path=args.context,
                         isolated_store=args.isolated_store, max_jobs=args.max_jobs)
        print(json.dumps(result))
        return 0 if result["status"] == "COMPLETE" else 2
    except Exception:
        print(json.dumps({"status": "FAILED", "code": "ENRICHMENT_EXECUTION_FAILED"}))
        return 1


def execute(config_path, index_path, spool, *, context_path=None, isolated_store=None, max_jobs=5, only_symbol=None):
    store = None
    try:
        config = worker.decode(Path(config_path).read_bytes())
        index = worker.decode(Path(index_path).read_bytes())
        store = worker.open_store(isolated_store, config)
        publisher = IsolatedPublisher(store) if isolated_store else ProjectionPublisher(os.environ.get("APP_PROJECTION_URL", ""),
            os.environ.get("APP_PROJECTION_TOKEN", ""),
            os.environ.get("APP_PROJECTION_PROJECT_REFERENCE", ""))
        if context_path:
            context = worker.decode(Path(context_path).read_bytes())
        elif isolated_store:
            raise worker.AcquisitionError('ISOLATED_CONTEXT_REQUIRED')
        else:
            context = publisher.read_context(config['provider_namespace'], fundamental_feed.fingerprint(index))
        now = datetime.now(timezone.utc)
        if (context.get("contract") not in {"private-enrichment-context/v1","private-enrichment-context/v2"}
                or not isinstance(context.get("companies"), dict)
                or not now - timedelta(days=1) <= worker.utc(context["observed_at"]) <= now):
            raise worker.AcquisitionError("INVALID_OR_STALE_ENRICHMENT_CONTEXT")
        if (context.get('provider_namespace', config['provider_namespace']) != config['provider_namespace']
                or context.get('index_sha256', fundamental_feed.fingerprint(index)) != fundamental_feed.fingerprint(index)):
            raise worker.AcquisitionError('ENRICHMENT_CONTEXT_CHANGED')
        if only_symbol is not None:
            symbols = fundamental_feed.validate_index(index, config['provider_namespace'])
            if only_symbol not in symbols or symbols[only_symbol] not in context['companies']:
                raise worker.AcquisitionError('UNMAPPED_ENRICHMENT_SYMBOL')
            context = {**context, 'companies': {symbols[only_symbol]: context['companies'][symbols[only_symbol]]}}
        return run(config, index, context["companies"], store,
                   publisher, Outbox(spool), max_jobs=max_jobs, target_symbol=only_symbol)
    finally:
        if isinstance(store, worker.SQLiteStore):
            store.db.close()


if __name__ == "__main__":
    raise SystemExit(main())

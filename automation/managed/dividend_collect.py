#!/usr/bin/env python3
"""Opt-in dividend-calendar acquisition. Archives raw pages; derives nothing.

Native URLs, headers and charsets live in a private JSON configuration.
No page content, issuer name or endpoint is printed to runner logs.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit


import worker

MAX_PAGE = 4 * 1024 * 1024
CONTRACT = "private-dividend-config/v1"
KEYS = {"year", "url", "method", "body", "headers", "optional", "charset"}


class DividendPublications:
    """Persist exact preparation and acknowledgements independently of raw archival."""
    def __init__(self, config, index, directory):
        import dividend_feed
        from outbox import Outbox, separate_spools
        config_check(config)
        dividend_feed.validate_index(index, config['provider_namespace'])
        self.config, self.index = config, index
        self.index_pin = dividend_feed.fingerprint(index)
        self.config_pin = dividend_feed.fingerprint(config)
        self.pending = Outbox(directory, entry_limit=24*1024*1024)
        self.accepted = Outbox(Path(directory).with_name(Path(directory).name+'.accepted'))
        separate_spools(self.pending.directory, self.accepted.directory)

    def enqueue(self, value, now):
        import dividend_feed
        digest, blob = worker.packed(value)
        document, error = None, None
        try:
            document = dividend_feed.canonical(dividend_feed.build(blob,digest,self.config,self.index,as_of=now))
        except Exception:
            error = 'DIVIDEND_PREPARATION_FAILED'
        job = {'contract':'private-dividend-job/v1','archive_sha256':digest,'archive_hex':blob.hex(),
               'document':document,'preparation_error':error,'index_sha256':self.index_pin,'config_sha256':self.config_pin}
        key, body = worker.packed(job,max_batch=self.pending.entry_limit)
        self.pending.put(key,body)
        return digest

    def checked(self, body, key):
        import dividend_feed
        job = worker.unpacked(key,body,max_batch=self.pending.entry_limit)
        if (job.get('contract')!='private-dividend-job/v1' or job.get('index_sha256')!=self.index_pin
                or job.get('config_sha256')!=self.config_pin):
            raise worker.AcquisitionError('DIVIDEND_CONTEXT_CHANGED')
        try:
            blob=bytes.fromhex(job['archive_hex'])
            value,_,_=dividend_feed.verified_archive(blob,job['archive_sha256'],self.config)
            if job['document'] is not None:
                parsed=worker.decode(job['document'])
                rebuilt=dividend_feed.build(blob,job['archive_sha256'],self.config,self.index,
                                            as_of=worker.utc(parsed['built_at']))
                if dividend_feed.canonical(rebuilt)!=job['document']:raise ValueError()
            elif job['preparation_error']!='DIVIDEND_PREPARATION_FAILED':raise ValueError()
        except Exception:
            raise worker.AcquisitionError('INVALID_DIVIDEND_JOB') from None
        return job,value,blob

    def receipts(self):
        result={}
        for path in self.accepted.entries():
            receipt=worker.unpacked(path.name[:64],self.accepted.read(path))
            if (set(receipt)!={'contract','provider_namespace','slot','archive_sha256','document_sha256','index_sha256','config_sha256'}
                    or any(not isinstance(receipt.get(field),str) or not re.fullmatch('[a-f0-9]{64}',receipt[field])
                           for field in ['archive_sha256','document_sha256','index_sha256','config_sha256'])
                    or receipt.get('contract')!='private-dividend-publish-receipt/v1'
                    or receipt.get('provider_namespace')!=self.config['provider_namespace']
                    or receipt.get('index_sha256')!=self.index_pin or receipt.get('config_sha256')!=self.config_pin):
                raise worker.AcquisitionError('INVALID_DIVIDEND_COMPLETION_RECEIPT')
            worker.utc(receipt['slot'])
            if receipt['slot'] in result and result[receipt['slot']]!=receipt:
                raise worker.AcquisitionError('DIVIDEND_COMPLETION_CONFLICT')
            result[receipt['slot']]=receipt
        return result

    def flush(self, store, publisher):
        receipts=self.receipts();completed=0;incomplete=0
        for path in self.pending.entries():
            job,value,blob=self.checked(self.pending.read(path),path.name[:64])
            parsed=worker.decode(job['document']) if job['document'] is not None else None
            receipt={'contract':'private-dividend-publish-receipt/v1','provider_namespace':self.config['provider_namespace'],
                'slot':value['slot'],'archive_sha256':job['archive_sha256'],
                'document_sha256':hashlib.sha256(job['document'].encode()).hexdigest() if parsed is not None else None,
                'index_sha256':self.index_pin,'config_sha256':self.config_pin}
            old=receipts.get(value['slot'])
            if old is not None:
                if old!=receipt:raise worker.AcquisitionError('DIVIDEND_COMPLETION_CONFLICT')
            else:
                if len(receipts)>=64:raise worker.AcquisitionError('DIVIDEND_RECEIPT_CAPACITY')
                worker.require_checkpoint_delivery_headroom('dividends',store,job['archive_sha256'],blob)
                if store.save_blob(job['archive_sha256'],blob)!=job['archive_sha256']:
                    raise worker.AcquisitionError('INVALID_ARCHIVE_RECEIPT')
                if parsed is None:raise worker.AcquisitionError('DIVIDEND_PREPARATION_FAILED')
                if value['completeness']!='COMPLETE' or parsed['completeness']!='COMPLETE':
                    self.pending.acknowledge(path.name[:64]);incomplete+=1;continue
                reply=publisher.publish(job['document'])
                if (reply.get('status')!='PUBLISHED' or reply.get('sha256')!=receipt['document_sha256']
                        or reply.get('kind')!='dividends' or type(reply.get('records')) is not int
                        or reply['records']!=len(parsed['rows'])):
                    raise worker.AcquisitionError('INVALID_PROJECTION_RECEIPT')
                receipt_key,receipt_body=worker.packed(receipt)
                self.accepted.put(receipt_key,receipt_body)
                receipts[value['slot']]=receipt
            # Durable exact receipt precedes acknowledgement, including interrupted retries.
            self.pending.acknowledge(path.name[:64]);completed+=1
        return {'published':completed,'incomplete':incomplete}


def publish_run(config,index,store,publisher,directory,*,clock=lambda:datetime.now(timezone.utc),fetcher=worker.fetch):
    from enrichment_jobs import run_lock
    from outbox import separate_spools
    from projection_store import ProjectionPublisher
    if isinstance(store,worker.SQLiteStore) and isinstance(publisher,ProjectionPublisher):
        raise worker.AcquisitionError('ISOLATED_PUBLISHER_REQUIRED')
    publications=DividendPublications(config,index,directory)
    raw_queue=getattr(store,'outbox',None)
    if raw_queue is not None:separate_spools(raw_queue.directory,publications.pending.directory,publications.accepted.directory)
    with run_lock(publications.pending):
        worker.resume_store(store)
        retried=publications.flush(store,publisher)
        now=clock()
        if worker.scheduled_slot(now,'dividends') is None:return {'status':'OUTSIDE_WINDOW',**retried}
        slot=now.replace(minute=0,second=0,microsecond=0).isoformat()
        if slot in publications.receipts():return {'status':'ALREADY_COMPLETE',**retried}
        if store.complete(config['provider_namespace'],'dividends',slot):
            raise worker.AcquisitionError('ARCHIVE_COMPLETE_WITHOUT_PUBLICATION_RECEIPT')
        worker.require_acquisition_admission(store,config['provider_namespace'],'dividends',slot,projection=True)
        value=acquire(config,fetcher=fetcher,scheduled_slot=slot,clock=clock)
        digest=publications.enqueue(value,clock())
        result=publications.flush(store,publisher)
        return {'status':'COMPLETE' if result['incomplete']==0 else 'INCOMPLETE','archive_digest':digest,**result}


def config_check(config):
    if (
        not isinstance(config, dict)
        or config.get("contract") != CONTRACT
        or not isinstance(config.get("provider_namespace"), str)
        or not re.fullmatch(r"feed_[a-f0-9]{16}", config["provider_namespace"])
        or not isinstance(config.get("jobs"), dict)
        or set(config["jobs"]) != {"dividends"}
    ):
        raise worker.AcquisitionError("INVALID_DIVIDEND_CONFIG")
    recipes = config["jobs"]["dividends"]
    if not isinstance(recipes, list) or not 1 <= len(recipes) <= 4:
        raise worker.AcquisitionError("INVALID_DIVIDEND_RECIPES")
    years = set()
    for recipe in recipes:
        if (
            not isinstance(recipe, dict)
            or set(recipe) - KEYS
            or not {"year", "url"}.issubset(recipe)
            or not isinstance(recipe["year"], int)
            or isinstance(recipe["year"], bool)
            or not 1900 <= recipe["year"] <= 2100
            or recipe["year"] in years
            or not isinstance(recipe.get("optional", False), bool)
            or (
                recipe.get("charset") is not None
                and (
                    not isinstance(recipe["charset"], str)
                    or not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", recipe["charset"])
                )
            )
            or not isinstance(recipe["url"], str)
            or urlsplit(recipe["url"]).scheme != "https"
        ):
            raise worker.AcquisitionError("INVALID_DIVIDEND_RECIPES")
        years.add(recipe["year"])


def envelope(config, fetched, completed_at, *, scheduled_slot=None):
    captures, targets, errors = [], [], []
    for position, (recipe, raw, received) in enumerate(fetched):
        digest = hashlib.sha256(raw).hexdigest()
        identity = hashlib.sha256(
            json.dumps(
                [config["provider_namespace"], digest, received.isoformat()],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        captures.append(
            {
                "request_index": position,
                "capture_id": identity,
                "received_at": received.isoformat(),
                "sha256": digest,
                "raw_hex": raw.hex(),
            }
        )
        targets.append(
            {
                "request_index": position,
                "year": recipe["year"],
                "charset": recipe.get("charset"),
            }
        )
    required = {recipe["year"] for recipe in config["jobs"]["dividends"]
                if not recipe.get("optional", False)}
    present = {recipe["year"] for recipe, _, _ in fetched}
    for year in sorted(required - present):
        errors.append({"year": year, "code": "CALENDAR_UNAVAILABLE"})
    slot = min(received for _, _, received in fetched).replace(
        minute=0, second=0, microsecond=0
    )
    if scheduled_slot is not None:
        slot = worker.utc(scheduled_slot)
    return {
        "contract": "private-acquisition/v2",
        "provider_namespace": config["provider_namespace"],
        "kind": "dividends",
        "slot": slot.isoformat(),
        "completed_at": completed_at.isoformat(),
        "execution": "CURRENT_ACQUISITION",
        "completeness": "COMPLETE" if not errors else "INCOMPLETE",
        "errors": errors,
        "captures": captures,
        "targets": targets,
        "authority": "UNPROMOTED",
        "prediction_eligible": False,
    }


def acquire(config, *, fetcher=worker.fetch, seconds=80, now=None, scheduled_slot=None,clock=lambda:datetime.now(timezone.utc)):
    config_check(config)
    deadline = time.monotonic() + seconds
    fetched = []
    for recipe in config["jobs"]["dividends"]:
        try:
            raw, received = fetcher(recipe, deadline, MAX_PAGE)
        except worker.AcquisitionError as error:
            # An optional future calendar may be absent or redirect to a landing page.
            # Never follow the redirect or treat its body as calendar evidence.
            if recipe.get("optional", False) and error.http_status in (302, 404):
                continue
            raise
        fetched.append((recipe, raw, received))
    if not fetched:
        raise worker.AcquisitionError("NO_CALENDAR_PAGES")
    completed = now or clock()
    if completed < max(received for _, _, received in fetched):
        raise worker.AcquisitionError("INVALID_COMPLETION_TIME")
    return envelope(config, fetched, completed, scheduled_slot=scheduled_slot)


def main(argv=None, *, clock=lambda: datetime.now(timezone.utc)):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--isolated-store", type=Path)
    parser.add_argument('--publish-index',type=Path)
    parser.add_argument('--publication-spool',type=Path)
    args = parser.parse_args(argv)
    try:
        config = worker.decode(
            args.config.read_bytes() if args.config else os.environ["APP_SOURCE_CONFIG"]
        )
        config_check(config)
        if (args.publish_index is None)!=(args.publication_spool is None):
            raise worker.AcquisitionError('DIVIDEND_PUBLICATION_CONFIGURATION_REQUIRED')
        if args.publish_index is not None:
            if args.isolated_store is not None:raise worker.AcquisitionError('MANAGED_PUBLICATION_REQUIRED')
            from projection_store import ProjectionPublisher
            store=worker.open_store(None,config)
            publisher=ProjectionPublisher(os.environ['APP_PROJECTION_URL'],os.environ['APP_PROJECTION_TOKEN'],
                                          os.environ['APP_PROJECTION_PROJECT_REFERENCE'])
            result=publish_run(config,worker.decode(args.publish_index.read_bytes()),store,publisher,
                               args.publication_spool,clock=clock)
            print(json.dumps(result))
            return 0 if result['status'] in ['COMPLETE','ALREADY_COMPLETE','OUTSIDE_WINDOW'] else 2
        now = clock()
        if worker.scheduled_slot(now, 'dividends') is None:
            print(json.dumps({'status':'OUTSIDE_WINDOW'}))
            return 0
        slot = now.replace(minute=0, second=0, microsecond=0).isoformat()
        store = worker.open_store(args.isolated_store, config)
        worker.resume_store(store)
        if store.complete(config["provider_namespace"], "dividends", slot):
            print(json.dumps({"status": "ALREADY_COMPLETE"}))
            return 0
        worker.require_acquisition_admission(store, config['provider_namespace'], 'dividends', slot)
        value = acquire(config, scheduled_slot=slot)
        digest = store.save(value)
        print(
            json.dumps(
                {
                    "status": value["completeness"],
                    "pages": len(value["captures"]),
                    "years": [target["year"] for target in value["targets"]],
                    "archive_digest": digest,
                    "prediction_eligible": False,
                }
            )
        )
        return 0 if value["completeness"] == "COMPLETE" else 2
    except Exception as error:
        code = (
            str(error)
            if isinstance(error, worker.AcquisitionError)
            else "WORKER_FAILURE"
        )
        print(json.dumps({"status": "FAILED", "code": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

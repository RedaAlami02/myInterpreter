"""Lossless acknowledged-receipt compaction; never removes a pending job.

Exact original compressed receipt bytes survive in the versioned checkpoint.
The serialized worker owns the state lock/concurrency while calling compact.
"""
import hashlib
from pathlib import Path

import runner_checkpoint
import worker

CONTRACT = 'private-receipt-history/v1'
MAX_HISTORY = 8 * 1024 * 1024


def compact(state, *, threshold=32, keep=8):
    state = runner_checkpoint.private_directory(state)
    if not 1 <= keep < threshold <= 48:
        raise worker.AcquisitionError('INVALID_RECEIPT_RETENTION')
    history = runner_checkpoint.queue(state, 'receipts.history')
    previous = history.entries() if history.directory.exists() else []
    records = {}
    for path in previous:
        value = worker.unpacked(path.name[:64], history.read(path))
        if value.get('contract') != CONTRACT or not isinstance(value.get('receipts'), dict):
            raise worker.AcquisitionError('INVALID_RECEIPT_HISTORY')
        for key, record in value['receipts'].items():
            if key in records and records[key] != record:
                raise worker.AcquisitionError('CONFLICTING_RECEIPT_HISTORY')
            raw = bytes.fromhex(record['raw_hex'])
            if hashlib.sha256(raw).hexdigest() != key:
                raise worker.AcquisitionError('INVALID_RECEIPT_HISTORY')
            worker.unpacked(key, raw)
            records[key] = record
    selected = []
    for channel in ['quotes.accepted', 'dividends.accepted', 'official_close.accepted']:
        spool = runner_checkpoint.queue(state, channel)
        paths = spool.entries()
        if len(paths) < threshold:
            continue
        ordered = []
        for path in paths:
            raw = spool.read(path)
            receipt = worker.unpacked(path.name[:64], raw)
            stamp = receipt.get('accepted_at', receipt.get('slot'))
            worker.utc(stamp)
            ordered.append((stamp, path, raw, receipt))
        for _, path, raw, receipt in sorted(ordered, key=lambda row: (row[0], row[1].name))[:-keep]:
            # Acknowledged evidence may still be needed to settle an interrupted
            # pending job; retain its individual receipt until that job is gone.
            pending = runner_checkpoint.queue(state, channel.removesuffix('.accepted'))
            pending_key = receipt.get('job_sha256')
            pending_paths = pending.entries()
            if isinstance(pending_key, str):
                unsettled = any(p.name.startswith(pending_key) for p in pending_paths)
            else:
                unsettled = any(worker.unpacked(p.name[:64], pending.read(p), max_batch=24*1024*1024).get('archive_sha256') == receipt.get('archive_sha256') for p in pending_paths)
            if unsettled:
                continue
            record = {'channel': channel, 'raw_hex': raw.hex()}
            key = path.name[:64]
            if key in records and records[key] != record:
                raise worker.AcquisitionError('CONFLICTING_RECEIPT_HISTORY')
            records[key] = record
            selected.append((spool, key))
    if not selected:
        return {'compacted': 0}
    digest, raw = worker.packed({'contract': CONTRACT, 'receipts': records}, max_batch=MAX_HISTORY)
    history.put(digest, raw)
    if history.read(history.directory / (digest + '.json.gz')) != raw:
        raise worker.AcquisitionError('RECEIPT_HISTORY_READBACK_FAILED')
    runner_checkpoint.flush_directory(history.directory)
    # Exact history was fsynced and read back before acknowledging originals.
    for spool, key in selected:
        spool.acknowledge(key)
    for path in previous:
        if path.name[:64] != digest:
            history.acknowledge(path.name[:64])
    return {'compacted': len(selected), 'history_receipts': len(records), 'history_sha256': digest}

#!/usr/bin/env python3
"""Checkpoint all retry queues after a worker stops; never sends or collects.

The caller must serialize collection and checkpoint operations. Checkpoints are
private immutable directories, including an explicit empty state. This module
does not upload artifacts or select a cloud checkpoint: that remains a separate
deployment/retention decision.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from outbox import Outbox, separate_spools
import outbox_bundle
from worker import AcquisitionError

CONTRACT = 'private-runner-checkpoint/v2'
LEGACY_CONTRACT = 'private-runner-checkpoint/v1'
RECEIPT_HISTORY_CONTRACT = 'private-runner-checkpoint/v3'
OFFICIAL_CONTRACT = 'private-runner-checkpoint/v4'
LEGACY_CHANNELS = {'archive': 'archive', 'quotes': 'quote',
                   'quotes.accepted': 'receipt', 'enrichment': 'enrichment'}
CHANNELS = {**LEGACY_CHANNELS,'dividends':'enrichment','dividends.accepted':'receipt'}
HISTORY_CHANNELS = {**CHANNELS, 'receipts.history': 'archive', 'quotes.quarantine': 'quote'}
ALL_CHANNELS = {**HISTORY_CHANNELS,
                'official_close':'enrichment', 'official_close.accepted':'receipt', 'official_close.quarantine':'enrichment'}
MANIFEST = 'CHECKPOINT.json'
MAX_TOTAL = 64 * 1024 * 1024


def private_directory(path, *, create=False):
    path = Path(path)
    if create:
        path.mkdir(mode=0o700)
    info = path.lstat()
    if path.is_symlink() or not path.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise AcquisitionError('CHECKPOINT_NOT_PRIVATE')
    return path


def write_new(path, body):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def flush_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def queue(root, channel):
    maximum = outbox_bundle.profile(ALL_CHANNELS[channel])[1]
    return Outbox(root / channel, entry_limit=maximum)


def inventory(root):
    allowed = set(ALL_CHANNELS) | {MANIFEST, 'enrichment.runner.lock','dividends.runner.lock'}
    if any(path.name not in allowed for path in root.iterdir()):
        raise AcquisitionError('CHECKPOINT_UNEXPECTED_STATE')
    for name, maximum in ((MANIFEST, 16 * 1024), ('enrichment.runner.lock', 0),('dividends.runner.lock',0)):
        if (root / name).exists() or (root / name).is_symlink():
            read_file(root / name, maximum)
    result = {}
    active = ALL_CHANNELS if any((root / name).exists() for name in set(ALL_CHANNELS)-set(CHANNELS)) else CHANNELS
    for channel in active:
        spool = queue(root, channel)
        result[channel] = {p.name: hashlib.sha256(spool.read(p)).hexdigest()
                           for p in spool.entries()}
    return result


def require_headroom(root, *, reserve_bytes, additions):
    """Reserve serialized evidence and ZIP overhead before a producer mutates queues."""
    if type(reserve_bytes) is not int or reserve_bytes<0 or set(additions)-set(ALL_CHANNELS):
        raise AcquisitionError('CHECKPOINT_RESERVATION_INVALID')
    state=private_directory(root)
    before=inventory(state)
    if any(type(n) is not int or n<0 for n in additions.values()):
        raise AcquisitionError('CHECKPOINT_RESERVATION_INVALID')
    for channel in set(before) | set(additions):
        if len(before.get(channel,{}))+additions.get(channel,0)>outbox_bundle.MAX_ENTRIES:
            raise AcquisitionError('CHECKPOINT_ENTRY_HEADROOM')
    used=sum(len(queue(state,channel).read(path)) for channel in before for path in queue(state,channel).entries())
    # Six bounded manifests plus ZIP local/central records and the outer marker.
    overhead=(len(ALL_CHANNELS)+2)*outbox_bundle.MAX_MANIFEST
    if used+reserve_bytes+overhead>MAX_TOTAL:raise AcquisitionError('CHECKPOINT_BYTE_HEADROOM')
    if inventory(state)!=before:raise AcquisitionError('CHECKPOINT_QUEUES_CHANGED')
    return {'existing_bytes':used,'reserved_bytes':reserve_bytes,'overhead_bytes':overhead}


def pack(state, output):
    state = private_directory(state)
    output = Path(output)
    separate_spools(state, output)
    before = inventory(state)
    private_directory(output, create=True)  # Exclusive; never overwrite a checkpoint.
    channels = {}
    total = 0
    for channel in before:
        kind = ALL_CHANNELS[channel]
        count = len(before[channel])
        entry = {'kind': kind, 'entries': count, 'sha256': None, 'bytes': 0}
        if count:
            target = output / (channel + '.zip')
            outbox_bundle.pack(state / channel, target, kind=kind)
            entry.update(sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                         bytes=target.stat().st_size)
            total += entry['bytes']
            if total > MAX_TOTAL:
                raise AcquisitionError('CHECKPOINT_CAPACITY')
        channels[channel] = entry
    if inventory(state) != before:
        raise AcquisitionError('CHECKPOINT_QUEUES_CHANGED')
    manifest = {'contract': OFFICIAL_CONTRACT if set(before)-set(HISTORY_CHANNELS) else RECEIPT_HISTORY_CONTRACT if set(before)-set(CHANNELS) else CONTRACT, 'channels': channels}
    # Marker is last: incomplete packing is never a usable checkpoint.
    body = (json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n').encode()
    write_new(output / MANIFEST, body)
    flush_directory(output)
    flush_directory(output.parent)
    return {'status': 'CHECKPOINTED', 'entries': sum(len(v) for v in before.values()),
            'bytes': total, 'manifest_sha256': hashlib.sha256(body).hexdigest()}


def read_file(path, maximum):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        import stat
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > maximum:
            raise AcquisitionError('CHECKPOINT_FILE_INVALID')
        body = stream.read(maximum + 1)
        if len(body) != info.st_size:
            raise AcquisitionError('CHECKPOINT_FILE_INVALID')
        return body


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AcquisitionError('CHECKPOINT_MANIFEST_INVALID')
        result[key] = value
    return result


def restore(checkpoint, state, *, expected_sha256):
    checkpoint = private_directory(checkpoint)
    state = Path(state)
    separate_spools(checkpoint, state)
    if state.exists() or state.is_symlink():
        raise AcquisitionError('CHECKPOINT_TARGET_EXISTS')
    body = read_file(checkpoint / MANIFEST, 16 * 1024)
    if not isinstance(expected_sha256, str) or not re.fullmatch('[a-f0-9]{64}', expected_sha256) or hashlib.sha256(body).hexdigest() != expected_sha256:
        raise AcquisitionError('CHECKPOINT_PIN_MISMATCH')
    value = json.loads(body, object_pairs_hook=unique_keys)
    if not isinstance(value,dict):raise AcquisitionError('CHECKPOINT_MANIFEST_INVALID')
    source_channels = (ALL_CHANNELS if value.get('contract') == OFFICIAL_CONTRACT else
                       HISTORY_CHANNELS if value.get('contract') == RECEIPT_HISTORY_CONTRACT else
                       LEGACY_CHANNELS if value.get('contract') == LEGACY_CONTRACT else CHANNELS)
    if set(value) != {'contract', 'channels'} or value.get('contract') not in [CONTRACT,LEGACY_CONTRACT,RECEIPT_HISTORY_CONTRACT,OFFICIAL_CONTRACT] or not isinstance(value['channels'], dict) or set(value['channels']) != set(source_channels):
        raise AcquisitionError('CHECKPOINT_MANIFEST_INVALID')
    expected_files = {MANIFEST}
    total = 0
    # Fully validate into a disposable private tree before touching the target.
    with tempfile.TemporaryDirectory(prefix='.checkpoint-verify-', dir=state.parent) as temporary:
        verified = Path(temporary)
        for channel, kind in source_channels.items():
            entry = value['channels'][channel]
            if not isinstance(entry, dict) or set(entry) != {'kind', 'entries', 'sha256', 'bytes'} or entry['kind'] != kind or type(entry['entries']) is not int or not 0 <= entry['entries'] <= outbox_bundle.MAX_ENTRIES or type(entry['bytes']) is not int or entry['bytes'] < 0:
                raise AcquisitionError('CHECKPOINT_MANIFEST_INVALID')
            spool = queue(verified, channel)
            if entry['entries']:
                if not isinstance(entry['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', entry['sha256']) or not 0 < entry['bytes'] <= MAX_TOTAL:
                    raise AcquisitionError('CHECKPOINT_MANIFEST_INVALID')
                name = channel + '.zip'
                expected_files.add(name)
                payload = read_file(checkpoint / name, entry['bytes'])
                total += len(payload)
                if total > MAX_TOTAL or len(payload) != entry['bytes'] or hashlib.sha256(payload).hexdigest() != entry['sha256']:
                    raise AcquisitionError('CHECKPOINT_PAYLOAD_MISMATCH')
                # Validate the captured bytes, not a path that could change later.
                frozen = verified / name
                write_new(frozen, payload)
                outbox_bundle.unpack(frozen, spool.directory, kind=kind)
                frozen.unlink()
                if len(spool.entries()) != entry['entries']:
                    raise AcquisitionError('CHECKPOINT_COUNT_MISMATCH')
            elif entry['sha256'] is not None or entry['bytes'] != 0:
                raise AcquisitionError('CHECKPOINT_MANIFEST_INVALID')
            else:
                spool._check_directory()
        if {p.name for p in checkpoint.iterdir()} != expected_files:
            raise AcquisitionError('CHECKPOINT_UNEXPECTED_FILE')
        private_directory(state, create=True)
        target_channels = ALL_CHANNELS if set(source_channels)-set(CHANNELS) else CHANNELS
        for channel in target_channels:
            if channel not in source_channels:queue(verified,channel)._check_directory()
            os.rename(verified / channel, state / channel)
            flush_directory(state / channel)
        # No consumer may start until this completion marker exists.
        write_new(state / MANIFEST, body)
        flush_directory(state)
        flush_directory(state.parent)
    return {'status': 'RESTORED', 'entries': sum(v['entries'] for v in value['channels'].values()),
            'bytes': total, 'manifest_sha256': expected_sha256}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    exporter = commands.add_parser('pack')
    exporter.add_argument('--state', type=Path, required=True)
    exporter.add_argument('--output', type=Path, required=True)
    importer = commands.add_parser('restore')
    importer.add_argument('--checkpoint', type=Path, required=True)
    importer.add_argument('--state', type=Path, required=True)
    importer.add_argument('--sha256', required=True)
    args = parser.parse_args(argv)
    previous_mask = os.umask(0o077)
    try:
        result = (pack(args.state, args.output) if args.command == 'pack' else
                  restore(args.checkpoint, args.state, expected_sha256=args.sha256))
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({'status': 'FAILED', 'code': str(error) if isinstance(error, AcquisitionError) else 'CHECKPOINT_FAILED'}))
        return 1
    finally:
        os.umask(previous_mask)


if __name__ == '__main__':
    raise SystemExit(main())

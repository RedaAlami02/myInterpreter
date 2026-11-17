#!/usr/bin/env python3
"""Bounded cross-run carriage for pending archive evidence.

The outbox lives on an ephemeral runner. This packs only pending transmission
copies into one bounded archive that a private workflow can persist, and restores
them into a fresh private spool with exact hash checks. It never collects, sends
or deletes evidence.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import zipfile

from outbox import Outbox
from worker import AcquisitionError

CONTRACT = "private-outbox-bundle/v1"
JOB_CONTRACT = "private-outbox-bundle/v2"
MANIFEST = "manifest.json"
NAME = re.compile(r"[a-f0-9]{64}\.json\.gz")
MAX_ENTRIES = 64
MAX_ENTRY = 8 * 1024 * 1024
MAX_JOB_ENTRY = 24 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_MANIFEST = 64 * 1024
MAX_CONTAINER = MAX_TOTAL + 3 * MAX_MANIFEST


@contextmanager
def _checked_zip(bundle):
    """Bound the container and central directory before ZipFile allocates its index.

    Our v1 packer produces single-disk, non-ZIP64 archives without comments.
    Inspect their standard 22-byte end record before parsing any entry metadata.
    """
    descriptor = os.open(bundle, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 22 <= info.st_size <= MAX_CONTAINER:
            raise AcquisitionError('OUTBOX_BUNDLE_LIMIT')
        stream.seek(-22, os.SEEK_END)
        signature, disk, start_disk, entries, total, size, offset, comment = struct.unpack('<4s4H2LH', stream.read(22))
        if signature != b'PK\x05\x06' or disk or start_disk or comment or entries != total:
            raise AcquisitionError('INVALID_OUTBOX_BUNDLE')
        if not 1 <= total <= MAX_ENTRIES + 1 or size > MAX_MANIFEST:
            raise AcquisitionError('OUTBOX_BUNDLE_LIMIT')
        if offset + size != info.st_size - 22:
            raise AcquisitionError('INVALID_OUTBOX_BUNDLE')
        with zipfile.ZipFile(stream) as archive:
            if len(archive.infolist()) != total:
                raise AcquisitionError('INVALID_OUTBOX_BUNDLE')
            yield archive


def _bounded_read(archive, info, maximum):
    if not 0 <= info.file_size <= maximum:
        raise AcquisitionError('OUTBOX_BUNDLE_LIMIT')
    with archive.open(info) as stream:
        body = stream.read(maximum + 1)
    if len(body) > maximum:
        raise AcquisitionError('OUTBOX_BUNDLE_LIMIT')
    if len(body) != info.file_size:
        raise AcquisitionError('INVALID_OUTBOX_BUNDLE')
    return body


def _zipinfo(name, mode=0o600):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = mode << 16
    return info


def profile(kind):
    if kind not in {'archive', 'enrichment', 'quote', 'receipt'}:
        raise AcquisitionError('INVALID_OUTBOX_KIND')
    return ((CONTRACT, MAX_ENTRY) if kind == 'archive' else
            (JOB_CONTRACT, MAX_ENTRY if kind == 'receipt' else MAX_JOB_ENTRY))


def pack(spool, output, *, kind='archive'):
    contract, maximum = profile(kind)
    outbox = Outbox(spool, entry_limit=maximum)
    entries = outbox.entries()
    if not entries:
        raise AcquisitionError("EMPTY_OUTBOX")
    if len(entries) > MAX_ENTRIES:
        raise AcquisitionError("OUTBOX_BUNDLE_LIMIT")
    output = Path(output)
    if output.resolve().is_relative_to(outbox.directory.resolve()):
        raise AcquisitionError('OUTBOX_BUNDLE_MUST_BE_OUTSIDE_SPOOL')
    if output.exists() or output.is_symlink():
        raise AcquisitionError("OUTBOX_BUNDLE_EXISTS")
    bodies = [(path.name, outbox.read(path)) for path in entries]
    if sum(len(body) for _, body in bodies) > MAX_TOTAL:
        raise AcquisitionError("OUTBOX_BUNDLE_LIMIT")
    manifest = {
        "contract": contract,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entries": [
            {"name": name, "sha256": name[:64], "bytes": len(body)}
            for name, body in bodies
        ],
    }
    if kind != 'archive':
        manifest.update(payload_kind=kind, entry_limit=maximum)
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    if len(manifest_bytes) > MAX_MANIFEST:
        raise AcquisitionError('OUTBOX_BUNDLE_LIMIT')
    descriptor, temporary = tempfile.mkstemp(
        prefix=".outbox-bundle-", dir=output.parent
    )
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            with zipfile.ZipFile(stream, "w") as archive:
                archive.writestr(
                    _zipinfo(MANIFEST),
                    manifest_bytes,
                )
                for name, body in bodies:
                    archive.writestr(_zipinfo(name), body)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError:
            raise AcquisitionError('OUTBOX_BUNDLE_EXISTS') from None
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {
        "status": "PACKED",
        "entries": len(bodies),
        "bytes": sum(len(body) for _, body in bodies),
        "bundle_bytes": output.stat().st_size,
    }


def unpack(bundle, spool, *, kind='archive'):
    contract, maximum = profile(kind)
    outbox = Outbox(spool, entry_limit=maximum)
    with _checked_zip(bundle) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or MANIFEST not in names:
            raise AcquisitionError("INVALID_OUTBOX_BUNDLE")
        if len(names) > MAX_ENTRIES + 1:
            raise AcquisitionError("OUTBOX_BUNDLE_LIMIT")
        try:
            manifest = json.loads(_bounded_read(archive, archive.getinfo(MANIFEST), MAX_MANIFEST))
        except (ValueError, UnicodeError):
            raise AcquisitionError("INVALID_OUTBOX_BUNDLE") from None
        if (
            not isinstance(manifest, dict)
            or manifest.get("contract") != contract
            or (kind != 'archive' and (manifest.get('payload_kind') != kind
                or type(manifest.get('entry_limit')) is not int or manifest['entry_limit'] != maximum))
            or not isinstance(manifest.get("entries"), list)
            or len(manifest["entries"]) != len(names) - 1
        ):
            raise AcquisitionError("INVALID_OUTBOX_BUNDLE")
        listed = {}
        for entry in manifest["entries"]:
            if (
                not isinstance(entry, dict)
                or set(entry) != {"name", "sha256", "bytes"}
                or not isinstance(entry["name"], str)
                or not NAME.fullmatch(entry["name"])
                or entry["sha256"] != entry["name"][:64]
                or not isinstance(entry["bytes"], int)
                or isinstance(entry["bytes"], bool)
                or not 0 < entry["bytes"] <= maximum
                or entry["name"] in listed
            ):
                raise AcquisitionError("INVALID_OUTBOX_BUNDLE")
            listed[entry["name"]] = entry
        if set(names) - {MANIFEST} != set(listed):
            raise AcquisitionError("INVALID_OUTBOX_BUNDLE")
        if sum(entry["bytes"] for entry in listed.values()) > MAX_TOTAL:
            raise AcquisitionError("OUTBOX_BUNDLE_LIMIT")
        before = {path.name for path in outbox.entries()}
        restored = 0
        for name, entry in listed.items():
            if archive.getinfo(name).file_size != entry["bytes"]:
                raise AcquisitionError("INVALID_OUTBOX_BUNDLE")
            body = _bounded_read(archive, archive.getinfo(name), maximum)
            if (
                len(body) != entry["bytes"]
                or hashlib.sha256(body).hexdigest() != entry["sha256"]
            ):
                raise AcquisitionError("OUTBOX_HASH_MISMATCH")
            outbox.put(entry["sha256"], body)
            if name not in before:
                restored += 1
    return {
        "status": "RESTORED",
        "restored": restored,
        "already_present": len(listed) - restored,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    packer = commands.add_parser("pack")
    packer.add_argument("--spool", type=Path, required=True)
    packer.add_argument("--output", type=Path, required=True)
    restorer = commands.add_parser("unpack")
    restorer.add_argument("--bundle", type=Path, required=True)
    restorer.add_argument("--spool", type=Path, required=True)
    for command in (packer, restorer):
        command.add_argument('--kind', choices=['archive', 'enrichment', 'quote', 'receipt'], default='archive')
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            result = pack(args.spool, args.output, kind=args.kind)
        else:
            result = unpack(args.bundle, args.spool, kind=args.kind)
        print(json.dumps(result))
        return 0
    except Exception as error:
        code = (
            str(error)
            if isinstance(error, AcquisitionError)
            else "OUTBOX_BUNDLE_FAILED"
        )
        print(json.dumps({"status": "FAILED", "code": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

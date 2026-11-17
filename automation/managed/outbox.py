"""Private local transmission copies. Never deletes unacknowledged evidence."""

import hashlib
import fcntl
from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat
import tempfile

from worker import AcquisitionError


def separate_spools(*directories):
    paths=[Path(path).resolve() for path in directories if path is not None]
    for index,path in enumerate(paths):
        if any(path.is_relative_to(other) or other.is_relative_to(path) for other in paths[:index]):
            raise AcquisitionError('WORKER_SPOOLS_MUST_BE_SEPARATE')


class Outbox:
    def __init__(self, directory, limit=64 * 1024 * 1024, *, entry_limit=8 * 1024 * 1024):
        if type(entry_limit) is not int or not 0 < entry_limit <= 24 * 1024 * 1024:
            raise AcquisitionError("OUTBOX_ENTRY_LIMIT")
        self.directory = Path(directory)
        self.limit = limit
        self.entry_limit = entry_limit

    def _check_directory(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        status = self.directory.lstat()
        if (
            not stat.S_ISDIR(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_mode & 0o077
        ):
            raise AcquisitionError("OUTBOX_NOT_PRIVATE")

    @contextmanager
    def _locked(self):
        self._check_directory()
        descriptor = os.open(
            self.directory / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            status = os.fstat(descriptor)
            if (
                not stat.S_ISREG(status.st_mode)
                or status.st_uid != os.getuid()
                or status.st_mode & 0o077
            ):
                raise AcquisitionError("OUTBOX_NOT_PRIVATE")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _paths(self):
        entries = []
        for path in sorted(self.directory.iterdir()):
            if path.name == ".lock":
                continue
            status = path.lstat()
            if (
                not stat.S_ISREG(status.st_mode)
                or status.st_uid != os.getuid()
                or status.st_mode & 0o077
                or not re.fullmatch(r"[a-f0-9]{64}\.json\.gz", path.name)
            ):
                raise AcquisitionError("OUTBOX_UNEXPECTED_ENTRY")
            entries.append(path)
        return entries

    def entries(self):
        with self._locked():
            return self._paths()

    def read(self, path):
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            body = stream.read(self.entry_limit + 1)
        if (
            len(body) > self.entry_limit
            or hashlib.sha256(body).hexdigest() + ".json.gz" != path.name
        ):
            raise AcquisitionError("OUTBOX_HASH_MISMATCH")
        return body

    def put(self, digest, body):
        if (
            not re.fullmatch(r"[a-f0-9]{64}", digest)
            or hashlib.sha256(body).hexdigest() != digest
        ):
            raise AcquisitionError("OUTBOX_HASH_MISMATCH")
        if len(body) > self.entry_limit:
            raise AcquisitionError("OUTBOX_ENTRY_LIMIT")
        with self._locked():
            entries = self._paths()
            target = self.directory / (digest + ".json.gz")
            if target in entries:
                if self.read(target) != body:
                    raise AcquisitionError("OUTBOX_HASH_MISMATCH")
                return
            if sum(path.stat().st_size for path in entries) + len(body) > self.limit:
                raise AcquisitionError("OUTBOX_CAPACITY")
            descriptor, temporary = tempfile.mkstemp(
                prefix=".writing-" + digest + "-", dir=self.directory
            )
            # Interrupted partial writes remain private and trigger explicit review.
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, target, follow_symlinks=False)
            self._sync_directory()
            os.unlink(temporary)
            self._sync_directory()

    def acknowledge(self, digest):
        with self._locked():
            target = self.directory / (digest + ".json.gz")
            if not target.exists():
                return  # Another sender may have acknowledged the same exact bytes.
            self.read(target)  # Recheck exact copy immediately before removal.
            target.unlink()
            self._sync_directory()

    def _sync_directory(self):
        descriptor = os.open(
            self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

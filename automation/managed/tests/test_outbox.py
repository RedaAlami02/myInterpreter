import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from outbox import Outbox
from worker import AcquisitionError


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / "outbox"
        self.store = Outbox(self.path)
        self.body = b"compressed-fixture-bytes"
        self.digest = hashlib.sha256(self.body).hexdigest()

    def test_exact_transmission_copy_persists_restart_without_duplicate(self):
        self.store.put(self.digest, self.body)
        self.store.put(self.digest, self.body)
        restarted = Outbox(self.path)
        self.assertEqual(len(restarted.entries()), 1)
        self.assertEqual(restarted.read(restarted.entries()[0]), self.body)

    def test_capacity_failure_preserves_existing_evidence(self):
        self.store.limit = len(self.body)
        self.store.put(self.digest, self.body)
        with self.assertRaisesRegex(AcquisitionError, "OUTBOX_CAPACITY"):
            self.store.put(hashlib.sha256(b"other").hexdigest(), b"other")
        self.assertEqual(len(self.store.entries()), 1)

    def test_wrong_hash_or_tampered_copy_is_never_uploaded(self):
        with self.assertRaisesRegex(AcquisitionError, "OUTBOX_HASH_MISMATCH"):
            self.store.put("a" * 64, self.body)
        self.store.put(self.digest, self.body)
        self.store.entries()[0].write_bytes(b"corrupted")
        with self.assertRaisesRegex(AcquisitionError, "OUTBOX_HASH_MISMATCH"):
            self.store.read(self.store.entries()[0])

    def test_acknowledgement_removes_only_matching_transmission_copy(self):
        self.store.put(self.digest, self.body)
        self.store.acknowledge(self.digest)
        self.assertEqual(self.store.entries(), [])

    def test_symlinks_and_group_readable_directories_are_rejected(self):
        self.path.mkdir(mode=0o755)
        self.path.chmod(0o755)  # Exercise unsafe permissions even under umask 077.
        with self.assertRaisesRegex(AcquisitionError, "OUTBOX_NOT_PRIVATE"):
            self.store.entries()
        self.path.chmod(0o700)
        (self.path / (self.digest + ".json.gz")).symlink_to(
            Path(self.root.name) / "outside"
        )
        with self.assertRaisesRegex(AcquisitionError, "OUTBOX_UNEXPECTED_ENTRY"):
            self.store.entries()


if __name__ == "__main__":
    unittest.main()

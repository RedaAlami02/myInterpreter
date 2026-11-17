import hashlib
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import outbox_bundle
import worker
from outbox import Outbox


def body(number):
    return gzip.compress(json.dumps({"n": number}).encode(), mtime=0)


def put(spool, number):
    value = body(number)
    digest = hashlib.sha256(value).hexdigest()
    Outbox(spool).put(digest, value)
    return digest + ".json.gz", value


def bundle_with(path, files, manifest=None, duplicate=None):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            outbox_bundle.MANIFEST,
            json.dumps(
                manifest if manifest is not None
                else {
                    "contract": outbox_bundle.CONTRACT,
                    "entries": [
                        {"name": name, "sha256": name[:64], "bytes": len(value)}
                        for name, value in files.items()
                    ],
                }
            ),
        )
        for name, value in files.items():
            archive.writestr(name, value)
        if duplicate:
            archive.writestr(duplicate, b"x")


class RoundTripTests(unittest.TestCase):
    def test_pack_and_unpack_preserve_exact_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            spool = folder / "spool"
            names = [put(spool, index) for index in (1, 2)]
            output = folder / "bundle.zip"
            result = outbox_bundle.pack(spool, output)
            self.assertEqual(result["status"], "PACKED")
            self.assertEqual(result["entries"], 2)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            restored = folder / "restored"
            second = outbox_bundle.unpack(output, restored)
            self.assertEqual(second, {
                "status": "RESTORED", "restored": 2, "already_present": 0,
            })
            for name, value in names:
                self.assertEqual((restored / name).read_bytes(), value)
            again = outbox_bundle.unpack(output, restored)
            self.assertEqual(again["restored"], 0)
            self.assertEqual(again["already_present"], 2)

    def test_pack_refuses_empty_existing_and_unsafe_spools(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            empty = folder / "empty"
            Outbox(empty)
            with self.assertRaisesRegex(worker.AcquisitionError, "EMPTY_OUTBOX"):
                outbox_bundle.pack(empty, folder / "b.zip")
            spool = folder / "spool"
            put(spool, 1)
            output = folder / "b.zip"
            output.write_bytes(b"existing")
            with self.assertRaisesRegex(
                worker.AcquisitionError, "OUTBOX_BUNDLE_EXISTS"
            ):
                outbox_bundle.pack(spool, output)
            loose = folder / "loose"
            put(loose, 1)
            os.chmod(loose, 0o755)
            with self.assertRaisesRegex(
                worker.AcquisitionError, "OUTBOX_NOT_PRIVATE"
            ):
                outbox_bundle.pack(loose, folder / "c.zip")
            unexpected = folder / "unexpected"
            put(unexpected, 1)
            (unexpected / "notes.txt").write_text("private")
            os.chmod(unexpected / "notes.txt", 0o600)
            with self.assertRaises(worker.AcquisitionError):
                outbox_bundle.pack(unexpected, folder / "d.zip")

    def test_pack_entry_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            spool = folder / "spool"
            for index in range(outbox_bundle.MAX_ENTRIES + 1):
                put(spool, index)
            with self.assertRaisesRegex(
                worker.AcquisitionError, "OUTBOX_BUNDLE_LIMIT"
            ):
                outbox_bundle.pack(spool, folder / "b.zip")


class UnpackValidationTests(unittest.TestCase):
    def reject(self, files, code, manifest=None, duplicate=None):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            path = folder / "bundle.zip"
            bundle_with(path, files, manifest, duplicate)
            with self.assertRaises(worker.AcquisitionError) as raised:
                outbox_bundle.unpack(path, folder / "spool")
            self.assertEqual(str(raised.exception), code)

    def entry(self, number=1):
        value = body(number)
        return hashlib.sha256(value).hexdigest() + ".json.gz", value

    def test_missing_manifest_or_wrong_contract(self):
        name, value = self.entry()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "b.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(name, value)
            with self.assertRaisesRegex(
                worker.AcquisitionError, "INVALID_OUTBOX_BUNDLE"
            ):
                outbox_bundle.unpack(path, Path(folder) / "spool")
        self.reject(
            {name: value},
            "INVALID_OUTBOX_BUNDLE",
            manifest={"contract": "private-outbox-bundle/v0", "entries": [
                {"name": name, "sha256": name[:64], "bytes": len(value)}
            ]},
        )

    def test_unknown_and_duplicate_names(self):
        name, value = self.entry()
        self.reject(
            {name: value, "evil.txt": b"x"},
            "INVALID_OUTBOX_BUNDLE",
        )
        self.reject({name: value}, "INVALID_OUTBOX_BUNDLE", duplicate=name)

    def test_declared_size_and_hash_are_enforced(self):
        name, value = self.entry()
        self.reject(
            {name: value},
            "INVALID_OUTBOX_BUNDLE",
            manifest={"contract": outbox_bundle.CONTRACT, "entries": [
                {"name": name, "sha256": name[:64], "bytes": len(value) + 1}
            ]},
        )
        tampered = value + b"x"
        self.reject(
            {name: tampered},
            "OUTBOX_HASH_MISMATCH",
            manifest={"contract": outbox_bundle.CONTRACT, "entries": [
                {"name": name, "sha256": name[:64], "bytes": len(tampered)}
            ]},
        )

    def test_corrupt_existing_entry_is_not_overwritten(self):
        name, value = self.entry()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            spool = folder / "spool"
            spool.mkdir(mode=0o700)
            (spool / name).write_bytes(b"corrupt")
            os.chmod(spool / name, 0o600)
            path = folder / "bundle.zip"
            bundle_with(path, {name: value})
            with self.assertRaises(worker.AcquisitionError):
                outbox_bundle.unpack(path, spool)

    def test_cli_reports_counts_only(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            spool = folder / "spool"
            put(spool, 1)
            output = folder / "b.zip"
            with_temp = [
                ["pack", "--spool", str(spool), "--output", str(output)],
                ["unpack", "--bundle", str(output), "--spool", str(folder / "r")],
            ]
            printed = []
            from unittest.mock import patch

            for arguments in with_temp:
                with patch("builtins.print") as mocked:
                    self.assertEqual(outbox_bundle.main(arguments), 0)
                    printed.append(json.loads(mocked.call_args.args[0]))
            self.assertEqual(printed[0]["status"], "PACKED")
            self.assertEqual(printed[1]["restored"], 1)


    def test_oversized_compressed_manifest_is_rejected_before_opening_entry(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bomb.zip'
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(outbox_bundle.MANIFEST, b' ' * (2 * 1024 * 1024))
            self.assertLess(path.stat().st_size, 10_000)
            with patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('must not decompress')):
                with self.assertRaisesRegex(worker.AcquisitionError, 'OUTBOX_BUNDLE_LIMIT'):
                    outbox_bundle.unpack(path, Path(folder) / 'spool')

    def test_excessive_directory_entries_are_rejected_before_zipfile_indexing(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'directory.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                for number in range(1000):
                    archive.writestr(str(number), b'')
            with patch.object(outbox_bundle.zipfile, 'ZipFile', side_effect=AssertionError('must not allocate index')):
                with self.assertRaisesRegex(worker.AcquisitionError, 'OUTBOX_BUNDLE_LIMIT'):
                    outbox_bundle.unpack(path, Path(folder) / 'spool')

    def test_stream_read_limit_is_enforced_even_if_metadata_lies(self):
        from io import BytesIO
        from types import SimpleNamespace
        from unittest.mock import Mock
        archive = Mock()
        archive.open.return_value = BytesIO(b'x' * (outbox_bundle.MAX_MANIFEST + 1))
        with self.assertRaisesRegex(worker.AcquisitionError, 'OUTBOX_BUNDLE_LIMIT'):
            outbox_bundle._bounded_read(archive, SimpleNamespace(file_size=1), outbox_bundle.MAX_MANIFEST)

    def test_oversized_container_is_refused_before_parsing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'oversized.zip'
            with path.open('wb') as stream:
                stream.truncate(outbox_bundle.MAX_CONTAINER + 1)
            with self.assertRaisesRegex(worker.AcquisitionError, 'OUTBOX_BUNDLE_LIMIT'):
                outbox_bundle.unpack(path, Path(folder) / 'spool')

    def test_pack_race_cannot_replace_an_existing_bundle(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            spool = Path(folder) / 'spool'
            put(spool, 1)
            output = Path(folder) / 'bundle.zip'
            def conflict(source, target):
                Path(target).write_bytes(b'existing-byte-identical-evidence-required')
                raise FileExistsError()
            with patch.object(outbox_bundle.os, 'link', side_effect=conflict):
                with self.assertRaisesRegex(worker.AcquisitionError, 'OUTBOX_BUNDLE_EXISTS'):
                    outbox_bundle.pack(spool, output)
            self.assertEqual(output.read_bytes(), b'existing-byte-identical-evidence-required')
            self.assertEqual(len(Outbox(spool).entries()), 1)


if __name__ == "__main__":
    unittest.main()

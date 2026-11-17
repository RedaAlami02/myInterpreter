import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "recover_market", Path(__file__).resolve().parents[1] / "tools/recover_appwrite_market.py")
RECOVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOVER)


def row(updated, price):
    return {"$id": "original-id", "$databaseId": "myinterpreter", "$collectionId": "data",
            "$createdAt": "2026-09-01T00:00:00Z", "$updatedAt": updated,
            "$permissions": ['read("any")'], "date": "2026-09-01T12:00:00Z",
            "c_name": "FIXTURE", "pa": price, "volume": None}


class RecoveryTests(unittest.TestCase):
    def test_later_capture_cannot_replace_a_newer_server_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(RECOVER, "ROOT", root):
                connection = sqlite3.connect(":memory:")
                RECOVER.initialize(connection)
                first = root / "first.json"
                first.write_text(json.dumps([row("2026-09-03T00:00:00Z", 123.45)]))
                older = root / "older.json"
                older.write_text(json.dumps([row("2026-09-02T00:00:00Z", 120)]))
                RECOVER.ingest(connection, first, RECOVER.iso("2026-09-04T00:00:00Z"), "baseline")
                RECOVER.ingest(connection, older, RECOVER.iso("2026-09-05T00:00:00Z"), "incremental_snapshot")
                actual = json.loads(connection.execute("SELECT payload FROM market").fetchone()[0])
                self.assertEqual(actual, row("2026-09-03T00:00:00Z", 123.45))

    def test_resume_rejects_modified_source_instead_of_silently_reimporting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(RECOVER, "ROOT", root):
                connection = sqlite3.connect(":memory:")
                RECOVER.initialize(connection)
                source = root / "source.json"
                source.write_text(json.dumps([row("2026-09-03T00:00:00Z", 123.45)]))
                observed = RECOVER.iso("2026-09-04T00:00:00Z")
                self.assertTrue(RECOVER.ingest(connection, source, observed, "baseline"))
                self.assertFalse(RECOVER.ingest(connection, source, observed, "baseline"))
                source.write_text("[]")
                with self.assertRaises(ValueError):
                    RECOVER.ingest(connection, source, observed, "baseline")

    def test_foreign_collection_is_rejected_without_partial_source_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(RECOVER, "ROOT", root):
                connection = sqlite3.connect(":memory:")
                RECOVER.initialize(connection)
                invalid = row("2026-09-03T00:00:00Z", 123.45)
                invalid["$collectionId"] = "portefeuille"
                source = root / "source.json"
                source.write_text(json.dumps([invalid]))
                with self.assertRaises(ValueError):
                    RECOVER.ingest(connection, source, RECOVER.iso("2026-09-04T00:00:00Z"), "baseline")
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

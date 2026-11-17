import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location(
    "export_appwrite", Path(__file__).resolve().parents[1] / "tools/export_appwrite.py")
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


class FakeAPI:
    def __init__(self, rows, field="documents", fail_at=None):
        self.rows = rows
        self.field = field
        self.fail_at = fail_at
        self.calls = []

    def get(self, path, queries):
        self.calls.append(queries)
        if self.fail_at == len(self.calls):
            raise EXPORT.ExportError(402, "limit_databases_reads_exceeded")
        offset = 0
        key = "key" if self.field in ("attributes", "indexes") else "$id"
        for query in queries:
            if query["method"] == "cursorAfter":
                offset = next(i + 1 for i, row in enumerate(self.rows)
                              if row[key] == query["values"][0])
            elif query["method"] == "offset":
                offset = query["values"][0]
        return {"total": len(self.rows), self.field: self.rows[offset:offset + 100]}


class ExportTests(unittest.TestCase):
    def test_accounts_are_saved_even_when_database_quota_is_exhausted(self):
        class QuotaAPI:
            def __init__(self):
                self.paths = []

            def get(self, path, queries):
                self.paths.append(path)
                if path == "/users":
                    return {"total": 1, "users": [{"$id": "original-user",
                             "password": "fixture-hash", "hash": "fixture-algorithm",
                             "hashOptions": {"cost": 12}, "prefs": {"language": "fr"}}]}
                if path == "/teams":
                    return {"total": 0, "teams": []}
                raise EXPORT.ExportError(402, "limit_databases_reads_exceeded")

        with tempfile.TemporaryDirectory() as directory:
            api = QuotaAPI()
            exporter = EXPORT.Exporter(Path(directory) / "backup", api)
            self.assertEqual(exporter.run(), 2)
            self.assertEqual(api.paths, ["/users", "/teams", "/databases"])
            self.assertTrue(exporter.state["jobs"]["users"]["complete"])
            payload = json.loads((exporter.output / "users/pages/000000.json").read_text())
            self.assertEqual(payload["users"][0]["password"], "fixture-hash")
            self.assertEqual(payload["users"][0]["hashOptions"], {"cost": 12})
            self.assertEqual(exporter.state["status"], "PARTIAL")

    def test_private_collections_are_exported_before_market_history(self):
        class InventoryAPI:
            def __init__(self):
                self.document_paths = []

            def get(self, path, queries):
                if path == "/users":
                    return {"total": 0, "users": []}
                if path == "/teams":
                    return {"total": 0, "teams": []}
                if path == "/databases":
                    return {"total": 1, "databases": [{"$id": "myinterpreter"}]}
                if path.endswith("/collections"):
                    ids = ["data", "benefits", "company", "achats", "ventes", "portefeuille"]
                    return {"total": len(ids), "collections": [{"$id": value} for value in ids]}
                field = path.split("/")[-1]
                if field == "documents":
                    self.document_paths.append(path.split("/")[-2])
                return {"total": 0, field: []}

        with tempfile.TemporaryDirectory() as directory:
            api = InventoryAPI()
            exporter = EXPORT.Exporter(Path(directory) / "backup", api)
            self.assertEqual(exporter.run(), 0)
            self.assertEqual(api.document_paths, ["achats", "ventes", "portefeuille", "benefits", "data", "company"])

    def test_empty_quota_blocked_resource_gets_fresh_cutoff_when_resumed(self):
        with tempfile.TemporaryDirectory() as directory:
            exporter = EXPORT.Exporter(Path(directory) / "backup", FakeAPI([], fail_at=1))
            with patch.object(EXPORT, "utc_now", return_value="2026-10-22T00:00:00.000+00:00"):
                with self.assertRaises(EXPORT.ExportError):
                    exporter.pages("data", "/documents", "documents", cutoff=True)
            api = FakeAPI([])
            resumed = EXPORT.Exporter(exporter.output, api, resume=True)
            with patch.object(EXPORT, "utc_now", return_value="2026-11-06T00:00:00.000+00:00"):
                resumed.pages("data", "/documents", "documents", cutoff=True)
            self.assertIn({"method": "lessThanEqual", "attribute": "$createdAt",
                           "values": ["2026-11-06T00:00:00.000+00:00"]}, api.calls[0])

    def test_quota_error_does_not_rotate_keys_or_repeat_database_requests(self):
        first = Mock()
        first.get.return_value.status_code = 402
        first.get.return_value.json.return_value = {"type": "limit_databases_reads_exceeded"}
        second = Mock()
        api = EXPORT.ReadOnlyAPI([])
        api.clients = [first, second]
        for path in ("/databases", "/databases/myinterpreter/collections"):
            with self.assertRaises(EXPORT.ExportError):
                api.get(path)
        self.assertEqual(first.get.call_count, 1)
        second.get.assert_not_called()

    def test_scope_failure_can_use_another_existing_key_with_get_only(self):
        first, second = Mock(), Mock()
        first.get.return_value.status_code = 401
        first.get.return_value.json.return_value = {
            "type": "general_unauthorized_scope", "message": 'missing scopes (["users.read"])'}
        second.get.return_value.status_code = 200
        second.get.return_value.json.return_value = {"total": 0, "users": []}
        api = EXPORT.ReadOnlyAPI([])
        api.clients = [first, second]
        self.assertEqual(api.get("/users"), {"total": 0, "users": []})
        self.assertFalse(second.get.call_args.kwargs["allow_redirects"])
        first.post.assert_not_called()
        second.post.assert_not_called()

    def test_resume_after_quota_failure_preserves_all_ids_and_permissions(self):
        rows = [{"$id": str(i), "$permissions": ['read("user:owner")'],
                 "value": i} for i in range(205)]
        with tempfile.TemporaryDirectory() as directory:
            first = EXPORT.Exporter(Path(directory) / "backup", FakeAPI(rows, fail_at=2))
            with self.assertRaises(EXPORT.ExportError):
                first.pages("data", "/documents", "documents")
            api = FakeAPI(rows)
            resumed = EXPORT.Exporter(first.output, api, resume=True)
            actual = resumed.pages("data", "/documents", "documents")
            self.assertEqual(actual, rows)
            self.assertEqual(len(api.calls), 2)
            self.assertIn({"method": "cursorAfter", "values": ["99"]}, api.calls[0])

    def test_exact_full_page_requires_final_empty_page(self):
        rows = [{"$id": str(i)} for i in range(100)]
        with tempfile.TemporaryDirectory() as directory:
            api = FakeAPI(rows)
            exporter = EXPORT.Exporter(Path(directory) / "backup", api)
            self.assertEqual(exporter.pages("data", "/documents", "documents"), rows)
            self.assertEqual(len(api.calls), 2)
            self.assertTrue(exporter.state["jobs"]["data"]["complete"])

    def test_schema_attributes_without_system_ids_use_offsets(self):
        rows = [{"key": f"field_{i}", "type": "string"} for i in range(103)]
        with tempfile.TemporaryDirectory() as directory:
            api = FakeAPI(rows, field="attributes")
            exporter = EXPORT.Exporter(Path(directory) / "backup", api)
            actual = exporter.pages("schema", "/attributes", "attributes",
                                    id_field="key", offset_pagination=True)
            self.assertEqual(actual, rows)
            self.assertIn({"method": "offset", "values": [100]}, api.calls[1])

    def test_corrupt_checkpoint_is_rejected_before_network_access(self):
        rows = [{"$id": "one"}]
        with tempfile.TemporaryDirectory() as directory:
            exporter = EXPORT.Exporter(Path(directory) / "backup", FakeAPI(rows))
            exporter.pages("data", "/documents", "documents")
            page = exporter.output / exporter.state["jobs"]["data"]["pages"][0]["file"]
            page.write_text("{}")
            api = FakeAPI(rows)
            resumed = EXPORT.Exporter(exporter.output, api, resume=True)
            with self.assertRaises(ValueError):
                resumed.pages("data", "/documents", "documents")
            self.assertEqual(api.calls, [])

    def test_count_mismatch_remains_flagged_after_resume(self):
        class WrongCountAPI(FakeAPI):
            def get(self, path, queries):
                response = super().get(path, queries)
                response["total"] = 2
                return response
        with tempfile.TemporaryDirectory() as directory:
            exporter = EXPORT.Exporter(Path(directory) / "backup", WrongCountAPI([{"$id": "one"}]))
            exporter.pages("data", "/documents", "documents")
            resumed = EXPORT.Exporter(exporter.output, FakeAPI([]), resume=True)
            resumed.pages("data", "/documents", "documents")
            self.assertIn("data", resumed.state["failures"])

    def test_duplicate_ids_never_produce_successful_export(self):
        with tempfile.TemporaryDirectory() as directory:
            api = FakeAPI([{"$id": "same"}, {"$id": "same"}])
            exporter = EXPORT.Exporter(Path(directory) / "backup", api)
            with self.assertRaises(ValueError):
                exporter.pages("data", "/documents", "documents")


if __name__ == "__main__":
    unittest.main()

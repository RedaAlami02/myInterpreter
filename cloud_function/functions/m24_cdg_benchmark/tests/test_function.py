import gzip
import hashlib
import importlib.util
import json
import sys
import threading
import time
import io
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
spec = importlib.util.spec_from_file_location("benchmark_main", SRC / "main.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class FakeDatabase:
    def __init__(self):
        self.docs = {}

    def get_document(self, database, collection, document):
        key = (collection, document)
        if key not in self.docs:
            raise KeyError(document)
        return self.docs[key]

    def create_document(self, database, collection, document, data, permissions=None):
        key = (collection, document)
        if key in self.docs:
            raise ValueError("duplicate document")
        self.docs[key] = {"$id": document, **data}
        return self.docs[key]

    def update_document(self, database, collection, document, data):
        self.docs[(collection, document)].update(data)
        return self.docs[(collection, document)]

    def list_documents(self, database, collection, queries=None):
        values = [doc for (name, _), doc in self.docs.items() if name == collection]
        if queries and "market_date" in str(queries):
            values = [doc for doc in values if doc.get("market_date") == "2026-09-23"]
        return {"documents": values, "total": len(values)}


class FakeStorage:
    def __init__(self):
        self.files = {}

    def get_file_download(self, bucket, file_id):
        return self.files[file_id]


class Response:
    def json(self, value):
        return value


class Context:
    def __init__(self, body=""):
        self.req = type("Request", (), {"headers": {}, "body": body})()
        self.res = Response()


@pytest.fixture
def cloud_mocks(monkeypatch):
    def get_doc(context, db, collection, document_id):
        del context
        try:
            return db.get_document("d", collection, document_id)
        except KeyError:
            return None

    def put_state(context, db, collection, document_id, market_date, state):
        del context
        data = {"market_date": market_date, "state_json": json.dumps(state, sort_keys=True, separators=(",", ":"))}
        if get_doc(None, db, collection, document_id) is None:
            return db.create_document("d", collection, document_id, data, permissions=[])
        return db.update_document("d", collection, document_id, data)

    def list_for_date(context, db, collection, market_date, limit=500):
        del context, market_date, limit
        return db.list_documents("d", collection, ["market_date"])

    def all_manifests(context, db, market_date):
        docs = list_for_date(context, db, benchmark.BATCHES, market_date).get("documents", [])
        return [benchmark.state_from_doc(doc) for doc in docs if json.loads(doc.get("state_json", "{}")).get("kind") == "RAW_BURST"]

    monkeypatch.setattr(benchmark, "get_doc", get_doc)
    monkeypatch.setattr(benchmark, "put_state", put_state)
    monkeypatch.setattr(benchmark, "list_for_date", list_for_date)
    monkeypatch.setattr(benchmark, "_all_batch_manifests", all_manifests)
    monkeypatch.setattr(benchmark, "_download", lambda context, storage, file_id: storage.get_file_download("b", file_id))


def test_source_connectivity_probe_is_payload_free_and_checks_both_sources(monkeypatch):
    monkeypatch.setattr(benchmark, "_m24_api", lambda method, isin: [{"public_field": "not returned"}])
    monkeypatch.setattr(benchmark, "_cdg_snapshot", lambda symbol: {"source_timestamp": "t", "raw_schema_hash": "abc", "provider_errors": []})
    result = benchmark.connectivity_probe("CRS")
    assert result["persisted"] is False
    assert result["freshness_classification"] == "UNCHANGED_UNKNOWN"
    assert result["results"]["CDG_DELAYED"]["status"] == "SUCCESS"
    assert result["results"]["MEDIAS24_PUBLIC"]["parse_success"] is True
    assert "not returned" not in json.dumps(result)


def test_http_429_is_separate_from_other_errors():
    response = requests.Response()
    response.status_code = 429
    exc = requests.HTTPError(response=response)
    assert benchmark.error_category(exc) == "HTTP_429"


def test_time_guard_rejects_post_close_without_appwrite_or_provider_calls(monkeypatch):
    local = datetime(2026, 9, 23, 15, 22, tzinfo=benchmark.TZ)
    monkeypatch.setattr(benchmark, "now_utc", lambda: local.astimezone(timezone.utc))
    monkeypatch.setattr(benchmark, "appwrite_client", lambda context: pytest.fail("no Appwrite access expected"))
    monkeypatch.setattr(benchmark, "_m24_snapshot", lambda symbol: pytest.fail("no network expected"))
    result = benchmark.main(Context())
    assert result["status"] == "NO_SESSION"


def test_slot_id_is_deterministic_within_slot():
    first = datetime(2026, 9, 23, 10, 1, 1, tzinfo=benchmark.TZ).astimezone(timezone.utc)
    second = datetime(2026, 9, 23, 10, 14, 59, tzinfo=benchmark.TZ).astimezone(timezone.utc)
    assert benchmark.slot_id(first) == benchmark.slot_id(second) == "2026-09-23_1000"


def test_slot_claim_returns_noop_for_completed_slot(cloud_mocks):
    db = FakeDatabase()
    sid = "2026-09-23_1000"
    doc_id = "slot_202609231000"
    db.create_document("d", benchmark.SLOTS, doc_id, {"market_date": "2026-09-23", "state_json": json.dumps({"status": "COMPLETE", "slot_id": sid})})
    _, state, result = benchmark.claim_slot(Context(), db, "2026-09-23", sid)
    assert state is None
    assert result == "ALREADY_COMPLETE"


def test_expired_slot_lease_can_recover_without_reusing_batch_id(cloud_mocks):
    db = FakeDatabase()
    sid = "2026-09-23_1000"
    doc_id = "slot_202609231000"
    expired = {"status": "COLLECTING", "slot_id": sid, "attempt": 1, "lease_until": "2020-01-01T00:00:00Z"}
    db.create_document("d", benchmark.SLOTS, doc_id,
                       {"market_date": "2026-09-23", "state_json": json.dumps(expired)})
    _, state, result = benchmark.claim_slot(Context(), db, "2026-09-23", sid)
    assert result == "CLAIMED"
    assert state["attempt"] == 2


def test_pair_collection_is_concurrent_and_batch_is_gzip_sha256_idempotent(monkeypatch, cloud_mocks):
    db = FakeDatabase(); storage = FakeStorage(); uploaded = []; guard = threading.Lock()
    active = [0]; max_active = [0]
    monkeypatch.setattr(benchmark, "BURST_SECONDS", 0.10)
    monkeypatch.setattr(benchmark, "CYCLE_SECONDS", 0.02)
    monkeypatch.setattr(benchmark, "now_utc", lambda: datetime(2026, 9, 23, 9, 30, tzinfo=benchmark.TZ).astimezone(timezone.utc))

    def invoke(source, symbol, cycle, position):
        with guard:
            active[0] += 1
            max_active[0] = max(max_active[0], active[0])
        started = benchmark.iso()
        time.sleep(0.015)
        with guard:
            active[0] -= 1
        return {"source": source, "symbol": symbol, "cycle_id": cycle, "operation": "quote",
                "fetch_order": "CONCURRENT", "source_position": position,
                "request_started_at_utc": started, "request_finished_at_utc": benchmark.iso(),
                "received_at_utc": benchmark.iso(), "transport_duration_ms": 15.0, "phase": "CONTINUOUS",
                "phase_start": "CONTINUOUS", "phase_end": "CONTINUOUS", "session_date_status": "SESSION_DATE_UNVERIFIED",
                "error": "HTTP_403" if source == "MEDIAS24_PUBLIC" else None,
                "provider_errors": [], "transactions": [], "data": None}

    monkeypatch.setattr(benchmark, "invoke", invoke)
    monkeypatch.setattr(benchmark, "_upload_bytes", lambda st, name, content, mime: (uploaded.append((name, content)) or {"$id": "file-1"}))
    when = datetime(2026, 9, 23, 10, 0, tzinfo=benchmark.TZ).astimezone(timezone.utc)
    result = benchmark.collect_burst(Context(), db, storage, when)
    assert result["status"] == "COMPLETE"
    assert result["provider_errors"] > 0  # M24 error did not cancel CDG observations.
    assert max_active[0] >= 2
    assert len(uploaded) == 1
    packed = uploaded[0][1]
    rows = [json.loads(line) for line in gzip.decompress(packed).decode().splitlines()]
    assert rows and all(row["request_started_at_utc"] and row["request_finished_at_utc"] for row in rows)
    manifest_doc = next(doc for (name, _), doc in db.docs.items() if name == benchmark.BATCHES)
    manifest = json.loads(manifest_doc["state_json"])
    assert hashlib.sha256(packed).hexdigest() == manifest["sha256"]
    again = benchmark.collect_burst(Context(), db, storage, when)
    assert again["status"] == "ALREADY_COMPLETE"
    assert len(uploaded) == 1


def test_statistics_require_twenty_directional_events():
    matches = [{"event_type": "BOOK", "scope": "TOP5", "direction": "M24_FIRST",
                "observed_first_seen_difference_seconds": 3} for _ in range(19)]
    result = next(row for row in benchmark.summaries([], matches) if row["scope"] == "TOP5")
    assert result["statistics_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["median_observed_first_seen_difference_seconds"] is None
    matches.append(dict(matches[0]))
    result = next(row for row in benchmark.summaries([], matches) if row["scope"] == "TOP5")
    assert result["statistics_status"] == "REVIEW_REQUIRED"


def test_finalizer_verifies_batches_writes_private_report_manifest_and_is_idempotent(monkeypatch, cloud_mocks):
    db = FakeDatabase(); storage = FakeStorage(); uploads = []
    day = "2026-09-23"
    db.create_document("d", benchmark.RUNS, "run_" + day,
                       {"market_date": day, "state_json": json.dumps({"market_date": day, "run_id": day,
                           "status": "COLLECTING", "bursts_expected": 24, "bursts_completed": 1,
                           "rows": 0, "provider_errors": 0, "finalized_at": None})})
    raw = gzip.compress(b"", mtime=0)
    storage.files["raw-file"] = raw
    manifest = {"batch_id": "raw-test", "market_date": day, "kind": "RAW_BURST", "storage_file_id": "raw-file",
                "sha256": hashlib.sha256(raw).hexdigest()}
    db.create_document("d", benchmark.BATCHES, "raw-test", {"market_date": day, "kind": "RAW_BURST",
                       "sha256": manifest["sha256"], "storage_file_id": "raw-file", "state_json": json.dumps(manifest)})
    monkeypatch.setattr(benchmark, "_upload_bytes", lambda st, name, content, mime: (uploads.append((name, content)) or {"$id": "report-file"}))
    when = datetime(2026, 9, 23, 15, 30, tzinfo=benchmark.TZ).astimezone(timezone.utc)
    result = benchmark.finalize_run(Context(), db, storage, when, day)
    assert result["status"] == "FAILED"  # no active observations; finalization still reports the empty day.
    report = uploads[0][1]
    with tarfile.open(fileobj=io.BytesIO(report), mode="r:gz") as archive:
        names = set(archive.getnames())
    assert {"MEDIAS24_CDG_BOOK_EVENTS.csv", "MEDIAS24_CDG_TRADE_EVENTS.csv", "MEDIAS24_CDG_QUOTE_EVENTS.csv",
            "MULTISOURCE_LATENCY_SUMMARY.csv", "PROVIDER_NETWORK_TIMING.csv", "FETCH_ORDER_BIAS_REPORT.md",
            "LONG_SESSION_SUMMARY.md"}.issubset(names)
    run = json.loads(db.get_document("d", benchmark.RUNS, "run_" + day)["state_json"])
    assert run["finalized_at"]
    assert run["statistics_gate_passed"] is False
    assert benchmark.finalize_run(Context(), db, storage, when, day)["status"] == "ALREADY_FINALIZED"
    assert len(uploads) == 1


def test_production_and_freshness_registries_are_not_referenced():
    source = (SRC / "main.py").read_text(encoding="utf-8")
    assert "SOURCE_REGISTRY.json" not in source
    assert "GETprice" not in source
    assert "CDG_DELAYED" in source

"""Private scheduled M24/CDG observation benchmark; it never changes routing."""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import tarfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from appwrite.client import Client
from appwrite.id import ID
from appwrite.input_file import InputFile
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logic import canonical_hash, event_inventory, market_phase, match_events, network_stats, summaries

TZ = ZoneInfo("Africa/Casablanca")
DB_ID = os.environ.get("APPWRITE_DATABASE_ID", "myinterpreter")
BUCKET_ID = os.environ.get("BENCHMARK_BUCKET_ID", "orderbook-history")
RUNS = "realtime_benchmark_runs"
SLOTS = "realtime_benchmark_slots"
BATCHES = "realtime_benchmark_batches"
SYMBOLS = ("ATW", "IAM", "BCP", "CRS")
ISINS = {"ATW": "MA0000012445", "IAM": "MA0000011488", "BCP": "MA0000011884", "CRS": "MA0000011868"}
WINDOW_START = (9, 30)
WINDOW_END = (15, 20)
SLOT_MINUTES = 15
BURST_SECONDS = 60
CYCLE_SECONDS = 5
EXPECTED_SLOTS = 24
LEASE_SECONDS = 240
M24_BASE = "https://medias24.com/content/api"
CDG_URL = os.environ.get("CDG_API_URL", "https://www.cdgcapitalbourse.ma/api/")
UA = "myinterpreter-multisource-research/1.0"


def now_utc():
    return datetime.now(timezone.utc)


def iso(value=None):
    return (value or now_utc()).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def local_slot(value):
    local = value.astimezone(TZ)
    minute = (local.minute // SLOT_MINUTES) * SLOT_MINUTES
    return local.replace(minute=minute, second=0, microsecond=0)


def slot_id(value):
    return local_slot(value).strftime("%Y-%m-%d_%H%M")


def collection_open(value):
    local = value.astimezone(TZ)
    return (local.weekday() < 5 and (local.hour, local.minute) >= WINDOW_START
            and (local.hour, local.minute) < WINDOW_END)


def is_slot_time(value):
    local = value.astimezone(TZ)
    return (collection_open(value) and local.minute % SLOT_MINUTES == 0
            and local.second <= 180)


def is_finalizer_time(value):
    local = value.astimezone(TZ)
    return local.weekday() < 5 and (local.hour, local.minute) >= (15, 30)


def appwrite_client(context):
    key = (context.req.headers or {}).get("x-appwrite-key", "")
    if not key:
        raise RuntimeError("MISSING_FUNCTION_EXECUTION_KEY")
    endpoint = os.environ.get("APPWRITE_ENDPOINT") or os.environ.get("APPWRITE_FUNCTION_API_ENDPOINT")
    project_id = os.environ.get("APPWRITE_PROJECT_ID") or os.environ.get("APPWRITE_FUNCTION_PROJECT_ID")
    if not endpoint or not project_id:
        raise RuntimeError("MISSING_APPWRITE_RUNTIME_CONFIGURATION")
    return Client().set_endpoint(endpoint).set_project(project_id).set_key(key)


def appwrite_runtime(context):
    headers = context.req.headers or {}
    key = headers.get("x-appwrite-key", "")
    endpoint = os.environ.get("APPWRITE_ENDPOINT") or os.environ.get("APPWRITE_FUNCTION_API_ENDPOINT")
    project_id = os.environ.get("APPWRITE_PROJECT_ID") or os.environ.get("APPWRITE_FUNCTION_PROJECT_ID")
    if not key or not endpoint or not project_id:
        raise RuntimeError("MISSING_APPWRITE_RUNTIME_CONFIGURATION")
    return endpoint.rstrip("/"), project_id, key


def appwrite_get(context, path, params=None):
    endpoint, project_id, key = appwrite_runtime(context)
    response = requests.get(endpoint + path, params=params or {}, headers={
        "X-Appwrite-Project": project_id, "X-Appwrite-Key": key, "Accept": "application/json"}, timeout=30)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def state_from_doc(document):
    raw = document.get("state_json", "{}") if isinstance(document, dict) else document._data.get("state_json", "{}")
    return json.loads(raw or "{}")


def get_doc(context, db, collection, document_id):
    del db
    path = "/databases/%s/collections/%s/documents/%s" % (quote(DB_ID, safe=""), quote(collection, safe=""), quote(document_id, safe=""))
    return appwrite_get(context, path)


def put_state(context, db, collection, document_id, market_date, state):
    payload = {"market_date": market_date, "state_json": json.dumps(state, sort_keys=True, separators=(",", ":"))}
    if get_doc(context, db, collection, document_id) is not None:
        db.update_document(DB_ID, collection, document_id, payload)
    else:
        db.create_document(DB_ID, collection, document_id, payload, permissions=[])


def list_for_date(context, db, collection, market_date, limit=500):
    del db
    path = "/databases/%s/collections/%s/documents" % (quote(DB_ID, safe=""), quote(collection, safe=""))
    query = json.dumps({"method": "equal", "attribute": "market_date", "values": [market_date]}, separators=(",", ":"))
    return appwrite_get(context, path, [("limit", str(limit)), ("queries[]", query)])


def _number(value):
    if value in (None, "", "-", "--"):
        return None


def error_category(exc):
    if isinstance(exc, requests.HTTPError):
        code = exc.response.status_code if exc.response is not None else None
        return "HTTP_%s" % code if code else "HTTP_ERROR"
    if isinstance(exc, requests.Timeout):
        return "TIMEOUT"
    if isinstance(exc, requests.ConnectionError):
        message = str(exc).lower()
        return "DNS_OR_CONNECTION_ERROR" if "name or service" in message or "nodename" in message else "CONNECTION_ERROR"
    message = str(exc)
    if message.startswith("SCHEMA_ERROR"):
        return message.split(":", 1)[0]
    return "PARSE_OR_VALUE_ERROR" if isinstance(exc, ValueError) else type(exc).__name__.upper()


def safe_http_diagnostics(exc):
    response = getattr(exc, "response", None)
    if response is None:
        return {}
    body = response.content or b""
    return {"http_status": response.status_code,
            "response_bytes": len(body),
            "response_content_type": response.headers.get("Content-Type"),
            "response_server": response.headers.get("Server"),
            "response_body_sha256": hashlib.sha256(body).hexdigest() if body else None}
    if isinstance(value, (float, int)):
        return value
    text = str(value).replace("\u00a0", " ").replace("\u202f", " ").replace(" ", "").replace(",", ".")
    try:
        parsed = float(text)
        return int(parsed) if parsed.is_integer() else parsed
    except (ValueError, TypeError):
        return None


def _m24_api(method, isin=None):
    params = {"method": method, "format": "json", "t": now_utc().strftime("%Y-%m-%d-%H:%M")}
    if isin:
        params["ISIN"] = isin
    url = M24_BASE + "?" + urllib.parse.urlencode(params)
    response = requests.get(url, timeout=5, headers={"User-Agent": UA, "Accept": "application/json,text/plain,*/*",
                                                      "Referer": "https://medias24.com/leboursier/fiche-action"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), (dict, list)):
        raise ValueError("SCHEMA_ERROR_M24_" + method)
    return payload["result"]


def _m24_snapshot(symbol):
    isin = ISINS[symbol]
    values = {}; component_errors = []
    # The three public frontend calls are concurrent within the source adapter.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_m24_api, method, isin): method for method in ("getStockInfo", "getBidAsk", "getTransactions")}
        for future in as_completed(futures):
            try:
                values[futures[future]] = future.result()
            except Exception as exc:
                component_errors.append({"operation": futures[future], "error": error_category(exc)})
    quote_value = values.get("getStockInfo")
    quote = quote_value[0] if isinstance(quote_value, list) and quote_value else quote_value
    if not isinstance(quote, dict) and "getBidAsk" not in values:
        raise ValueError("SCHEMA_ERROR_M24_QUOTE")
    quote = quote if isinstance(quote, dict) else {}
    book_value = values.get("getBidAsk", [])
    book_payload = book_value if isinstance(book_value, dict) else {"orderBook": book_value}
    book_rows = book_payload.get("orderBook") or []
    bids, asks = [], []
    for row in book_rows[:10]:
        bid = _number(row.get("bidValue")); ask = _number(row.get("askValue"))
        if bid not in (None, 0):
            bids.append({"level": len(bids) + 1, "price": bid, "quantity": _number(row.get("bidQte")), "order_count": _number(row.get("bidOrder")), "level_time": None})
        if ask not in (None, 0):
            asks.append({"level": len(asks) + 1, "price": ask, "quantity": _number(row.get("askQte")), "order_count": _number(row.get("askOrder")), "level_time": None})
    raw_trades = values.get("getTransactions", [])
    if not isinstance(raw_trades, list):
        raw_trades = []
    trades = [{"time": row.get("heure"), "price": _number(row.get("prix")), "quantity": _number(row.get("qte")),
               "value_mad": _number(row.get("total")), "sequence": row.get("id") or row.get("sequence")} for row in raw_trades if isinstance(row, dict)]
    data = {"source": "MEDIAS24_PUBLIC", "symbol": symbol, "source_timestamp": quote.get("cotation"),
            "quote_timestamp": quote.get("cotation"), "last_trade_timestamp": trades[-1].get("time") if trades else None,
            "vendor_timestamp": quote.get("cotation"), "last_price": _number(quote.get("cours")),
            "open": _number(quote.get("ouverture")), "high": _number(quote.get("max")), "low": _number(quote.get("min")),
            "best_bid": bids[0]["price"] if bids else None, "best_bid_qty": bids[0]["quantity"] if bids else None,
            "best_bid_orders": bids[0]["order_count"] if bids else None, "best_ask": asks[0]["price"] if asks else None,
            "best_ask_qty": asks[0]["quantity"] if asks else None, "best_ask_orders": asks[0]["order_count"] if asks else None,
            "daily_quantity": _number(quote.get("volumeTitre")), "daily_turnover": _number(quote.get("volume")),
            "transaction_count": len(trades), "status": None, "phase": None,
            "freshness_class": "UNKNOWN", "book": {"bids": bids, "asks": asks}, "transactions": trades,
            "provider_errors": component_errors,
            "raw_schema_hash": canonical_hash({"quote": sorted(quote.keys()), "book": sorted((book_rows[0] if book_rows else {}).keys()),
                                                "transaction": sorted((raw_trades[0] if raw_trades else {}).keys())})}
    return data


def _cdg_action(name, symbol, top=None):
    params = [{"NAME": "Lang_", "TYPE": "S", "VALUE": "FR"}, {"NAME": "Espace_", "TYPE": "I", "VALUE": "1"},
              {"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol}]
    if name == "VALEUR-PROFONDEUR":
        params.append({"NAME": "NumSeq_", "TYPE": "I", "VALUE": "0"})
    if top is not None:
        params.append({"NAME": "Top_", "TYPE": "I", "VALUE": str(top)})
    return {"ACTION": {"NAME": name, "TYPE": "SELECT", "VALUE": name}, "PARAMS": params}


def _cdg_snapshot(symbol):
    actions = [_cdg_action("VALEUR-SYNTHESE", symbol), _cdg_action("VALEUR-PROFONDEUR", symbol, 10)]
    response = requests.post(CDG_URL, json={"ACTIONS": actions}, timeout=5, headers={"User-Agent": UA})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("SCHEMA_ERROR_CDG_ENVELOPE")
    values = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        for name, envelope in item.items():
            if not isinstance(envelope, dict) or not envelope.get("Valid"):
                raise ValueError("SCHEMA_ERROR_CDG_" + str(name))
            values[name] = envelope.get("Data", [])
    summary_rows = values.get("VALEUR-SYNTHESE") or []
    summary = summary_rows[0] if summary_rows else {}
    depth = values.get("VALEUR-PROFONDEUR") or []
    bids, asks = [], []
    for row in depth[:10]:
        if row.get("Achat") not in (None, "", 0, "0"):
            bids.append({"level": len(bids) + 1, "price": _number(row.get("Achat")), "quantity": _number(row.get("QteAchat")),
                         "order_count": _number(row.get("NbrAchat")), "level_time": row.get("HeureAchat")})
        if row.get("Vente") not in (None, "", 0, "0"):
            asks.append({"level": len(asks) + 1, "price": _number(row.get("Vente")), "quantity": _number(row.get("QteVente")),
                         "order_count": _number(row.get("NbrVente")), "level_time": row.get("HeureVente")})
    component_errors = []
    try:
        trade_response = requests.post(CDG_URL, json={"ACTIONS": [_cdg_action("VALEUR-TRANSACTIONS", symbol)]}, timeout=5,
                                       headers={"User-Agent": UA})
        trade_response.raise_for_status()
        trade_payload = trade_response.json()
        raw_trades = []
        for item in trade_payload if isinstance(trade_payload, list) else []:
            for name, envelope in item.items():
                if name == "VALEUR-TRANSACTIONS" and isinstance(envelope, dict) and envelope.get("Valid"):
                    raw_trades = envelope.get("Data", [])
    except Exception as exc:
        component_errors.append({"operation": "VALEUR-TRANSACTIONS", "error": error_category(exc)})
    trades = [{"time": row.get("Heure") or row.get("DateCours") or row.get("DateTransaction"),
               "price": _number(row.get("Cours") or row.get("Prix")), "quantity": _number(row.get("NbrTitre") or row.get("Qte") or row.get("Quantite")),
               "value_mad": _number(row.get("Volume") or row.get("Valeur")),
               "sequence": row.get("NumSeq") or row.get("NumTransaction") or row.get("IdTransaction"), "raw": row} for row in raw_trades if isinstance(row, dict)]
    return {"source": "CDG_DELAYED", "symbol": symbol, "source_timestamp": summary.get("DateJour"),
            "quote_timestamp": summary.get("DateJour"), "last_trade_timestamp": summary.get("DateCours"), "vendor_timestamp": summary.get("DateJour"),
            "last_price": _number(summary.get("Cours")), "open": _number(summary.get("Ouverture")), "high": _number(summary.get("PlusHaut")),
            "low": _number(summary.get("PlusBas")), "best_bid": bids[0]["price"] if bids else None,
            "best_bid_qty": bids[0]["quantity"] if bids else None, "best_bid_orders": bids[0]["order_count"] if bids else None,
            "best_ask": asks[0]["price"] if asks else None, "best_ask_qty": asks[0]["quantity"] if asks else None,
            "best_ask_orders": asks[0]["order_count"] if asks else None, "daily_quantity": _number(summary.get("NbrTitre")),
            "daily_turnover": _number(summary.get("Volume")), "transaction_count": _number(summary.get("NbrTransaction")),
            "status": summary.get("Cotation"), "phase": summary.get("Phase"), "freshness_class": "DELAYED",
            "book": {"bids": bids, "asks": asks}, "transactions": trades, "provider_errors": component_errors,
            "raw_schema_hash": canonical_hash({"summary": sorted(summary.keys()), "depth": sorted((depth[0] if depth else {}).keys()),
                                                "transaction": sorted((raw_trades[0] if raw_trades else {}).keys())})}


def invoke(source, symbol, cycle, position):
    started_at = iso(); begin = time.perf_counter()
    try:
        data = _m24_snapshot(symbol) if source == "MEDIAS24_PUBLIC" else _cdg_snapshot(symbol)
        error = None
    except requests.HTTPError as exc:
        error = error_category(exc); data = None
    except Exception as exc:
        error = error_category(exc)
        data = None
    duration_ms = round((time.perf_counter() - begin) * 1000.0, 3)
    finished_at = iso(); phase = market_phase(finished_at)
    row = {"source": source, "symbol": symbol, "operation": "quote", "cycle_id": cycle,
           "fetch_order": "CONCURRENT", "source_position": position,
           "request_started_at_utc": started_at, "request_finished_at_utc": finished_at,
           "received_at_utc": finished_at, "transport_duration_ms": duration_ms,
           "phase": phase, "phase_start": market_phase(started_at), "phase_end": phase,
           "session_date_status": "SESSION_DATE_UNVERIFIED", "error": error,
           "freshness_class": "DELAYED" if source == "CDG_DELAYED" else "UNKNOWN", "data": data}
    if data:
        row.update({key: data.get(key) for key in ("source_timestamp", "quote_timestamp", "last_trade_timestamp", "vendor_timestamp",
                                                   "last_price", "best_bid", "best_bid_qty", "best_bid_orders", "best_ask",
                                                   "best_ask_qty", "best_ask_orders", "daily_quantity", "daily_turnover", "status")})
        book = data.get("book") or {}
        for depth in (1, 5, 10):
            row["top%d_hash" % depth] = canonical_hash([
                [[item.get("price"), item.get("quantity"), item.get("order_count")] for item in (book.get(side) or [])[:depth]]
                for side in ("bids", "asks")])
        row["transactions"] = data.get("transactions", [])
        row["provider_errors"] = data.get("provider_errors", [])
    else:
        row["transactions"] = []
    return row


def claim_slot(context, db, market_date, sid):
    slot_doc = "slot_" + sid.replace("-", "").replace("_", "")
    existing = get_doc(context, db, SLOTS, slot_doc)
    now = now_utc()
    if existing is not None:
        state = state_from_doc(existing)
        if state.get("status") == "COMPLETE":
            return slot_doc, None, "ALREADY_COMPLETE"
        lease = state.get("lease_until")
        if state.get("status") == "COLLECTING" and lease and _parse_iso(lease) > now:
            return slot_doc, None, "SLOT_IN_PROGRESS"
        attempt = int(state.get("attempt", 0)) + 1
    else:
        attempt = 1
    state = {"slot_id": sid, "market_date": market_date, "status": "COLLECTING", "attempt": attempt,
             "lease_until": iso(now + timedelta(seconds=LEASE_SECONDS)), "started_at": iso(now),
             "bursts_expected": EXPECTED_SLOTS}
    try:
        put_state(context, db, SLOTS, slot_doc, market_date, state)
    except Exception:
        # A parallel scheduler/manual invocation may have won the create race.
        raced = get_doc(context, db, SLOTS, slot_doc)
        if raced is None:
            raise
        raced_state = state_from_doc(raced)
        if raced_state.get("status") == "COMPLETE":
            return slot_doc, None, "ALREADY_COMPLETE"
        if raced_state.get("status") == "COLLECTING" and raced_state.get("lease_until") and _parse_iso(raced_state["lease_until"]) > now:
            return slot_doc, None, "SLOT_IN_PROGRESS"
        raise
    return slot_doc, state, "CLAIMED"


def _parse_iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def connectivity_probe(symbol="CRS"):
    """No-write transport/schema probe for explicit manual invocation only."""
    symbol = symbol.upper()
    if symbol not in ISINS:
        return {"status": "INVALID_SYMBOL", "allowed_symbols": sorted(ISINS)}
    output = {"MEDIAS24_PUBLIC": {"endpoints": {}}}
    m24_methods = ("getStockInfo", "getBidAsk", "getTransactions")
    m24_started = {method: time.perf_counter() for method in m24_methods}
    cdg_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_m24_api, method, ISINS[symbol]): method for method in m24_methods}
        futures[pool.submit(_cdg_snapshot, symbol)] = "CDG_DELAYED"
        for future in as_completed(futures):
            name = futures[future]
            if name == "CDG_DELAYED":
                try:
                    value = future.result()
                    output[name] = {"status": "SUCCESS", "parse_success": True,
                                    "source_timestamp": value.get("source_timestamp"),
                                    "schema_hash": value.get("raw_schema_hash"),
                                    "component_errors": value.get("provider_errors", []),
                                    "transport_duration_ms": round((time.perf_counter() - cdg_started) * 1000, 3)}
                except Exception as exc:
                    output[name] = {"status": error_category(exc), "parse_success": False}
                continue
            try:
                value = future.result()
                first = value[0] if isinstance(value, list) and value else value
                schema = sorted(first.keys()) if isinstance(first, dict) else type(first).__name__
                output["MEDIAS24_PUBLIC"]["endpoints"][name] = {"status": "SUCCESS", "result_type": "list" if isinstance(value, list) else "object",
                    "result_count": len(value) if isinstance(value, (list, dict)) else None,
                    "schema_hash": canonical_hash(schema), "parse_success": True,
                    "transport_duration_ms": round((time.perf_counter() - m24_started[name]) * 1000, 3)}
            except Exception as exc:
                output["MEDIAS24_PUBLIC"]["endpoints"][name] = {"status": error_category(exc), "parse_success": False,
                    **safe_http_diagnostics(exc),
                    "transport_duration_ms": round((time.perf_counter() - m24_started[name]) * 1000, 3)}
    endpoints_ok = sum(item.get("parse_success", False) for item in output["MEDIAS24_PUBLIC"]["endpoints"].values())
    output["MEDIAS24_PUBLIC"]["status"] = "SUCCESS" if endpoints_ok else "FAILED"
    output["MEDIAS24_PUBLIC"]["parse_success"] = endpoints_ok == len(m24_methods)
    return {"status": "PROBE_COMPLETE", "symbol": symbol, "timestamp": iso(), "results": output,
            "persisted": False, "freshness_classification": "UNCHANGED_UNKNOWN"}


def _upload_bytes(storage, name, content, mime):
    temp_path = None
    try:
        prefix = name.rsplit(".", 1)[0][:32] + "-"
        with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".gz", delete=False) as handle:
            handle.write(content); temp_path = handle.name
        return storage.create_file(BUCKET_ID, ID.unique(), InputFile.from_path(temp_path), permissions=[])
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def collect_burst(context, db, storage, current):
    local = current.astimezone(TZ); market_date = local.date().isoformat(); sid = slot_id(current)
    slot_doc, state, claim_status = claim_slot(context, db, market_date, sid)
    if state is None:
        return {"status": claim_status, "slot_id": sid}
    rows = []; started = time.monotonic(); cycle_index = 0; errors = 0
    # All sources and symbols begin together per cycle; source-specific minima remain 5 seconds.
    workers = ThreadPoolExecutor(max_workers=len(SYMBOLS) * 2)
    try:
        while time.monotonic() - started < BURST_SECONDS:
            cycle_started = time.monotonic(); cycle_id = "%s_c%02d" % (sid, cycle_index)
            futures = {}
            for symbol in SYMBOLS:
                futures[workers.submit(invoke, "MEDIAS24_PUBLIC", symbol, cycle_id, "PAIR_THREAD_M24")] = (symbol, "MEDIAS24_PUBLIC")
                futures[workers.submit(invoke, "CDG_DELAYED", symbol, cycle_id, "PAIR_THREAD_CDG")] = (symbol, "CDG_DELAYED")
            for future in as_completed(futures):
                try:
                    row = future.result()
                except Exception as exc:
                    symbol, source = futures[future]
                    row = {"source": source, "symbol": symbol, "operation": "quote", "cycle_id": cycle_id,
                           "fetch_order": "CONCURRENT", "source_position": "PAIR_THREAD_" + source,
                           "request_started_at_utc": iso(), "request_finished_at_utc": iso(), "received_at_utc": iso(),
                           "transport_duration_ms": None, "phase": "CONTINUOUS", "phase_start": "CONTINUOUS", "phase_end": "CONTINUOUS",
                           "session_date_status": "SESSION_DATE_UNVERIFIED", "error": type(exc).__name__.upper(),
                           "freshness_class": "UNKNOWN", "data": None, "transactions": []}
                rows.append(row)
                errors += int(bool(row.get("error"))) + len(row.get("provider_errors", []))
            cycle_index += 1
            wait = CYCLE_SECONDS - (time.monotonic() - cycle_started)
            if wait > 0:
                time.sleep(wait)
    finally:
        workers.shutdown(wait=True)
    rows.sort(key=lambda row: row["received_at_utc"])
    raw_payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str) + "\n" for row in rows).encode()
    compressed = gzip.compress(raw_payload, compresslevel=6, mtime=0)
    digest = hashlib.sha256(compressed).hexdigest()
    batch_id = "raw_" + ID.unique()
    upload = _upload_bytes(storage, batch_id + ".jsonl.gz", compressed, "application/gzip")
    file_id = upload.get("$id") or getattr(upload, "id", None)
    manifest_id = batch_id
    manifest = {"batch_id": batch_id, "run_id": market_date, "market_date": market_date, "slot_id": sid,
                "kind": "RAW_BURST", "storage_file_id": file_id, "storage_path": "multisource/%s/%s/%s.jsonl.gz" % (local.strftime("%Y/%m/%d/%H"), sid, batch_id),
                "sha256": digest, "compressed_bytes": len(compressed), "uncompressed_bytes": len(raw_payload),
                "row_count": len(rows), "symbols": list(SYMBOLS), "cycle_count": cycle_index, "schema_version": "benchmark-observation-v1",
                "uploaded_at": iso(), "attempt": state["attempt"]}
    db.create_document(DB_ID, BATCHES, manifest_id,
                       {"market_date": market_date, "kind": "RAW_BURST", "sha256": digest,
                        "storage_file_id": file_id, "state_json": json.dumps(manifest, sort_keys=True, separators=(",", ":"))}, permissions=[])
    finished = now_utc()
    state.update({"status": "COMPLETE", "lease_until": None, "finished_at": iso(finished), "batch_id": batch_id,
                  "rows": len(rows), "cycles": cycle_index, "provider_errors": errors,
                  "symbols": list(SYMBOLS), "request_successes": sum(not bool(row.get("error")) for row in rows)})
    put_state(context, db, SLOTS, slot_doc, market_date, state)
    completed = list_for_date(context, db, SLOTS, market_date).get("documents", [])
    states = [state_from_doc(item) for item in completed]
    complete_slots = [item for item in states if item.get("status") == "COMPLETE" and not str(item.get("slot_id", "")).endswith("_FINALIZE")]
    all_rows = sum(int(item.get("rows", 0)) for item in complete_slots)
    all_errors = sum(int(item.get("provider_errors", 0)) for item in complete_slots)
    run_state = {"run_id": market_date, "market_date": market_date, "status": "COLLECTING",
                 "symbols": list(SYMBOLS), "bursts_expected": EXPECTED_SLOTS, "bursts_completed": len(complete_slots),
                 "first_collection_at": min([item["started_at"] for item in complete_slots] or [iso()]),
                 "last_collection_at": max([item["finished_at"] for item in complete_slots] or [iso()]),
                 "rows": all_rows, "provider_errors": all_errors, "finalized_at": None,
                 "session_date_status": "SESSION_DATE_UNVERIFIED"}
    put_state(context, db, RUNS, "run_" + market_date, market_date, run_state)
    return {"status": "COMPLETE", "slot_id": sid, "rows": len(rows), "provider_errors": errors, "batch_id": batch_id}


def _all_batch_manifests(context, db, market_date):
    docs = list_for_date(context, db, BATCHES, market_date, limit=500).get("documents", [])
    output = []
    for doc in docs:
        state = state_from_doc(doc)
        if state.get("kind") == "RAW_BURST":
            output.append(state)
    return output


def _download(context, storage, file_id):
    del storage
    endpoint, project_id, key = appwrite_runtime(context)
    path = "/storage/buckets/%s/files/%s/download" % (quote(BUCKET_ID, safe=""), quote(file_id, safe=""))
    response = requests.get(endpoint + path, headers={"X-Appwrite-Project": project_id,
                            "X-Appwrite-Key": key}, timeout=90)
    response.raise_for_status()
    return response.content


def _csv_bytes(rows):
    if not rows:
        return b"\n"
    fields = sorted(set(key for row in rows for key in row.keys()))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    return buffer.getvalue().encode("utf-8")


def finalize_run(context, db, storage, current, market_date_override=None):
    local = current.astimezone(TZ); market_date = market_date_override or local.date().isoformat()
    run_doc_id = "run_" + market_date; existing = get_doc(context, db, RUNS, run_doc_id)
    if existing is None and not _all_batch_manifests(context, db, market_date):
        return {"status": "NO_SESSION", "market_date": market_date, "reason": "NO_BENCHMARK_RUN"}
    run = state_from_doc(existing) if existing is not None else {"run_id": market_date, "market_date": market_date,
        "status": "WAITING", "symbols": list(SYMBOLS), "bursts_expected": EXPECTED_SLOTS,
        "bursts_completed": 0, "first_collection_at": None, "last_collection_at": None,
        "rows": 0, "provider_errors": 0, "finalized_at": None, "session_date_status": "SESSION_DATE_UNVERIFIED"}
    if run.get("finalized_at"):
        return {"status": "ALREADY_FINALIZED", "market_date": market_date}
    slot_docs = list_for_date(context, db, SLOTS, market_date).get("documents", [])
    burst_states = [state_from_doc(item) for item in slot_docs]
    completed_bursts = [item for item in burst_states if item.get("status") == "COMPLETE" and not str(item.get("slot_id", "")).endswith("_FINALIZE")]
    if completed_bursts:
        run["bursts_completed"] = len(completed_bursts)
        run["rows"] = sum(int(item.get("rows", 0)) for item in completed_bursts)
        run["provider_errors"] = sum(int(item.get("provider_errors", 0)) for item in completed_bursts)
        run["first_collection_at"] = min(item.get("started_at", "") for item in completed_bursts if item.get("started_at"))
        run["last_collection_at"] = max(item.get("finished_at", "") for item in completed_bursts if item.get("finished_at"))
    finalize_slot_id = market_date + "_FINALIZE"
    finalize_doc, finalize_state, lock_status = claim_slot(context, db, market_date, finalize_slot_id)
    if finalize_state is None:
        return {"status": "ALREADY_FINALIZED" if lock_status == "ALREADY_COMPLETE" else "FINALIZER_IN_PROGRESS",
                "market_date": market_date}
    run["finalizing_at"] = iso()
    report_id = "report_" + market_date.replace("-", "")
    existing_report = get_doc(context, db, BATCHES, report_id)
    if existing_report is not None:
        report_manifest = state_from_doc(existing_report)
        run.update({"status": run.get("status") if run.get("status") in ("INSUFFICIENT_EVIDENCE", "REVIEW_REQUIRED", "COMPLETE") else "INSUFFICIENT_EVIDENCE",
                    "finalized_at": iso(), "report_manifest_id": report_id,
                    "report_file_id": report_manifest.get("storage_file_id")})
        put_state(context, db, RUNS, run_doc_id, market_date, run)
        finalize_state.update({"status": "COMPLETE", "lease_until": None, "finished_at": iso(), "report_manifest_id": report_id})
        put_state(context, db, SLOTS, finalize_doc, market_date, finalize_state)
        return {"status": "ALREADY_FINALIZED_FROM_MANIFEST", "market_date": market_date}
    run["status"] = "FINALIZING"; put_state(context, db, RUNS, run_doc_id, market_date, run)
    raw_rows = []
    for manifest in _all_batch_manifests(context, db, market_date):
        blob = _download(context, storage, manifest["storage_file_id"])
        if hashlib.sha256(blob).hexdigest() != manifest["sha256"]:
            raise ValueError("BATCH_SHA256_MISMATCH:" + manifest["batch_id"])
        for line in gzip.decompress(blob).decode("utf-8").splitlines():
            if line.strip():
                raw_rows.append(json.loads(line))
    events = event_inventory(raw_rows); matches = match_events(events); summary = summaries(events, matches); network = network_stats(raw_rows)
    book_events = [row for row in matches if row["event_type"] == "BOOK"]
    trade_events = [row for row in matches if row["event_type"] == "TRADE"]
    quote_events = [row for row in matches if row["event_type"] == "QUOTE"]
    counts = {"M24_FIRST": 0, "CDG_FIRST": 0, "SAME_POLL_WINDOW": 0, "AMBIGUOUS": 0}
    for item in matches:
        counts[item["direction"]] = counts.get(item["direction"], 0) + 1
    meets = any(row["unambiguous_events"] >= 20 for row in summary)
    observed_active = any(row.get("phase") == "CONTINUOUS" and not row.get("error") for row in raw_rows)
    status = "REVIEW_REQUIRED" if meets else ("INSUFFICIENT_EVIDENCE" if observed_active else "FAILED")
    report_lines = ["# Cloud benchmark run summary", "", "Market date: %s" % market_date,
                    "Session date status: SESSION_DATE_UNVERIFIED (weekday schedule; no authoritative calendar assertion)",
                    "Slots completed: %s / %s" % (run.get("bursts_completed", 0), EXPECTED_SLOTS),
                    "Raw observation rows: %s" % len(raw_rows), "Matched book/trade/quote events: %s / %s / %s" % (len(book_events), len(trade_events), len(quote_events)),
                    "Directional counts: %s" % json.dumps(counts, sort_keys=True),
                    "Statistics gate: %s (>=20 directional matches per event/depth group)" % ("REVIEW_REQUIRED" if meets else "INSUFFICIENT_EVIDENCE"),
                    "Run status: %s" % status, "", "No source freshness class or production route is changed by this Function.",
                    "Network timing below is adapter-call duration, not feed latency.", "Polling event times are interval-censored.", ""]
    files = {"MEDIAS24_CDG_BOOK_EVENTS.csv": _csv_bytes(book_events), "MEDIAS24_CDG_TRADE_EVENTS.csv": _csv_bytes(trade_events),
             "MEDIAS24_CDG_QUOTE_EVENTS.csv": _csv_bytes(quote_events), "MULTISOURCE_LATENCY_SUMMARY.csv": _csv_bytes(summary),
             "PROVIDER_NETWORK_TIMING.csv": _csv_bytes(network), "FETCH_ORDER_BIAS_REPORT.md": ("# Fetch-order bias report\n\nPair calls use concurrent worker launches for each symbol and cycle. Both request start/finish timestamps and source positions are retained. A directional result requires non-overlapping interval-censored bounds; a threshold pass is marked REVIEW_REQUIRED and never updates source_registry.json or production routing.\n\n" + "Directional outcomes: " + json.dumps(counts, sort_keys=True) + "\n").encode(),
             "LONG_SESSION_SUMMARY.md": "\n".join(report_lines).encode()}
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as bundle:
        for name, content in files.items():
            info = tarfile.TarInfo(name); info.size = len(content); info.mtime = 0
            bundle.addfile(info, io.BytesIO(content))
    bundle_bytes = archive.getvalue(); digest = hashlib.sha256(bundle_bytes).hexdigest()
    upload = _upload_bytes(storage, report_id + ".tar.gz", bundle_bytes, "application/gzip")
    file_id = upload.get("$id") or getattr(upload, "id", None)
    report_manifest = {"batch_id": report_id, "run_id": market_date, "market_date": market_date,
                       "kind": "FINAL_REPORTS", "storage_file_id": file_id,
                       "storage_path": "multisource/%s/reports/%s.zip" % (local.strftime("%Y/%m/%d"), report_id),
                       "sha256": digest, "compressed_bytes": len(bundle_bytes), "uncompressed_bytes": sum(len(x) for x in files.values()),
                       "report_files": sorted(files), "uploaded_at": iso(), "schema_version": "benchmark-report-v1"}
    db.create_document(DB_ID, BATCHES, report_id,
                       {"market_date": market_date, "kind": "FINAL_REPORTS", "sha256": digest,
                        "storage_file_id": file_id, "state_json": json.dumps(report_manifest, sort_keys=True, separators=(",", ":"))}, permissions=[])
    run.update({"status": status, "finalized_at": iso(), "report_manifest_id": report_id,
                "report_file_id": file_id, "matched_book_events": len(book_events),
                "matched_trade_events": len(trade_events), "matched_quote_events": len(quote_events),
                "statistics_gate_passed": meets, "review_required": meets,
                "provider_errors": sum(bool(row.get("error")) for row in raw_rows)})
    put_state(context, db, RUNS, run_doc_id, market_date, run)
    finalize_state.update({"status": "COMPLETE", "lease_until": None, "finished_at": iso(), "rows": len(raw_rows),
                           "report_manifest_id": report_id})
    put_state(context, db, SLOTS, finalize_doc, market_date, finalize_state)
    return {"status": status, "market_date": market_date, "rows": len(raw_rows), "reports": len(files),
            "statistics_gate_passed": meets, "report_manifest_id": report_id}


def main(context):
    current = now_utc(); local = current.astimezone(TZ)
    body = getattr(context.req, "body", "") or ""
    try:
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        request_body = json.loads(body) if body else {}
    except (TypeError, ValueError):
        request_body = {}
    if request_body.get("mode") == "CONNECTIVITY_PROBE":
        return context.res.json(connectivity_probe(request_body.get("symbol", "CRS")))
    if local.weekday() >= 5:
        return context.res.json({"status": "NO_SESSION", "reason": "WEEKEND", "local_time": local.isoformat()})
    if is_finalizer_time(current) or collection_open(current):
        client = appwrite_client(context); db = Databases(client); storage = Storage(client)
        # Recover prior incomplete dates on the next invocation, even after a PC/cloud outage.
        pending_path = "/databases/%s/collections/%s/documents" % (quote(DB_ID, safe=""), quote(RUNS, safe=""))
        pending = (appwrite_get(context, pending_path, {"limit": "100"}) or {}).get("documents", [])
        for document in pending:
            pending_run = state_from_doc(document)
            pending_date = pending_run.get("market_date")
            if not pending_date or pending_run.get("finalized_at"):
                continue
            if pending_date < local.date().isoformat() or (pending_date == local.date().isoformat() and is_finalizer_time(current)):
                finalize_run(context, db, storage, current, pending_date)
        if is_finalizer_time(current):
            return context.res.json(finalize_run(context, db, storage, current))
    if not collection_open(current):
        return context.res.json({"status": "NO_SESSION", "reason": "OUTSIDE_CONTINUOUS_COLLECTION_WINDOW", "local_time": local.isoformat()})
    if not is_slot_time(current):
        return context.res.json({"status": "NO_SLOT", "local_time": local.isoformat()})
    return context.res.json(collect_burst(context, db, storage, current))

"""Five-minute private, change-only CDG_DELAYED order-book pilot."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

import requests
from appwrite.client import Client
from appwrite.id import ID
from appwrite.input_file import InputFile
from appwrite.query import Query
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage

DB_ID = "myinterpreter"
BUCKET_ID = "orderbook-history"
SOURCE = "CDG_DELAYED"
SCHEMA = "orderbook-v1"
API_URL = os.environ.get("CDG_API_URL", "https://www.cdgcapitalbourse.ma/api/")

# The session gate ships with its own copy of the IANA rule; see market_window.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_window import diagnostics as tz_diagnostics  # noqa: E402
from market_window import gate as session_gate  # noqa: E402


def action(name, symbol, top=None):
    params = [{"NAME": "Lang_", "TYPE": "S", "VALUE": "FR"}, {"NAME": "Espace_", "TYPE": "I", "VALUE": "1"}, {"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol}]
    if name == "VALEUR-PROFONDEUR": params.append({"NAME": "NumSeq_", "TYPE": "I", "VALUE": "0"})
    if top is not None: params.append({"NAME": "Top_", "TYPE": "I", "VALUE": str(top)})
    return {"ACTION": {"NAME": name, "TYPE": "SELECT", "VALUE": name}, "PARAMS": params}


def request(actions):
    response = requests.post(API_URL, json={"ACTIONS": actions}, timeout=15, headers={"User-Agent": "myinterpreter-orderbook-pilot/1.0"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list): raise ValueError("unexpected CDG response envelope")
    output = {}
    for item in payload:
        for name, envelope in item.items():
            if not envelope.get("Valid"): raise ValueError(f"CDG invalid {name}")
            output[name] = envelope.get("Data", [])
    return output


def symbols():
    raw = request([{ "ACTION": {"NAME": "TICKER", "TYPE": "SELECT", "VALUE": "TICKER"}, "PARAMS": [
        {"NAME":"Espace_","TYPE":"I","VALUE":"1"}, {"NAME":"IdPartener_","TYPE":"I","VALUE":"1"},
        {"NAME":"Lang_","TYPE":"S","VALUE":"XX"}, {"NAME":"NumseqMin_","TYPE":"I","VALUE":"0"}, {"NAME":"NumseqMax_","TYPE":"I","VALUE":"0"}]}])
    return sorted({str(row.get("Symbol", "")).upper() for row in raw["TICKER"] if row.get("Symbol")})


def normalize(symbol, raw, received_at):
    summary = (raw.get("VALEUR-SYNTHESE") or [{}])[0]
    depth = raw.get("VALEUR-PROFONDEUR") or []
    value = {"schema_version": SCHEMA, "source": SOURCE, "collector_id": "appwrite-orderbook-pilot",
             "symbol": symbol, "source_market_timestamp": summary.get("DateJour"), "received_at": received_at,
             "status": summary.get("Cotation"), "trading_phase": summary.get("Phase"), "last_trade_price": summary.get("Cours"),
             "last_trade_time": summary.get("DateCours"), "daily_open": summary.get("Ouverture"), "daily_high": summary.get("PlusHaut"),
             "daily_low": summary.get("PlusBas"), "daily_quantity": summary.get("NbrTitre"), "daily_turnover_mad": summary.get("Volume"),
             "daily_transaction_count": summary.get("NbrTransaction"),
             "bids": [{"level": i + 1, "price": row.get("Achat"), "quantity": row.get("QteAchat"), "orders": row.get("NbrAchat"), "level_time": row.get("HeureAchat")} for i, row in enumerate(depth[:5]) if row.get("Achat")],
             "asks": [{"level": i + 1, "price": row.get("Vente"), "quantity": row.get("QteVente"), "orders": row.get("NbrVente"), "level_time": row.get("HeureVente")} for i, row in enumerate(depth[:5]) if row.get("Vente")]}
    comparable = dict(value); comparable.pop("received_at")
    value["content_hash"] = hashlib.sha256(json.dumps(comparable, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return value


def market_open(now):
    """Should this run collect, and why?

    The comparison is between UTC instants: `now` against an explicit session
    open and close computed for the Casablanca calendar date. It deliberately
    does not ask the container what the local time is — the container's time
    zone database was an hour stale, which cost every session its closing hour.

    Ramadan/date overrides stay configuration-driven through an env JSON list,
    rather than hardcoded calendar assumptions.
    """
    periods = json.loads(os.environ.get("RAMADAN_PERIODS_JSON", "[]"))
    return session_gate(now, ramadan_periods=periods)


def client(context):
    key = (context.req.headers or {}).get("x-appwrite-key", "")
    if not key: raise RuntimeError("missing dynamic execution key")
    return Client().set_endpoint(os.environ["APPWRITE_ENDPOINT"]).set_project(os.environ["APPWRITE_PROJECT_ID"]).set_key(key)


def main(context):
    started = datetime.now(timezone.utc); run_id = ID.unique(); db = Databases(client(context)); storage = Storage(client(context))
    decision = market_open(started)
    # The gate's reasoning goes to the execution log on every run, including the
    # ones that decide not to collect. A run that refuses is the interesting case,
    # and the offset and window it refused against are what make it diagnosable
    # rather than mysterious. No secrets are involved.
    logged = {k: decision[k] for k in (
        "state", "market_date", "market_mode", "casablanca_offset_seconds",
        "session_open_utc", "session_close_utc", "now_utc",
        "zone_source", "tzdata_sha256")}
    # Also record what the container itself believes. When these two disagree the
    # gate is doing its job, and the discrepancy is visible in the log instead of
    # having to be inferred from a missing hour of captures.
    logged.update(tz_diagnostics())
    context.log("session gate: " + json.dumps(logged, sort_keys=True))
    opened, phase = decision["open"], decision["market_mode"]
    if not opened:
        db.create_document(DB_ID, "orderbook_collector_runs", run_id, {"run_id":run_id,"source":SOURCE,"started_at":started.isoformat(),"finished_at":datetime.now(timezone.utc).isoformat(),"market_phase":phase,"status":"NO_SESSION","attempted":0,"succeeded":0,"changed":0,"unchanged":0,"failed":0,"source_empty":0})
        return context.res.json({"status":"NO_SESSION","run_id":run_id})
    attempted=succeeded=changed=unchanged=failed=empty=0; latencies=[]; changed_rows=[]
    try: names = symbols()
    except Exception as exc:
        db.create_document(DB_ID,"orderbook_collector_runs",run_id,{"run_id":run_id,"source":SOURCE,"started_at":started.isoformat(),"finished_at":datetime.now(timezone.utc).isoformat(),"market_phase":phase,"status":"FAILED_SYMBOL_DISCOVERY","attempted":0,"succeeded":0,"changed":0,"unchanged":0,"failed":1,"source_empty":0})
        context.error(type(exc).__name__); return context.res.json({"status":"FAILED_SYMBOL_DISCOVERY"},502)
    for symbol in names:
        attempted += 1; began=time.perf_counter()
        try:
            raw=request([action("VALEUR-SYNTHESE",symbol),action("VALEUR-PROFONDEUR",symbol,5)])
            snapshot=normalize(symbol,raw,datetime.now(timezone.utc).isoformat()); latencies.append((time.perf_counter()-began)*1000); succeeded += 1
            doc_id=f"{SOURCE}_{symbol}"; previous=None
            try: previous=db.get_document(DB_ID,"orderbook_latest",doc_id)._data.get("content_hash")
            except Exception: pass
            if previous == snapshot["content_hash"]: unchanged += 1
            else:
                changed += 1; changed_rows.append(snapshot)
                current={"source":SOURCE,"symbol":symbol,"content_hash":snapshot["content_hash"],"received_at":snapshot["received_at"],"source_market_timestamp":snapshot["source_market_timestamp"] or "","status":snapshot["status"] or "","trading_phase":snapshot["trading_phase"] or "","snapshot_json":json.dumps(snapshot,separators=(",",":"),default=str)}
                try: db.update_document(DB_ID,"orderbook_latest",doc_id,current)
                except Exception: db.create_document(DB_ID,"orderbook_latest",doc_id,current)
        except Exception: failed += 1
        time.sleep(0.5)
    batch_id=""; file_id=""; digest=""; compressed=uncompressed=0
    if changed_rows:
        batch_id=ID.unique(); raw="".join(json.dumps(row,separators=(",",":"),default=str)+"\n" for row in changed_rows).encode(); compressed_path=tempfile.mktemp(suffix=".jsonl.gz")
        with gzip.open(compressed_path,"wb") as handle: handle.write(raw)
        data=open(compressed_path,"rb").read(); digest=hashlib.sha256(data).hexdigest(); compressed=len(data); uncompressed=len(raw)
        upload=storage.create_file(BUCKET_ID,ID.unique(),InputFile.from_path(compressed_path),permissions=[])
        file_id=getattr(upload,"id",None) or upload["$id"]
        db.create_document(DB_ID,"orderbook_batches",batch_id,{"batch_id":batch_id,"source":SOURCE,"market_date":started.date().isoformat(),"start_time":started.isoformat(),"end_time":datetime.now(timezone.utc).isoformat(),"storage_file_id":file_id,"storage_path":f"orderbooks/{SOURCE}/{started:%Y/%m/%d/%H}/{batch_id}.jsonl.gz","sha256":digest,"compressed_bytes":compressed,"uncompressed_bytes":uncompressed,"snapshot_count":len(changed_rows),"schema_version":SCHEMA,"uploaded_at":datetime.now(timezone.utc).isoformat(),"status":"UPLOADED"})
    db.create_document(DB_ID,"orderbook_collector_runs",run_id,{"run_id":run_id,"source":SOURCE,"started_at":started.isoformat(),"finished_at":datetime.now(timezone.utc).isoformat(),"market_phase":phase,"attempted":attempted,"succeeded":succeeded,"changed":changed,"unchanged":unchanged,"failed":failed,"source_empty":empty,"latency_mean_ms":(sum(latencies)/len(latencies) if latencies else 0),"batch_id":batch_id,"status":"SUCCESS"})
    return context.res.json({"status":"SUCCESS","run_id":run_id,"attempted":attempted,"changed":changed,"unchanged":unchanged,"failed":failed,"batch_id":batch_id,"compressed_bytes":compressed})

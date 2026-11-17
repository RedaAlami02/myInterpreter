#!/usr/bin/env python3
"""Capture complete market/profile responses without Appwrite or backend writes.

Reuses the existing read-only enrichment adapter and its audited fiscal-year
calculation. It also retains ALL raw financial tables, stock metadata, annual
series, quarterly/interim tables and registry responses instead of keeping only
the latest calculated fields. Request headers and credentials are never saved.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time

from refetch_public_data import ROOT, adapter, save
from stage_supabase import sha256


def year_series(response):
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items()
            if re.fullmatch(r"\d{4}p?", str(key)) and isinstance(value, (int, float)) and not isinstance(value, bool)}


def make_profile(symbol, name, result, raw, captured_at):
    def table(key):
        item = raw.get("TABLE/" + key)
        return item.get("data") if isinstance(item, dict) else None
    computed = result.get("computed", {})
    holders = computed.get("shareholders")
    holders = json.loads(holders) if isinstance(holders, str) else None
    metrics = {"ca":"ca-corpo", "rnpg":"rnpg-corpo", "ebe":"ebe-corpo",
               "ebit":"ebit-corpo", "fcf":"fcf-corpo", "fp":"fp-corpo",
               "dn":"dn-corpo", "dpa":"dpa-corpo", "coursref":"coursref-corpo",
               "tn":"tn-corpo", "actif":"actif-corpo", "nmt":"nmt-corpo"}
    return {"symbol":symbol, "c_name":name, "captured_at":captured_at,
            "ext_name":result.get("ext_name"), "sector":result.get("sector"),
            "description":result.get("description"), "shareholders":holders,
            "computed":computed,
            "charts":{metric:year_series(raw.get("TABLE/"+key)) for metric,key in metrics.items()},
            "annual_statements":{metric:table(key) for metric,key in metrics.items()},
            "trim":table("trim-corpo"), "sem":table("sem-corpo"),
            "source_status":"available" if "error" not in result else "unmatched_symbol",
            "historical_baseline_overwritten":False}


def run(output):
    output = output.absolute()
    if output.parent != ROOT or not output.name.startswith("backup_live_"):
        raise ValueError("Use an ignored backup_live_* directory")
    output.mkdir(mode=0o700, exist_ok=True)
    baseline = ROOT / "backup_live_recovery_20261022/baseline"
    baseline_manifest = json.loads((baseline/"manifest.json").read_text())
    symbol_file = baseline/baseline_manifest["collections"]["format"]["file"]
    if sha256(symbol_file) != baseline_manifest["collections"]["format"]["sha256"]:
        raise ValueError("Symbol baseline changed")
    symbols = json.loads(symbol_file.read_text())
    manifest_path = output/"manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "status":"NONPERSONAL_CAPTURE_IN_PROGRESS", "started_at_utc":datetime.now(timezone.utc).isoformat(),
        "database_writes":False, "personal_data_included":False, "files":[], "profiles":[],
    }
    # Existing files are content-verified on resume; unchanged successful or
    # unavailable responses are not repeatedly fetched within this capture.
    for entry in manifest["files"]:
        path = output/entry["path"]
        if not path.resolve().is_relative_to(output.resolve()) or sha256(path) != entry["sha256"]:
            raise ValueError("Capture file changed")
    if not any(entry["path"] == "market_snapshot.json" for entry in manifest["files"]):
        market = adapter("getprice")
        stocks,index,status,tickers = market.fetch_all()
        if not index or not tickers:
            raise ValueError("Incomplete index/market response")
        save(output,"market_snapshot.json",{"stocks":stocks,"index":index,"market_status":status,
            "tickers":tickers,"retrieved_at_utc":datetime.now(timezone.utc).isoformat()},manifest)
    module = adapter("onboard_company")
    original_request = module._request
    registry = original_request("GET",module.SRC1+"/symblinks",what="registry")
    captures = {}
    lock = threading.Lock()
    def record_request(method,url,what,**kwargs):
        if method == "GET" and url.endswith("/symblinks"):
            value = registry
            key = "GET/registry"
        else:
            value = original_request(method,url,what,**kwargs)
            key = "TABLE/"+json.loads(kwargs["data"])["table"] if method == "POST" else "GET/"+url.rsplit("/",2)[-2]
        with lock:
            captures[key] = value
        return value
    module._request = record_request
    done = {row["symbol"] for row in manifest["profiles"]}
    for item in symbols:
        symbol,name = item["symbol"],item["name"]
        if not re.fullmatch(r"[A-Z0-9]{1,12}",symbol):
            raise ValueError("Unexpected symbol")
        if symbol in done:
            continue
        captures.clear()
        module.reset_failures()
        captured_at = datetime.now(timezone.utc).isoformat()
        result = module.fetch_symbol(symbol)
        profile = make_profile(symbol,name,result,captures,captured_at)
        failures = len(module.fetch_failures())
        save(output,"profiles/"+symbol+".json",{"profile":profile,"raw_responses":dict(captures),
            "fetch_failure_count":failures},manifest)
        manifest["profiles"].append({"symbol":symbol,"status":profile["source_status"],
            "raw_response_groups":len(captures),"fetch_failure_count":failures,
            "annual_series_with_values":sum(bool(series) for series in profile["charts"].values())})
        manifest_path.write_text(json.dumps(manifest,indent=2)+"\n")
        if len(manifest["profiles"]) % 10 == 0:
            print(json.dumps({"profiles_processed":len(manifest["profiles"]),"total":len(symbols)}),flush=True)
        time.sleep(0.1)
    manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["status"] = "NONPERSONAL_CAPTURE_COMPLETE_WITH_EXPLICIT_GAPS"
    manifest_path.write_text(json.dumps(manifest,indent=2)+"\n")
    report = {"profiles_attempted":len(manifest["profiles"]),
              "profiles_available":sum(r["status"]=="available" for r in manifest["profiles"]),
              "unmatched_symbols":sum(r["status"]=="unmatched_symbol" for r in manifest["profiles"]),
              "profiles_with_request_failures":sum(r["fetch_failure_count"]>0 for r in manifest["profiles"]),
              "complete_market_snapshot_saved":True,"database_writes":False,"personal_data_included":False}
    print(json.dumps(report),flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"backup_live_nonpersonal_20261024")
    args = parser.parse_args()
    try:
        run(args.output)
    except Exception as error:
        print(json.dumps({"ok":False,"error_category":type(error).__name__}),flush=True)
        raise SystemExit(1)

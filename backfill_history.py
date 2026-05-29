"""
Backfill historical price data for all companies from wafabourse VALEUR-GRAPH.

Usage:
    python3 backfill_history.py [--symbols SYM1,SYM2,...] [--skip-existing]

Fetches ~3 years of daily close prices for every company in the 'format'
collection and inserts them into the Appwrite 'data' collection.
Skips dates that already exist for each company.
"""

import json, sys, time, urllib.request, urllib.parse, argparse, math

# ── Appwrite ──────────────────────────────────────────────────────────────────
AW_ENDPOINT  = "https://fra.cloud.appwrite.io/v1"
AW_PROJECT   = "6a12447800077d5113ae"
AW_DB        = "myinterpreter"

# ── wafabourse ────────────────────────────────────────────────────────────────
WAFA_BASE    = "https://www.wafabourse.com"

# ─────────────────────────────────────────────────────────────────────────────

def aw_req(method, path, body=None, api_key=None):
    url = AW_ENDPOINT + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Appwrite-Project", AW_PROJECT)
    if api_key:
        req.add_header("X-Appwrite-Key", api_key)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def aw_list_all(path, api_key):
    """Paginate through all documents."""
    docs, offset, limit = [], 0, 500
    while True:
        q = [
            json.dumps({"method": "limit",  "values": [limit]}),
            json.dumps({"method": "offset", "values": [offset]}),
        ]
        qs = "&".join(f"queries[]={urllib.parse.quote(x)}" for x in q)
        res = aw_req("GET", f"{path}?{qs}", api_key=api_key)
        page = res.get("documents", [])
        docs.extend(page)
        if len(page) < limit:
            break
        offset += limit
    return docs

def get_symbol_map(api_key):
    """Returns {symbol: c_name} from 'format' collection."""
    docs = aw_list_all(f"/databases/{AW_DB}/collections/format/documents", api_key)
    return {d["symbol"]: d["name"] for d in docs}

def get_existing_dates(c_name, api_key):
    """Returns set of 'YYYY-MM-DD' already stored for this company."""
    dates, offset, limit = set(), 0, 500
    while True:
        q = [
            json.dumps({"method": "equal",  "attribute": "c_name", "values": [c_name]}),
            json.dumps({"method": "limit",  "values": [limit]}),
            json.dumps({"method": "offset", "values": [offset]}),
        ]
        qs = "&".join(f"queries[]={urllib.parse.quote(x)}" for x in q)
        res = aw_req("GET", f"/databases/{AW_DB}/collections/data/documents?{qs}", api_key=api_key)
        for doc in res.get("documents", []):
            day = (doc.get("date") or "")[:10]
            if day:
                dates.add(day)
        if len(res.get("documents", [])) < limit:
            break
        offset += limit
    return dates

# ── wafabourse session ────────────────────────────────────────────────────────

def wafa_session():
    """Get cookies + CSRF token from wafabourse homepage."""
    import http.cookiejar
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(
        WAFA_BASE + "/",
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36"}
    )
    with opener.open(req, timeout=15) as r:
        csrf = r.headers.get("x-csrf-token", "")
    return jar, csrf, opener

def wafa_token(jar, csrf, opener):
    """Get a fresh 60-second proxy token."""
    req = urllib.request.Request(
        WAFA_BASE + "/api/proxy/token",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
            "X-CSRF-Token": csrf,
            "Origin": WAFA_BASE,
            "Referer": WAFA_BASE + "/",
        }
    )
    with opener.open(req, timeout=10) as r:
        return json.loads(r.read())["token"]

def wafa_fetch(symbol, opener, token, csrf):
    """Fetch VALEUR-GRAPH history for a symbol. Returns list of {Seance, Cours}."""
    payload = json.dumps({
        "ACTIONS": [{
            "ACTION": {"NAME": "VALEUR-GRAPH", "TYPE": "SELECT", "VALUE": "VALEUR-GRAPH"},
            "PARAMS": [{"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol}]
        }]
    }).encode()
    req = urllib.request.Request(
        WAFA_BASE + "/api/proxy/data/JNNJ",
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": WAFA_BASE,
            "Referer": f"{WAFA_BASE}/instrument/actions/{symbol}",
            "X-CSRF-Token": csrf,
            "x-proxy-token": token,
        }
    )
    with opener.open(req, timeout=20) as r:
        data = json.loads(r.read())
    vg = data[0].get("VALEUR-GRAPH", {})
    if not vg.get("Valid"):
        return None
    return vg.get("Data", [])

# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("api_key", help="Appwrite server API key")
    parser.add_argument("--symbols", help="Comma-separated symbols to process (default: all)")
    parser.add_argument("--part", help="N/TOTAL — e.g. 3/8 to run chunk 3 of 8 (1-indexed)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip companies that already have >10 historical docs")
    args = parser.parse_args()

    api_key = args.api_key

    print("Loading symbol→name map from Appwrite...")
    sym_map = get_symbol_map(api_key)
    print(f"Found {len(sym_map)} companies.")

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    else:
        symbols = sorted(sym_map.keys())

    if args.part:
        n, total = map(int, args.part.split("/"))
        chunk = math.ceil(len(symbols) / total)
        symbols = symbols[(n - 1) * chunk : n * chunk]
        print(f"Part {n}/{total}: processing {len(symbols)} symbols")

    print("Establishing wafabourse session...")
    jar, csrf, opener = wafa_session()

    total_inserted = 0
    total_skipped  = 0
    failed = []

    for i, sym in enumerate(symbols):
        c_name = sym_map.get(sym)
        if not c_name:
            print(f"[{i+1}/{len(symbols)}] {sym}: not in format collection, skipping")
            continue

        print(f"\n[{i+1}/{len(symbols)}] {sym} ({c_name})")

        # Fetch existing dates
        existing = get_existing_dates(c_name, api_key)
        if args.skip_existing and len(existing) > 10:
            print(f"  Already has {len(existing)} docs, skipping.")
            continue

        # Get fresh token (they expire in 60s — get one per company)
        for attempt in range(3):
            try:
                token = wafa_token(jar, csrf, opener)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  Token fetch failed: {e}")
                    failed.append(sym)
                    break
                time.sleep(2)
        else:
            continue

        # Fetch history
        rows = None
        for attempt in range(3):
            try:
                rows = wafa_fetch(sym, opener, token, csrf)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  Fetch failed: {e}")
                    failed.append(sym)
                else:
                    time.sleep(2 ** attempt)
                    try:
                        token = wafa_token(jar, csrf, opener)
                    except Exception:
                        pass

        if rows is None:
            print(f"  No data returned (symbol may not exist on wafabourse)")
            continue

        print(f"  Got {len(rows)} rows from wafabourse, {len(existing)} already in Appwrite")

        inserted = skipped = 0
        for e in rows:
            parts = e["Seance"].split(" ")[0].split("/")
            iso_day  = f"{parts[2]}-{parts[1]}-{parts[0]}"
            iso_date = f"{iso_day}T15:30:00.000+00:00"

            if iso_day in existing:
                skipped += 1
                continue

            doc = {"date": iso_date, "c_name": c_name, "pa": float(e["Cours"])}
            for attempt in range(5):
                try:
                    aw_req("POST",
                           f"/databases/{AW_DB}/collections/data/documents",
                           body={"documentId": "unique()", "data": doc},
                           api_key=api_key)
                    inserted += 1
                    existing.add(iso_day)
                    break
                except Exception as err:
                    if attempt == 4:
                        print(f"    FAILED {iso_day}: {err}")
                    else:
                        time.sleep(2 ** attempt)

        print(f"  Inserted {inserted}, skipped {skipped}")
        total_inserted += inserted
        total_skipped  += skipped

        # Small pause between companies to avoid hammering either API
        time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Done. Total inserted: {total_inserted}, skipped: {total_skipped}")
    if failed:
        print(f"Failed symbols: {', '.join(failed)}")

if __name__ == "__main__":
    main()

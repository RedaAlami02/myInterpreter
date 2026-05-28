"""
Backfill MASI historical data from wafabourse export into Appwrite.

Usage:
    python3 backfill_masi.py masi.txt
"""

import json, sys, time, urllib.request, urllib.parse

API_ENDPOINT = "https://fra.cloud.appwrite.io/v1"
PROJECT_ID   = "6a12447800077d5113ae"
DB_ID        = "myinterpreter"
COL_ID       = "data"

def aw_req(method, path, body=None, api_key=None):
    url = API_ENDPOINT + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Appwrite-Project", PROJECT_ID)
    if api_key:
        req.add_header("X-Appwrite-Key", api_key)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def list_existing_dates(api_key):
    """Fetch all existing MASI doc dates."""
    dates = set()
    limit, offset = 500, 0
    while True:
        params = urllib.parse.urlencode({
            "queries[0]": json.dumps({"method": "equal", "attribute": "c_name", "values": ["MASI"]}),
            "queries[1]": json.dumps({"method": "limit", "values": [limit]}),
            "queries[2]": json.dumps({"method": "offset", "values": [offset]}),
        })
        res = aw_req("GET", f"/databases/{DB_ID}/collections/{COL_ID}/documents?{params}", api_key=api_key)
        for doc in res.get("documents", []):
            day = (doc.get("date") or "")[:10]
            if day:
                dates.add(day)
        if len(res.get("documents", [])) < limit:
            break
        offset += limit
    return dates

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "masi.txt"
    api_key = input("Appwrite API key: ").strip()

    raw = json.loads(open(src).read())
    entries = raw[0]["INDICE-GRAPH-HIST"]["Data"]
    print(f"Loaded {len(entries)} entries from {src}")

    print("Fetching existing MASI dates from Appwrite...")
    existing = list_existing_dates(api_key)
    print(f"Found {len(existing)} existing MASI dates, will skip them.")

    inserted = skipped = 0
    for e in entries:
        # Parse DD/MM/YYYY HH:MM:SS → YYYY-MM-DD
        parts = e["Seance"].split(" ")[0].split("/")
        iso_day  = f"{parts[2]}-{parts[1]}-{parts[0]}"
        iso_date = f"{iso_day}T15:30:00.000+00:00"  # end-of-day Casablanca

        if iso_day in existing:
            skipped += 1
            continue

        doc = {
            "date":   iso_date,
            "c_name": "MASI",
            "pa":     float(e["Cours"]),
        }

        for attempt in range(5):
            try:
                body = {"documentId": "unique()", "data": doc}
                aw_req("POST", f"/databases/{DB_ID}/collections/{COL_ID}/documents",
                       body=body, api_key=api_key)
                inserted += 1
                existing.add(iso_day)
                break
            except Exception as err:
                if attempt == 4:
                    print(f"  FAILED {iso_day}: {err}")
                else:
                    time.sleep(2 ** attempt)

        if (inserted + skipped) % 50 == 0:
            print(f"  {inserted} inserted, {skipped} skipped so far...")

    print(f"\nDone. Inserted {inserted}, skipped {skipped} (already existed).")

if __name__ == "__main__":
    main()

"""Order-book capture from the public Medias24 and CDG endpoints.

Medias24 is the primary source (ten bid and ten ask levels over plain HTTPS);
CDG Capital is the fallback for symbols Medias24 does not serve or fails on.
Nothing here writes to a database: the module produces the snapshot artifact
that `tools/publish_exchange_orderbooks.py` sends to the service-role RPC.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, time as clock_time, timezone
from zoneinfo import ZoneInfo

MEDIAS24_API = "https://medias24.com/content/api"
MEDIAS24_REFERER = "https://medias24.com/leboursier/fiche-action"
CDG_API = "https://www.cdgcapitalbourse.ma/api/"
USER_AGENT = "myInterpreter-orderbook-capture/1.0 (+https://myinterpreter.infinityfree.me)"

CASABLANCA = ZoneInfo("Africa/Casablanca")
SESSION_OPEN = clock_time(8, 50)
SESSION_CLOSE = clock_time(15, 40)
MAX_LEVELS = 10


def casablanca_now(moment: datetime | None = None) -> datetime:
    value = moment or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(CASABLANCA)


def session_open(moment: datetime | None = None) -> bool:
    local = casablanca_now(moment)
    return local.weekday() < 5 and SESSION_OPEN <= local.time() <= SESSION_CLOSE


def utc_stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def number(value):
    if value in (None, "", "-", "--"):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).replace(" ", " ").replace(" ", "").replace(",", ".")
    try:
        parsed = float(text)
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def clean_levels(rows, side, limit=MAX_LEVELS):
    """Sort, deduplicate and bound one side of the book.

    Invalid or zero-priced rows are dropped rather than repaired: a level the
    source cannot price is not a level we may publish.
    """
    levels = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        price = number(row.get("price"))
        quantity = number(row.get("quantity"))
        if price is None or price <= 0 or price >= 1_000_000_000:
            continue
        if quantity is None or quantity < 0:
            continue
        if price in seen:
            continue
        seen.add(price)
        orders = number(row.get("orders"))
        levels.append({"price": price, "quantity": quantity,
                       "orders": orders if isinstance(orders, int) or isinstance(orders, float) else None})
    reverse = side == "bids"
    levels.sort(key=lambda level: level["price"], reverse=reverse)
    return levels[:limit]


def book_row(symbol, source, bids, asks, captured_at, market_time=None, status=None, phase=None):
    clean_bids = clean_levels(bids, "bids")
    clean_asks = clean_levels(asks, "asks")
    if not clean_bids and not clean_asks:
        return None
    return {
        "symbol": symbol.upper(),
        "source": source,
        "captured_at": utc_stamp(captured_at),
        "market_time": market_time,
        "status": status,
        "phase": phase,
        "bids": clean_bids,
        "asks": clean_asks,
    }


def medias24_universe(fetch_json):
    """ISIN -> row for every instrument Medias24 currently lists."""
    payload = fetch_json(f"{MEDIAS24_API}?method=getAllStocks&format=json&t="
                         + datetime.now(timezone.utc).strftime("%Y-%m-%d-%H:%M"))
    rows = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("MEDIAS24_UNIVERSE_INVALID")
    value = {}
    for row in rows:
        isin = row.get("ISIN")
        if isinstance(isin, str) and isin:
            value[isin] = row
    return value


def medias24_book(fetch_json, isin):
    payload = fetch_json(f"{MEDIAS24_API}?method=getBidAsk&ISIN={isin}&format=json&t="
                         + datetime.now(timezone.utc).strftime("%Y-%m-%d-%H:%M"))
    result = payload.get("result") if isinstance(payload, dict) else None
    rows = result.get("orderBook") if isinstance(result, dict) else result
    if not isinstance(rows, list):
        raise RuntimeError("MEDIAS24_BOOK_INVALID")
    bids = [{"price": row.get("bidValue"), "quantity": row.get("bidQte"),
             "orders": row.get("bidOrder")} for row in rows if isinstance(row, dict)]
    asks = [{"price": row.get("askValue"), "quantity": row.get("askQte"),
             "orders": row.get("askOrder")} for row in rows if isinstance(row, dict)]
    return bids, asks


def cdg_depth(posts, symbol, levels=MAX_LEVELS):
    action = {"ACTION": {"NAME": "VALEUR-PROFONDEUR", "TYPE": "SELECT", "VALUE": "VALEUR-PROFONDEUR"},
              "PARAMS": [{"NAME": "Lang_", "TYPE": "S", "VALUE": "FR"},
                         {"NAME": "Espace_", "TYPE": "I", "VALUE": "1"},
                         {"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol.upper()},
                         {"NAME": "NumSeq_", "TYPE": "I", "VALUE": "0"},
                         {"NAME": "Top_", "TYPE": "I", "VALUE": str(levels)}]}
    payload = posts({"ACTIONS": [action]})
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("CDG_BOOK_INVALID")
    envelope = payload[0].get("VALEUR-PROFONDEUR") or {}
    if not envelope.get("Valid"):
        raise RuntimeError("CDG_BOOK_REJECTED")
    rows = envelope.get("Data") or []
    bids = [{"price": row.get("Achat"), "quantity": row.get("QteAchat"),
             "orders": row.get("NbrAchat")} for row in rows]
    asks = [{"price": row.get("Vente"), "quantity": row.get("QteVente"),
             "orders": row.get("NbrVente")} for row in rows]
    return bids, asks


def http_json(url, *, data=None, headers=None, timeout=25, attempts=3):
    # Medias24 sits behind a CDN that rejects datacenter clients unless the
    # request carries the same browser fingerprint the public page sends.
    if "medias24.com" in url:
        request_headers = {
            "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
            "Referer": MEDIAS24_REFERER,
            "Origin": "https://medias24.com",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }
    else:
        request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"}
    request_headers.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data, separators=(",", ":")).encode()
        request_headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(attempts):
        request = urllib.request.Request(url, data=body, headers=request_headers,
                                         method="POST" if body else "GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last = error
        if attempt < attempts - 1:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"HTTP_FAILED {url.split('?')[0]}: {last}")


def fetch_json(url, **kwargs):
    return http_json(url, **kwargs)


def post_json(url, data, **kwargs):
    return http_json(url, data=data, **kwargs)


def cdg_poster(poster):
    return lambda payload: poster(CDG_API, payload)


def capture(symbols, identities, *, fetch_json_fn, cdg_post, moment=None,
            levels=MAX_LEVELS, pause=0.0):
    """Build one snapshot: Medias24 first, CDG only for what it cannot serve."""
    captured_at = moment or datetime.now(timezone.utc)
    universe = {}
    universe_error = None
    try:
        universe = medias24_universe(fetch_json_fn)
    except Exception as error:  # the fallback source still covers every symbol
        universe_error = f"{type(error).__name__}: {error}"
    rows = []
    report = {"medias24": 0, "cdg": 0, "empty": 0, "failed": 0,
              "unmapped_isin": 0, "universe_error": universe_error, "failures": [],
              "empty_symbols": []}
    for symbol in symbols:
        symbol = symbol.upper()
        isin = (identities or {}).get(symbol)
        row = None
        if isin and isin in universe:
            try:
                bids, asks = medias24_book(fetch_json_fn, isin)
                row = book_row(symbol, "MEDIAS24_PUBLIC", bids, asks, captured_at,
                               market_time=(universe[isin] or {}).get("datetime"),
                               status=None, phase=None)
            except Exception:
                row = None
        if row is None and isin and isin not in universe and universe:
            report["unmapped_isin"] += 1
        if row is None:
            try:
                bids, asks = cdg_depth(cdg_post, symbol, levels=levels)
                row = book_row(symbol, "CDG_DELAYED", bids, asks, captured_at)
            except Exception as error:
                report["failed"] += 1
                report["failures"].append({"symbol": symbol,
                                           "error": f"{type(error).__name__}: {error}"[:200]})
                continue
        if row is None:
            report["empty"] += 1
            report["empty_symbols"].append(symbol)
            continue
        report["medias24" if row["source"] == "MEDIAS24_PUBLIC" else "cdg"] += 1
        rows.append(row)
        if pause:
            time.sleep(pause)
    return rows, report

"""Deterministic cloud benchmark primitives, aligned with bourse_data tooling."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, time as day_time, timezone
from zoneinfo import ZoneInfo

CASABLANCA = ZoneInfo("Africa/Casablanca")
MIN_EVENTS = 20
DEPTHS = (1, 5, 10)


def canonical_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def book_hash(book, levels):
    return canonical_hash([
        [[item.get("price"), item.get("quantity"), item.get("order_count")] for item in (book.get(side) or [])[:levels]]
        for side in ("bids", "asks")
    ])


def market_phase(iso_value):
    dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00")).astimezone(CASABLANCA)
    if dt.weekday() >= 5:
        return "UNKNOWN"
    value = dt.timetz().replace(tzinfo=None)
    if day_time(9, 30) <= value <= day_time(15, 20):
        return "CONTINUOUS"
    if day_time(9, 0) <= value < day_time(9, 30):
        return "OPENING_AUCTION"
    if day_time(15, 20) < value <= day_time(15, 30):
        return "CLOSING"
    return "OUTSIDE_CONTINUOUS"


def transaction_key(trade):
    def first(*keys):
        for key in keys:
            if trade.get(key) not in (None, ""):
                return trade[key]
        return None
    payload = {
        "time": first("time", "heure", "Heure", "trade_time", "DateTransaction", "DateCours"),
        "price": first("price", "prix", "Prix", "Cours", "Price"),
        "quantity": first("quantity", "qte", "Qte", "quantite", "Quantite", "Quantité", "NbrTitre"),
        "value": first("value_mad", "total", "Total", "valeur", "Valeur", "Volume", "Value"),
        "sequence": first("sequence", "seq", "NumSeq", "IdTransaction", "NumTransaction", "id"),
    }
    if payload["time"] is None or payload["price"] is None or payload["quantity"] is None:
        return None
    return canonical_hash(payload), payload


def _iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def event_inventory(rows):
    """Build transition events with (last absent, first present] observation windows."""
    grouped = defaultdict(list)
    for row in rows:
        if row.get("operation") == "quote" and not row.get("error") and row.get("phase") == "CONTINUOUS":
            grouped[(row["source"], row["symbol"])].append(row)
    events = []
    for (source, symbol), observations in grouped.items():
        observations.sort(key=lambda item: item["request_finished_at_utc"])
        prior_books = {}
        prior_quote = None
        prior_trades = set()
        seen_trades = set()
        prior_time = None
        for row in observations:
            book = row.get("book") or {}
            for depth in DEPTHS:
                fingerprint = book_hash(book, depth)
                key = ("BOOK", "TOP%d" % depth)
                previous = prior_books.get(key)
                if previous is not None and previous[0] != fingerprint:
                    events.append(_event(source, symbol, "BOOK", key[1], fingerprint, previous[0], previous[1], row))
                prior_books[key] = (fingerprint, row["request_finished_at_utc"])
            state = {key: row.get(key) for key in ("last_price", "best_bid", "best_bid_qty", "best_bid_orders", "best_ask", "best_ask_qty", "best_ask_orders", "daily_quantity")}
            if any(value is not None for value in state.values()):
                fingerprint = canonical_hash(state)
                if prior_quote is not None and prior_quote[0] != fingerprint:
                    events.append(_event(source, symbol, "QUOTE", "QUOTE_STATE", fingerprint, prior_quote[0], prior_quote[1], row))
                prior_quote = (fingerprint, row["request_finished_at_utc"])
            current = {}
            for trade in row.get("transactions") or []:
                if isinstance(trade, dict):
                    pair = transaction_key(trade)
                    if pair:
                        current[pair[0]] = pair[1]
            for fingerprint, trade in current.items():
                if prior_time is not None and fingerprint not in prior_trades and fingerprint not in seen_trades:
                    events.append(_event(source, symbol, "TRADE", "", fingerprint, None, prior_time, row, trade))
                    seen_trades.add(fingerprint)
            prior_trades = set(current)
            prior_time = row["request_finished_at_utc"]
    return events


def _event(source, symbol, kind, scope, fingerprint, previous_hash, previous_absent, row, trade=None):
    return {"source": source, "symbol": symbol, "event_type": kind, "scope": scope,
            "fingerprint": fingerprint, "previous_hash": previous_hash,
            "new_hash": fingerprint if kind == "BOOK" else None,
            "first_seen_cycle": row["cycle_id"], "first_seen_at": row["received_at_utc"],
            "previous_absent_at": previous_absent, "request_started_at": row["request_started_at_utc"],
            "request_finished_at": row["request_finished_at_utc"], "source_position": row.get("source_position"),
            "trade": trade}


def match_events(events):
    left = [event for event in events if event["source"] == "MEDIAS24_PUBLIC"]
    right = [event for event in events if event["source"] == "CDG_DELAYED"]
    output = []
    used = set()
    for first in sorted(left, key=lambda value: value["first_seen_at"]):
        candidates = [(index, event) for index, event in enumerate(right)
                      if index not in used and event["symbol"] == first["symbol"]
                      and event["event_type"] == first["event_type"] and event["scope"] == first["scope"]
                      and event["fingerprint"] == first["fingerprint"]
                      and (first.get("previous_hash") is None or event.get("previous_hash") == first.get("previous_hash"))]
        if not candidates:
            continue
        index, second = min(candidates, key=lambda pair: abs((_iso(pair[1]["first_seen_at"]) - _iso(first["first_seen_at"])).total_seconds()))
        used.add(index)
        low = high = None
        if first.get("previous_absent_at") and second.get("previous_absent_at"):
            low = (_iso(second["previous_absent_at"]) - _iso(first["first_seen_at"])).total_seconds()
            high = (_iso(second["first_seen_at"]) - _iso(first["previous_absent_at"])).total_seconds()
        if low is not None and low > 0:
            direction = "M24_FIRST"
        elif high is not None and high < 0:
            direction = "CDG_FIRST"
        elif first["first_seen_cycle"] == second["first_seen_cycle"]:
            direction = "SAME_POLL_WINDOW"
        else:
            direction = "AMBIGUOUS"
        output.append({"symbol": first["symbol"], "event_type": first["event_type"], "scope": first["scope"],
                       "fingerprint": first["fingerprint"], "m24_previous_hash": first.get("previous_hash"),
                       "cdg_previous_hash": second.get("previous_hash"), "m24_first_seen_at": first["first_seen_at"],
                       "cdg_first_seen_at": second["first_seen_at"], "m24_previous_absent_at": first.get("previous_absent_at"),
                       "cdg_previous_absent_at": second.get("previous_absent_at"),
                       "observed_first_seen_difference_seconds": (_iso(second["first_seen_at"]) - _iso(first["first_seen_at"])).total_seconds(),
                       "lag_lower_bound_sec": low, "lag_upper_bound_sec": high, "direction": direction,
                       "m24_source_position": first.get("source_position"), "cdg_source_position": second.get("source_position"),
                       "m24_trade": first.get("trade"), "cdg_trade": second.get("trade"),
                       "match_method": "one_to_one_transition_context_interval_censored"})
    return output


def percentile(values, probability):
    ordered = sorted(values)
    return ordered[max(0, int(math.ceil(probability * len(ordered))) - 1)] if ordered else None


def summaries(events, matches):
    groups = defaultdict(list)
    for item in matches:
        groups[(item["event_type"], item["scope"])].append(item)
    keys = [("BOOK", "TOP%d" % depth) for depth in DEPTHS] + [("TRADE", ""), ("QUOTE", "QUOTE_STATE")]
    result = []
    for kind, scope in keys:
        rows = groups[(kind, scope)]
        directional = [row for row in rows if row["direction"] in ("M24_FIRST", "CDG_FIRST")]
        vals = [row["observed_first_seen_difference_seconds"] for row in directional]
        enough = len(directional) >= MIN_EVENTS
        result.append({"pair": "M24_CDG", "event_type": kind, "scope": scope,
                       "matched_events": len(rows), "unambiguous_events": len(directional),
                       "unmatched_events": max(0, sum(e["event_type"] == kind and e["scope"] == scope for e in events) - 2 * len(rows)),
                       "m24_first": sum(row["direction"] == "M24_FIRST" for row in rows),
                       "cdg_first": sum(row["direction"] == "CDG_FIRST" for row in rows),
                       "same_poll_window": sum(row["direction"] == "SAME_POLL_WINDOW" for row in rows),
                       "ambiguous": sum(row["direction"] == "AMBIGUOUS" for row in rows),
                       "median_observed_first_seen_difference_seconds": statistics.median(vals) if enough else None,
                       "p90_observed_first_seen_difference_seconds": percentile(vals, .9) if enough else None,
                       "statistics_status": "REVIEW_REQUIRED" if enough else "INSUFFICIENT_EVIDENCE",
                       "freshness_classification": "UNKNOWN"})
    return result


def network_stats(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row.get("source", "UNKNOWN")].append(row)
    output = []
    for source, group in sorted(groups.items()):
        good = [float(row["transport_duration_ms"]) for row in group if not row.get("error") and row.get("transport_duration_ms") is not None]
        errors = [str(row.get("error") or "") for row in group]
        component_errors = [str(item.get("error") or "") for row in group for item in row.get("provider_errors", [])]
        all_errors = errors + component_errors
        output.append({"source": source, "attempts": len(group), "successes": len(good),
                       "success_rate": len(good) / float(len(group)) if group else None,
                       "median_adapter_call_duration_ms": statistics.median(good) if good else None,
                       "p90_adapter_call_duration_ms": percentile(good, .9),
                       "http_429": sum("429" in value for value in all_errors),
                       "http_5xx": sum(any(str(code) in value for code in range(500, 600)) for value in all_errors),
                       "timeouts_or_dns": sum(any(term in value.lower() for term in ("timeout", "dns", "gaierror")) for value in all_errors),
                       "other_errors": sum(bool(value) and not any(term in value.lower() for term in ("429", "timeout", "dns", "gaierror")) and not any(str(code) in value for code in range(500, 600)) for value in all_errors),
                       "metric_type": "NETWORK_ADAPTER_CALL_DURATION_NOT_FEED_LATENCY"})
    return output

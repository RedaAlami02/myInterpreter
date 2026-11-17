"""Isolated no-write egress probe for the public CDG endpoint."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import ssl
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests


CDG_API_URL = os.environ.get("CDG_API_URL", "https://www.cdgcapitalbourse.ma/api/")
TIMEOUT_SECONDS = float(os.environ.get("CDG_PROBE_TIMEOUT_SECONDS", "15"))


def _shape(value):
    if isinstance(value, dict):
        return {str(key): _shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def safe_probe(url: str = CDG_API_URL, timeout: float = TIMEOUT_SECONDS) -> dict:
    """Return safe connectivity diagnostics; never store/log the market body."""
    parsed = urlparse(url)
    host = parsed.hostname
    result = {"timestamp": datetime.now(timezone.utc).isoformat(), "host": host,
              "dns": "NOT_ATTEMPTED", "tls": "NOT_ATTEMPTED", "http_status": None,
              "latency_ms": None, "response_bytes": None, "schema_hash": None,
              "parse_success": False, "error_category": None}
    if not host:
        result["error_category"] = "INVALID_URL"
        return result
    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        result["dns"] = "SUCCESS" if addresses else "EMPTY"
    except socket.gaierror:
        result.update(dns="FAILED", error_category="DNS_FAILURE")
        return result
    try:
        raw = socket.create_connection((host, parsed.port or 443), timeout=timeout)
        with ssl.create_default_context().wrap_socket(raw, server_hostname=host):
            result["tls"] = "SUCCESS"
    except (OSError, ssl.SSLError):
        result.update(tls="FAILED", error_category="TLS_FAILURE")
        return result
    payload = {"ACTIONS": [{"ACTION": {"NAME": "TICKER", "TYPE": "SELECT", "VALUE": "TICKER"}, "PARAMS": [
        {"NAME": "Espace_", "TYPE": "I", "VALUE": "1"},
        {"NAME": "IdPartener_", "TYPE": "I", "VALUE": "1"},
        {"NAME": "Lang_", "TYPE": "S", "VALUE": "XX"},
        {"NAME": "NumseqMin_", "TYPE": "I", "VALUE": "0"},
        {"NAME": "NumseqMax_", "TYPE": "I", "VALUE": "0"}]}]}
    try:
        started = time.perf_counter()
        response = requests.post(url, json=payload, timeout=timeout,
                                 headers={"User-Agent": "myinterpreter-cdg-probe/1.0"})
        body = response.content
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        result["http_status"] = response.status_code
        result["response_bytes"] = len(body)
        parsed_payload = response.json()
        result["schema_hash"] = hashlib.sha256(json.dumps(_shape(parsed_payload), sort_keys=True).encode()).hexdigest()
        result["parse_success"] = isinstance(parsed_payload, list)
        if not response.ok:
            result["error_category"] = "HTTP_ERROR"
        elif not result["parse_success"]:
            result["error_category"] = "SCHEMA_UNEXPECTED"
    except requests.Timeout:
        result["error_category"] = "HTTP_TIMEOUT"
    except requests.RequestException:
        result["error_category"] = "HTTP_FAILURE"
    except ValueError:
        result["error_category"] = "JSON_PARSE_FAILURE"
    return result


def main(context):
    result = safe_probe()
    context.log("CDG probe completed: " + json.dumps(result, sort_keys=True))
    return context.res.json(result, 200 if result["error_category"] is None else 502)

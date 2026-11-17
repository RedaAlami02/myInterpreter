"""Inert egress probe: can an Appwrite function reach a public HTTPS host?

Reachability from a developer's laptop says nothing about reachability from the
runtime that would actually do the collecting. Appwrite runs functions in its own
container with its own egress rules, so the only honest way to answer "can this
host be collected from the cloud?" is to ask from there.

This function therefore:

* writes nothing — no collections, no buckets, no documents;
* stores no response body, only its length and digest;
* has no schedule and no execute permission, so it runs only when invoked
  deliberately;
* receives its targets in the request body, so no host appears in this file.

Targets are validated first: HTTPS only, and a host that resolves to a private,
loopback or link-local address is refused rather than fetched.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import ssl
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests


# One target per invocation is the intended use: a function run has a
# 60-second ceiling, and a hanging host would otherwise consume the budget
# of every target after it.
MAX_TARGETS = 3
TIMEOUT_SECONDS = 12
USER_AGENT = "myinterpreter-egress-probe/1.0"


def _is_public(host: str) -> tuple[bool, str]:
    """Refuse anything that is not a public address."""
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False, "DNS_FAILURE"
    if not addresses:
        return False, "DNS_EMPTY"
    for entry in addresses:
        try:
            address = ipaddress.ip_address(entry[4][0])
        except ValueError:
            return False, "UNPARSEABLE_ADDRESS"
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast):
            return False, "NON_PUBLIC_ADDRESS"
    return True, "PUBLIC"


def probe(url: str) -> dict:
    result = {"url_sha256": hashlib.sha256(url.encode()).hexdigest(),
              "host": urlparse(url).hostname or "",
              "checked_at": datetime.now(timezone.utc).isoformat(),
              "dns": "NOT_ATTEMPTED", "tls": "NOT_ATTEMPTED", "http_status": None,
              "response_bytes": None, "body_sha256": None, "latency_ms": None,
              "looks_like_html": None, "outcome": None}
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        result["outcome"] = "REJECTED_NOT_HTTPS"
        return result
    public, verdict = _is_public(parsed.hostname)
    result["dns"] = "SUCCESS" if public else "FAILED"
    if not public:
        result["outcome"] = verdict
        return result
    try:
        raw = socket.create_connection((parsed.hostname, 443), timeout=TIMEOUT_SECONDS)
        with ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname):
            result["tls"] = "SUCCESS"
    except (OSError, ssl.SSLError) as exc:
        result["tls"] = "FAILED"
        result["outcome"] = f"TLS_FAILURE:{type(exc).__name__}"
        return result
    started = time.perf_counter()
    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS,
                                headers={"User-Agent": USER_AGENT})
    except requests.Timeout:
        result["outcome"] = "HTTP_TIMEOUT"
        return result
    except requests.RequestException as exc:
        result["outcome"] = f"HTTP_FAILURE:{type(exc).__name__}"
        return result
    body = response.content
    result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    result["http_status"] = response.status_code
    result["response_bytes"] = len(body)
    result["body_sha256"] = hashlib.sha256(body).hexdigest()
    result["looks_like_html"] = b"<html" in body[:2000].lower()
    result["outcome"] = "OK" if response.ok else "HTTP_ERROR"
    return result


def main(context):
    try:
        payload = context.req.body if isinstance(context.req.body, dict) else json.loads(
            context.req.body or "{}")
    except Exception:
        payload = {}
    targets = payload.get("targets") or []
    if not isinstance(targets, list) or not targets:
        return context.res.json({"error": "expected {\"targets\": [\"https://...\"]}"}, 400)
    if len(targets) > MAX_TARGETS:
        return context.res.json({"error": f"at most {MAX_TARGETS} targets"}, 400)
    results = [probe(str(target)) for target in targets]
    context.log("egress probe outcomes: " + json.dumps([r["outcome"] for r in results]))
    return context.res.json({"probes": results}, 200)

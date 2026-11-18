#!/usr/bin/env python3
"""Capture the Bourse de Casablanca instrument universe and detail pages.

Portable cloud/CI capture: standard library only. If the exchange serves an
incomplete TLS chain, the tool fetches the issuer's intermediate from the leaf
certificate's AIA URL, verifies it against the system roots, and builds a local
bundle. Verification is never disabled.

Raw pages are untrusted data: they are written to the output directory and only
parsed as JSON/HTML. No page script is executed.
"""
import argparse
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "myInterpreter-exchange-reconciliation/1.0 (+https://myinterpreter.infinityfree.me)"
DEFAULT_ACTIONS = "https://www.casablanca-bourse.com/live-market/actions"
DEFAULT_INDICES = "https://www.casablanca-bourse.com/live-market/indices"
CDG_API = "https://www.cdgcapitalbourse.ma/api/"
SETTINGS_RE = re.compile(
    r'<script type="application/json" data-drupal-selector="drupal-settings-json">(.*?)</script>',
    re.S,
)
AIA_RE = re.compile(r"CA Issuers - URI:(\S+)")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


def request(url, context, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    opener = urllib.request.build_opener(
        NoRedirect, urllib.request.HTTPSHandler(context=context))
    for attempt in range(3):
        try:
            with opener.open(req, timeout=timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise
        except urllib.error.URLError as error:
            if isinstance(error.reason, (TimeoutError, ConnectionError)) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise


def _run(args, input_bytes=None):
    return subprocess.run(args, input=input_bytes, capture_output=True, timeout=30)


def _system_ca():
    paths = ssl.get_default_verify_paths()
    for path in (paths.cafile, "/etc/ssl/certs/ca-certificates.crt"):
        if path and os.path.exists(path):
            return path
    raise RuntimeError("No system CA bundle found")


def complete_chain(host, out_dir):
    """Return a verified local CA bundle for a host with an incomplete chain."""
    tls = Path(out_dir) / ".tls"
    tls.mkdir(parents=True, exist_ok=True)
    probe = _run(["openssl", "s_client", "-connect", f"{host}:443",
                  "-servername", host, "-showcerts"], input_bytes=b"")
    if probe.returncode != 0:
        raise RuntimeError("TLS probe failed")
    blocks = re.findall(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                        probe.stdout, re.S)
    if not blocks:
        raise RuntimeError("No certificate returned")
    leaf = tls / "leaf.pem"
    leaf.write_bytes(blocks[0] + b"\n")
    info = _run(["openssl", "x509", "-in", str(leaf), "-noout", "-text"])
    match = AIA_RE.search(info.stdout.decode("utf-8", "replace"))
    if not match:
        raise RuntimeError("No CA Issuers AIA URL in the leaf certificate")
    issuer_url = match.group(1)
    _, issuer = request(issuer_url, None)
    intermediate = tls / "intermediate.der"
    intermediate.write_bytes(issuer)
    pem = _run(["openssl", "x509", "-inform", "DER", "-in", str(intermediate),
                "-out", str(tls / "intermediate.pem")])
    if pem.returncode != 0:
        raise RuntimeError("Intermediate certificate is not valid DER")
    verify = _run(["openssl", "verify", "-CAfile", _system_ca(),
                   "-untrusted", str(tls / "intermediate.pem"), str(leaf)])
    if verify.returncode != 0 or b": OK" not in verify.stdout:
        raise RuntimeError("Intermediate does not verify against system roots")
    bundle = tls / "bundle.pem"
    bundle.write_bytes(Path(_system_ca()).read_bytes() + b"\n" + (tls / "intermediate.pem").read_bytes())
    return str(bundle)


def context_for(bundle):
    if bundle:
        return ssl.create_default_context(cafile=bundle)
    return ssl.create_default_context()


def fetch(url, out_dir, bundle=None):
    try:
        return request(url, context_for(bundle))
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        if bundle:
            raise
        host = urllib.parse.urlsplit(url).hostname
        completed = complete_chain(host, out_dir)
        return request(url, context_for(completed))
    except ssl.SSLCertVerificationError:
        if bundle:
            raise
        host = urllib.parse.urlsplit(url).hostname
        completed = complete_chain(host, out_dir)
        return request(url, context_for(completed))


def settings(html):
    match = SETTINGS_RE.search(html)
    if not match:
        raise ValueError("SETTINGS_NOT_FOUND")
    return json.loads(match.group(1))


def actions(html):
    data = settings(html).get("live_market") or {}
    rows = data.get("actions")
    if not isinstance(rows, list):
        raise ValueError("ACTIONS_NOT_FOUND")
    return rows


def _positive(value):
    try:
        return float(str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")) > 0
    except (TypeError, ValueError):
        return False


def instrument(html, status, sha):
    data = (settings(html).get("live_market") or {}).get("action_data") or {}
    inst = data.get("instrument_details") or {}
    fin = data.get("financials_details") or {}
    return {
        "symbol": data.get("symbol"),
        "ce": data.get("ce"),
        "company": (data.get("emetteur") or {}).get("fr"),
        "sector": (data.get("secteur") or {}).get("fr"),
        "isin": inst.get("isin"),
        "shares": inst.get("shares_count"),
        "nominal": inst.get("nominal_value"),
        "price": data.get("dernierCours"),
        "cap": data.get("capitalisation"),
        "annual_rows": fin.get("chiffres") or [],
        "ratios": fin.get("ratios") or [],
        "capital_actions": data.get("capital_increase_details") or [],
        "dividends": data.get("dividend_details") or [],
        "http_status": status,
        "page_sha256": sha,
        # A suspended or untraded instrument still shows its last price; the
        # publisher must not restamp it as today's quote.
        "traded": _positive(data.get("quantite")) or _positive(data.get("nbTransactions")),
    }


def session_probe(symbol="ADH"):
    """The exchange's own last-trade date (CDG VALEUR-SYNTHESE).

    The public pages keep the previous session's aggregates when the market is
    closed, so quantity alone cannot prove that a session happened today.
    """
    action = {"ACTION": {"NAME": "VALEUR-SYNTHESE", "TYPE": "SELECT", "VALUE": "VALEUR-SYNTHESE"},
              "PARAMS": [{"NAME": "Lang_", "TYPE": "S", "VALUE": "FR"},
                         {"NAME": "Espace_", "TYPE": "I", "VALUE": "1"},
                         {"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol}]}
    request = urllib.request.Request(
        CDG_API, data=json.dumps({"ACTIONS": [action]}).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "myInterpreter-capture/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    row = ((payload[0].get("VALEUR-SYNTHESE") or {}).get("Data") or [{}])[0]
    stamp = str(row.get("DateCours") or "")[:10]
    try:
        day = datetime.strptime(stamp, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None
    return {"trading_day": day, "phase": row.get("Phase"), "symbol": symbol,
            "probed_at": datetime.now(timezone.utc).isoformat()}


def summary(records):
    ok = [r for r in records if not r.get("error")]
    years = {}
    without = 0
    for row in ok:
        latest = max((r.get("exercice") for r in row.get("annual_rows") or []
                      if isinstance(r.get("exercice"), int)), default=None)
        if latest is None:
            without += 1
        else:
            years[latest] = years.get(latest, 0) + 1
    return {
        "requested": len(records),
        "ok": len(ok),
        "errors": len(records) - len(ok),
        "with_annual_rows": sum(1 for row in ok if row.get("annual_rows")),
        "without_annual_rows": without,
        "latest_year_counts": dict(sorted((str(k), v) for k, v in years.items())),
        "with_capital_actions": sum(1 for row in ok if row.get("capital_actions")),
        "with_dividends": sum(1 for row in ok if row.get("dividends")),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--actions-url", default=DEFAULT_ACTIONS)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--ca-bundle")
    args = parser.parse_args()
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        print(json.dumps({"status": "FAILED", "code": "OUTPUT_DIRECTORY_NOT_EMPTY"}))
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    pages = args.out_dir / "pages"
    pages.mkdir(exist_ok=True)
    bundle = args.ca_bundle
    try:
        status, body = fetch(args.actions_url, args.out_dir, bundle)
        (args.out_dir / "actions.html").write_bytes(body)
        universe = actions(body.decode("utf-8", "replace"))
        (args.out_dir / "actions.json").write_text(
            json.dumps(universe, ensure_ascii=False, indent=1), encoding="utf-8")
        # Index closes ride along so the MASI chart has a daily point.
        try:
            _, index_body = fetch(DEFAULT_INDICES, args.out_dir, bundle)
            index_rows = (settings(index_body.decode("utf-8", "replace"))
                          .get("live_market") or {}).get("indices") or {}
            (args.out_dir / "indices.json").write_text(
                json.dumps(index_rows.get("all") or [], ensure_ascii=False, indent=1),
                encoding="utf-8")
        except Exception as error:
            (args.out_dir / "indices.json").write_text("[]", encoding="utf-8")
            print("indices capture failed", type(error).__name__, file=sys.stderr)
        try:
            probed = session_probe()
        except Exception as error:
            probed = None
            print("session probe failed", type(error).__name__, file=sys.stderr)
        (args.out_dir / "session.json").write_text(
            json.dumps(probed or {}, ensure_ascii=False, indent=1), encoding="utf-8")
        wanted = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}
        records = []
        for index, row in enumerate(universe, 1):
            symbol = str(row.get("symbol") or "").strip()
            ce = row.get("ce")
            if wanted and symbol.upper() not in wanted:
                continue
            if not symbol or not isinstance(ce, str) or not ce:
                records.append({"symbol": symbol, "ce": ce, "error": "INVALID_IDENTITY"})
                continue
            url = (f"https://www.casablanca-bourse.com/live-market/actions/cours"
                   f"?symbol={urllib.parse.quote(symbol)}&ce={urllib.parse.quote(ce)}")
            try:
                page_status, page = fetch(url, args.out_dir, bundle)
                (pages / f"{symbol}.html").write_bytes(page)
                digest = hashlib.sha256(page).hexdigest()
                record = instrument(page.decode("utf-8", "replace"), page_status, digest)
                record["fetched_at"] = datetime.now(timezone.utc).isoformat()
                record["source_url"] = url
                records.append(record)
                print(index, symbol, record.get("isin"), digest[:12], file=sys.stderr)
                if args.delay:
                    time.sleep(args.delay)
            except Exception as error:
                records.append({"symbol": symbol, "ce": ce, "error": type(error).__name__})
                print(index, symbol, "ERROR", type(error).__name__, file=sys.stderr)
        (args.out_dir / "snapshot.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        sums = []
        for path in sorted(args.out_dir.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS":
                sums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(args.out_dir)}")
        (args.out_dir / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
        print(json.dumps({"status": "OK", "summary": summary(records),
                          "outputs": ["actions.json", "snapshot.json", "session.json", "SHA256SUMS"]},
                         ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "FAILED",
                          "code": str(error) if isinstance(error, ValueError) else "CAPTURE_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

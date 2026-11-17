#!/usr/bin/env python3
"""Read-only, resumable export of Appwrite database schemas, rows, and identities.

Output contains private financial data and potentially password hashes. Use an
ignored backup_live_* directory. Credentials are read only from explicit project
key files or APPWRITE_EXPORT_KEY, never from a CLI login or browser session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests


ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://fra.cloud.appwrite.io/v1"
PROJECT = "6a12447800077d5113ae"
DATABASE = "myinterpreter"
PRIVATE_COLLECTION_PRIORITY = ("achats", "ventes", "portefeuille", "benefits")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def resource_id(value):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,36}", value) or value in (".", ".."):
        raise ValueError("Unexpected Appwrite resource ID")
    return value


class ExportError(Exception):
    def __init__(self, status, kind, scopes=()):
        self.status = status
        self.kind = kind
        self.scopes = list(scopes)
        super().__init__(f"HTTP {status}: {kind}")

    def report(self):
        return {"http_status": self.status, "type": self.kind,
                "missing_scopes": self.scopes}


class ReadOnlyAPI:
    def __init__(self, credentials):
        self.clients = []
        self.preferred = {}
        self.database_limit = None
        for key in dict.fromkeys(credentials):
            client = requests.Session()
            client.headers.update({"X-Appwrite-Project": PROJECT,
                                   "X-Appwrite-Key": key,
                                   "User-Agent": "myinterpreter-recovery-export/1.0"})
            self.clients.append(client)

    def get(self, path, queries=None):
        if not path.startswith("/") or path.startswith("//") or "?" in path:
            raise ValueError("Only relative Appwrite API paths are accepted")
        group = path.split("/")[1]
        if group == "databases" and self.database_limit is not None:
            raise self.database_limit
        indices = list(range(len(self.clients)))
        if group in self.preferred:
            indices.remove(self.preferred[group])
            indices.insert(0, self.preferred[group])
        last = ExportError(401, "export_credentials_unavailable")
        for index in indices:
            for attempt in range(4):
                try:
                    response = self.clients[index].get(
                        ENDPOINT + path,
                        params=[("queries[]", json.dumps(q, separators=(",", ":")))
                                for q in (queries or [])],
                        timeout=(10, 90), allow_redirects=False,
                    )
                except requests.RequestException:
                    if attempt == 3:
                        raise ExportError(0, "export_network_error") from None
                    time.sleep(2 ** attempt)
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        time.sleep(2 ** attempt)
                        continue
                try:
                    payload = response.json()
                except ValueError:
                    raise ExportError(response.status_code, "export_non_json_response") from None
                if response.status_code == 200:
                    self.preferred[group] = index
                    return payload
                scopes = []
                for match in re.findall(r'"([a-z]+\.(?:read|write))"', payload.get("message", "")):
                    scopes.append(match)
                last = ExportError(response.status_code, payload.get("type", "export_api_error"), scopes)
                if response.status_code == 402 and last.kind == "limit_databases_reads_exceeded":
                    self.database_limit = last
                # A scope error may use another existing key. Quota failures do
                # not cause credential rotation or attempts to bypass billing.
                if response.status_code in (401, 403):
                    break
                raise last
        raise last


class Exporter:
    def __init__(self, output, api, resume=False, collections=()):
        self.output = Path(output)
        self.api = api
        self.collections = list(collections)
        self.state_path = self.output / "export_state.json"
        if self.output.is_symlink():
            raise ValueError("Output must not be a symlink")
        if self.state_path.exists():
            if not resume:
                raise ValueError("Output already exists; use --resume")
            self.state = json.loads(self.state_path.read_text())
            if self.state.get("project") != PROJECT or self.state.get("endpoint") != ENDPOINT:
                raise ValueError("Export belongs to another source")
            if self.state.get("selected_collections", []) != self.collections:
                raise ValueError("Resume must use the same collection selection")
        else:
            if self.output.exists() and any(self.output.iterdir()):
                raise ValueError("Choose an empty output directory")
            self.output.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.state = {"format": "myInterpreter resumable database and identity export v1",
                          "endpoint": ENDPOINT, "project": PROJECT,
                          "started_at_utc": utc_now(), "atomic_snapshot": False,
                          "scope": "database_schemas_documents_users_teams",
                          "selected_collections": self.collections,
                          "jobs": {}, "failures": {}, "status": "IN_PROGRESS"}
            self.save()

    def save(self):
        write_json(self.state_path, self.state)

    def pages(self, name, path, field, cutoff=False, order_ids=False,
              id_field="$id", offset_pagination=False):
        job = self.state["jobs"].setdefault(name, {
            "path": path, "field": field, "pages": [], "cursor": None,
            "count": 0, "complete": False, "reported_totals": [],
            "id_field": id_field, "offset_pagination": offset_pagination,
        })
        if job["path"] != path or job["field"] != field:
            raise ValueError("Saved export job does not match requested resource")
        if job["id_field"] != id_field or job["offset_pagination"] != offset_pagination:
            raise ValueError("Saved pagination settings do not match requested resource")
        rows = []
        seen = set()
        # Verify checkpoints before trusting a resume. Never advance past a
        # missing/corrupt page or silently replace a verified collection.
        for page in job["pages"]:
            saved = self.output / page["file"]
            if not saved.resolve().is_relative_to(self.output.resolve()):
                raise ValueError("Saved page path escapes the export directory")
            if not saved.is_file() or digest(saved) != page["sha256"]:
                raise ValueError("Saved export page is missing or corrupt")
            values = json.loads(saved.read_text())[field]
            rows.extend(values)
            for row in values:
                if row[id_field] in seen:
                    raise ValueError("Duplicate IDs in saved export pages")
                seen.add(row[id_field])
        if len(rows) != job["count"]:
            raise ValueError("Checkpoint row count does not match saved pages")
        if job["cursor"] != (rows[-1][id_field] if rows else None):
            raise ValueError("Checkpoint cursor does not match saved pages")
        if job["complete"]:
            if not job.get("needs_reconciliation"):
                self.state["failures"].pop(name, None)
            return rows
        # A run may first be created while quota blocks every page. Set the
        # creation cutoff when this resource can actually start, rather than
        # excluding records created during the wait for restored access.
        if cutoff and not job["pages"]:
            job["cutoff_at_utc"] = utc_now()
        try:
            while True:
                queries = [{"method": "limit", "values": [100]}]
                if order_ids:
                    queries.append({"method": "orderAsc", "attribute": "$id"})
                if cutoff:
                    queries.append({"method": "lessThanEqual", "attribute": "$createdAt",
                                    "values": [job["cutoff_at_utc"]]})
                if offset_pagination and rows:
                    queries.append({"method": "offset", "values": [len(rows)]})
                elif job["cursor"] and not offset_pagination:
                    queries.append({"method": "cursorAfter", "values": [job["cursor"]]})
                payload = self.api.get(path, queries)
                values = payload.get(field)
                if not isinstance(values, list):
                    raise ValueError("API response is missing the expected resource list")
                if len(values) > 100:
                    raise ValueError("API response exceeds requested page size")
                page_ids = [row[id_field] for row in values]
                if len(set(page_ids)) != len(page_ids) or seen.intersection(page_ids):
                    raise ValueError("Pagination returned duplicate IDs")
                filename = f"{name}/pages/{len(job['pages']):06d}.json"
                saved = self.output / filename
                write_json(saved, payload)
                job["pages"].append({"file": filename, "bytes": saved.stat().st_size,
                                     "sha256": digest(saved), "count": len(values)})
                total = payload.get("total")
                if not isinstance(total, int) or total < 0:
                    raise ValueError("API did not provide a valid total")
                job["reported_totals"].append(total)
                seen.update(page_ids)
                rows.extend(values)
                job["count"] = len(rows)
                if values:
                    job["cursor"] = values[-1][id_field]
                job["complete"] = len(values) < 100
                self.save()
                if job["complete"]:
                    if set(job["reported_totals"]) != {len(rows)}:
                        job["needs_reconciliation"] = True
                        self.state["failures"][name] = {
                            "type": "source_count_changed_or_count_mismatch"}
                    else:
                        self.state["failures"].pop(name, None)
                    self.save()
                    return rows
                if len(rows) % 10000 == 0:
                    print(json.dumps({"exported_rows_for_current_resource": len(rows)}), flush=True)
        except ExportError as error:
            self.state["failures"][name] = error.report()
            self.save()
            raise

    def attempt(self, name, path, field, **options):
        try:
            return self.pages(name, path, field, **options)
        except ExportError:
            return None

    def run(self):
        self.state["status"] = "IN_PROGRESS"
        # Identities cannot be reconstructed from market APIs. Capture them
        # before any large database export, even while database reads are
        # blocked. No database quota error suppresses the separate Auth API.
        self.attempt("users", "/users", "users", cutoff=True)
        teams = self.attempt("teams", "/teams", "teams")
        for team in teams or []:
            tid = resource_id(team["$id"])
            self.attempt(f"teams/{tid}/memberships", f"/teams/{quote(tid)}/memberships", "memberships")
        databases = self.attempt("databases", "/databases", "databases")
        database_blocked = self.state["failures"].get("databases", {}).get("http_status") == 402
        if databases is None and not database_blocked:
            databases = [{"$id": DATABASE}]
        for database in databases or []:
            dbid = resource_id(database["$id"])
            prefix = f"databases/{dbid}/collections"
            path = f"/databases/{quote(dbid)}/collections"
            collections = self.attempt(prefix, path, "collections")
            blocked = self.state["failures"].get(prefix, {}).get("http_status") == 402
            if collections is None and self.collections and not blocked:
                collections = [{"$id": resource_id(value)} for value in self.collections]
            priority = {name: index for index, name in enumerate(PRIVATE_COLLECTION_PRIORITY)}
            ordered = sorted(collections or [], key=lambda item: priority.get(item["$id"], len(priority)))
            for collection in ordered:
                cid = resource_id(collection["$id"])
                if self.collections and cid not in self.collections:
                    continue
                directory = f"databases/{dbid}/collections/{cid}"
                base = f"{path}/{quote(cid)}"
                for field in ("attributes", "indexes"):
                    self.attempt(f"{directory}/{field}", f"{base}/{field}", field,
                                 id_field="key", offset_pagination=True)
                self.attempt(f"{directory}/documents", f"{base}/documents", "documents",
                             cutoff=True, order_ids=True)
        self.state["status"] = ("PARTIAL" if self.state["failures"] or self.collections
                                else "EXPORTED_REQUIRES_RECONCILIATION")
        self.state["last_attempt_at_utc"] = utc_now()
        self.state["restore_test_performed"] = False
        self.save()
        summary = {"status": self.state["status"],
                   "saved_pages": sum(len(j["pages"]) for j in self.state["jobs"].values()),
                   "blocked_resources": len(self.state["failures"]),
                   "failures": list(self.state["failures"].values())}
        write_json(self.output / "summary.json", summary)
        print(json.dumps(summary), flush=True)
        return 2 if self.state["status"] == "PARTIAL" else 0


def credentials(paths):
    values = []
    if os.environ.get("APPWRITE_EXPORT_KEY", "").strip():
        values.append(os.environ["APPWRITE_EXPORT_KEY"].strip())
    for name in paths:
        path = Path(name)
        if path.is_file():
            key = path.read_text().strip()
            if key:
                values.append(key)
    if not values:
        raise ValueError("No project API key available; save a read-only key in .appwrite-export-key")
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--key-file", type=Path, action="append")
    parser.add_argument("--collections", nargs="*", default=[],
                        help="Optional subset; also permits document export when collection discovery is unavailable")
    args = parser.parse_args()
    # Restrict automatic exports to the project's ignored recovery directories.
    output = args.output.absolute()
    if output.parent != ROOT or not output.name.startswith("backup_live_"):
        parser.error("Use an ignored backup_live_* directory directly under the project root")
    keys = args.key_file or [ROOT / name for name in (
        ".appwrite-export-key", ".appwrite-ops-key", ".appwrite-orderbook-key", ".env.txt")]
    os.umask(0o077)
    try:
        exporter = Exporter(output, ReadOnlyAPI(credentials(keys)), args.resume, args.collections)
        return exporter.run()
    except (ValueError, OSError) as error:
        # Never echo HTTP headers, response bodies, or credential file contents.
        print(json.dumps({"status": "LOCAL_ERROR", "error": type(error).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

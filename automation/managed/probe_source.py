#!/usr/bin/env python3
"""Manual reachability check only. Never an acquisition receipt or price import."""

from datetime import datetime, timezone
import hashlib
import json
import os
import time

from worker import AcquisitionError, decode, fetch


def main():
    try:
        recipe = decode(os.environ["APP_SOURCE_PROBE"])
        raw, captured = fetch(recipe, time.monotonic() + 30)
        decode(raw)
        print(
            json.dumps(
                {
                    "scope": "REACHABILITY_ONLY",
                    "http_ok": True,
                    "json_valid": True,
                    "bytes": len(raw),
                    "response_sha256": hashlib.sha256(raw).hexdigest(),
                    "captured_at": captured.isoformat(),
                    "raw_archived": False,
                    "database_accessed": False,
                    "source_completeness_assessed": False,
                }
            )
        )
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "scope": "REACHABILITY_ONLY",
                    "http_ok": False,
                    "code": str(error) if isinstance(error, AcquisitionError) else "PROBE_FAILURE",
                    "http_status": error.http_status
                    if isinstance(error, AcquisitionError)
                    else None,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

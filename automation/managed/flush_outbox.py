#!/usr/bin/env python3
"""Inspect private pending archives; --send retries exact bytes without collection."""

import argparse
import json
import os
from pathlib import Path

from archive_store import ArchiveGatewayStore
import worker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = worker.decode(
            args.config.read_bytes() if args.config else os.environ["APP_SOURCE_CONFIG"]
        )
        if os.environ.get("APP_WORKER_DATABASE_URL"):
            raise worker.AcquisitionError("AMBIGUOUS_ARCHIVE_CONFIGURATION")
        store = ArchiveGatewayStore(
            os.environ["APP_ARCHIVE_GATEWAY_URL"],
            os.environ["APP_ARCHIVE_WRITE_TOKEN"],
            config.get("archive_project_reference"),
        )
        entries = store.outbox.entries()
        total = sum(len(store.outbox.read(path)) for path in entries)
        sent = store.flush_pending() if args.send else 0
        print(
            json.dumps(
                {
                    "status": "SENT" if args.send else "INSPECTED",
                    "pending_before": len(entries),
                    "pending_bytes_before": total,
                    "acknowledged": sent,
                    "collection_performed": False,
                }
            )
        )
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": str(error)
                    if isinstance(error, worker.AcquisitionError)
                    else "OUTBOX_FAILURE",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

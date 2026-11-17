#!/usr/bin/env python3
"""Publish one prepared projection through the scoped projection boundary."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation/managed"))
import projection_store
import worker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--project-reference")
    args = parser.parse_args(argv)
    try:
        url = os.environ.get("APP_PROJECTION_URL")
        token = os.environ.get("APP_PROJECTION_TOKEN")
        reference = args.project_reference or os.environ.get(
            "APP_PROJECTION_PROJECT_REFERENCE"
        )
        if not url or not token or not reference:
            raise worker.AcquisitionError("PROJECTION_NOT_CONFIGURED")
        document = args.document.read_text()
        if document.endswith("\n"):
            document = document[:-1]
        summary = projection_store.ProjectionPublisher(
            url, token, reference
        ).publish(document)
        print(json.dumps(summary))
        return 0
    except Exception as error:
        code = (
            str(error)
            if isinstance(error, worker.AcquisitionError)
            else "PROJECTION_PUBLISH_FAILED"
        )
        print(json.dumps({"status": "FAILED", "code": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

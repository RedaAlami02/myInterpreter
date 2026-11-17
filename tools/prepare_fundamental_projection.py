#!/usr/bin/env python3
"""Prepare a private fundamental projection from a verified archive; no remote write."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation/managed"))
import fundamental_feed
import worker


def private_output(path):
    if not path.resolve().is_relative_to((ROOT / "private").resolve()):
        raise ValueError("Output must stay in the ignored private directory")
    if path.exists():
        raise ValueError("Refusing to overwrite an existing artifact")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of")
    args = parser.parse_args(argv)
    try:
        private_output(args.output)
        config = worker.decode(args.config.read_bytes())
        document = fundamental_feed.build(
            args.archive.read_bytes(),
            args.sha256,
            config,
            worker.decode(args.index.read_bytes()),
            as_of=worker.utc(args.as_of) if args.as_of else datetime.now(timezone.utc),
        )
        args.output.write_text(fundamental_feed.canonical(document) + "\n")
        print(
            json.dumps(
                {
                    "status": document["completeness"],
                    "symbol": document["symbol"],
                    "c_name": document["c_name"],
                    "fiscal_year": document["fields"]["fiscal_year"],
                    "fields": sum(
                        value is not None for value in document["fields"].values()
                    ),
                    "remote_data_written": False,
                }
            )
        )
        return 0
    except Exception as error:
        code = (
            str(error)
            if isinstance(error, (ValueError, worker.AcquisitionError))
            else "FUNDAMENTAL_PREPARATION_FAILED"
        )
        print(json.dumps({"status": "FAILED", "code": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

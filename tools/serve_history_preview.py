#!/usr/bin/env python3
"""Serve only the opt-in history preview on loopback with a pinned export.

No migration environment or backend credentials are passed to the PHP process.
This launches a foreground development server, never a schedule or deployment.
"""

import argparse
import hashlib
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--port", type=int, default=8943)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a nonprivileged local port")
    try:
        raw = (directory / "manifest.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != args.manifest_sha256:
            raise ValueError("Manifest pin mismatch")
    except (OSError, ValueError):
        parser.error("A matching pinned history export is required")
    root = Path(__file__).resolve().parents[1]
    # Pass only ordinary runtime settings, plus the sanitized export reference.
    env = {
        key: os.environ[key]
        for key in ("PATH", "LANG", "LC_ALL", "TZ")
        if key in os.environ
    }
    env["MYINTERPRETER_HISTORY_PREVIEW_DIR"] = str(directory)
    env["MYINTERPRETER_HISTORY_PREVIEW_SHA256"] = args.manifest_sha256
    os.execvpe(
        "php",
        [
            "php",
            "-d",
            "display_errors=0",
            "-d",
            "auto_prepend_file=",
            "-d",
            "auto_append_file=",
            "-S",
            f"127.0.0.1:{args.port}",
            "-t",
            str(root),
            str(root / "tools/history_preview_router.php"),
        ],
        env,
    )


if __name__ == "__main__":
    main()

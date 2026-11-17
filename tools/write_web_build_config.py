#!/usr/bin/env python3
"""Write only public Supabase runtime settings; never admin/database credentials."""

import argparse
import json
import os
import subprocess
import tempfile

from stage_supabase import ROOT, local_config
from write_flutter_build_config import public_config


def write_web_config(config, target, *, refresh_public=False):
    if target.exists() and not refresh_public:
        return False  # Preserve existing administrator configuration byte-for-byte.
    public = public_config(config)
    runtime = {
        "backend": "supabase",
        "url": public["SUPABASE_PROJECT_URL"],
        "publishable_key": public["SUPABASE_PUBLISHABLE_KEY"],
        "admin_user_id": "",
    }
    previous = target.read_bytes() if target.exists() else None
    if previous is not None:
        loaded = subprocess.run(
            ["php", "-r", "echo json_encode(require $argv[1],JSON_THROW_ON_ERROR);", str(target)],
            capture_output=True,
            text=True,
            check=True,
        )
        existing = json.loads(loaded.stdout)
        if (
            not isinstance(existing, dict)
            or not set(runtime).issubset(existing)
            or not set(existing).issubset(set(runtime) | {"market_preview", "portfolio_valuation", "public_url", "recurring_feed"})
            or existing["backend"] != "supabase"
            or existing["url"].rstrip("/") != runtime["url"].rstrip("/")
            or not isinstance(existing["admin_user_id"], str)
        ):
            raise ValueError("Public refresh cannot change project or configuration shape")
        runtime["admin_user_id"] = existing["admin_user_id"]
        for name in ("market_preview", "portfolio_valuation", "recurring_feed"):
            if name in existing:
                if not isinstance(existing[name], bool):
                    raise ValueError("Invalid runtime feature setting")
                runtime[name] = existing[name]
        if "public_url" in existing:
            runtime["public_url"] = existing["public_url"]
    runtime["public_url"] = config.get("MYINTERPRETER_PUBLIC_URL", runtime.get(
        "public_url", "https://myinterpreter.infinityfree.me"))
    # Use the same pure validator as the runtime callback builder.
    subprocess.run(
        ["php", "-r", 'require $argv[1]; sb_auth_redirect_url(json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR),"/auth_callback.php");',
         str(ROOT / "core/supabase_session.php")],
        input=json.dumps(runtime["public_url"]), capture_output=True, text=True, check=True,
    )
    result = subprocess.run(
        [
            "php",
            "-r",
            '$v=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR); echo "<?php\nreturn ".var_export($v,true).";\n";',
        ],
        input=json.dumps(runtime),
        capture_output=True,
        text=True,
        check=True,
    )
    if previous is None:
        with target.open("x") as stream:
            stream.write(result.stdout)
    else:
        descriptor, temporary = tempfile.mkstemp(prefix=".web-public-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                stream.write(result.stdout)
            if target.read_bytes() != previous:
                raise ValueError("Configuration changed during refresh")
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-public",
        action="store_true",
        help="Replace public key only, preserving project and administrator",
    )
    args = parser.parse_args()
    try:
        written = write_web_config(
            local_config(ROOT / ".supabase-migration.env"),
            ROOT / "config/supabase.local.php",
            refresh_public=args.refresh_public,
        )
        if not written:
            print(json.dumps({"written": False, "reason": "existing_configuration_preserved"}))
            return 0
        print(json.dumps({"written": True, "backend": "supabase", "secret_fields_written": False}))
        return 0
    except Exception as exc:
        print(json.dumps({"written": False, "error_category": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

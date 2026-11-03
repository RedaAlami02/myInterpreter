#!/usr/bin/env python3
"""Write an ignored Flutter build config containing only public client fields."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def public_config(config, backend="supabase"):
    if backend != "supabase":
        raise ValueError("Unknown client backend")
    url = config.get("SUPABASE_PROJECT_URL", "")
    key = config.get("SUPABASE_PUBLISHABLE_KEY", "")
    if (not re.fullmatch(r"https://[a-z0-9]{10,40}\.supabase\.co/?",url)
            or not re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]+",key)):
        raise ValueError("Invalid public client configuration")
    result = {"MYINTERPRETER_BACKEND":"supabase", "SUPABASE_PROJECT_URL":url,
              "SUPABASE_PUBLISHABLE_KEY":key}
    for field in ("MYINTERPRETER_MARKET_PREVIEW", "MYINTERPRETER_MOBILE_AUTH_LINKS", "MYINTERPRETER_RECURRING_FEED"):
        setting = config.get(field)
        if setting is not None:
            if setting not in ("true", "false"):
                raise ValueError("Invalid public feature setting")
            result[field] = setting
    return result


def write_config(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".flutter-public-",dir=path.parent)
    try:
        with os.fdopen(descriptor,"w") as stream:
            stream.write(json.dumps(values,indent=2)+"\n")
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend",choices=("supabase",),default="supabase")
    parser.add_argument("--from-env",action="store_true")
    parser.add_argument("--output",type=Path,default=ROOT/"myinterpreter_app/backend.local.json")
    args = parser.parse_args()
    try:
        if args.from_env:
            config = os.environ
        else:
            # The CI --from-env path uses only Python's standard library.
            from stage_supabase import local_config
            config = local_config(ROOT/".supabase-migration.env")
        values = public_config(config,args.backend)
        write_config(args.output,values)
        print(json.dumps({"written":True,"backend":args.backend,"secret_fields_written":False,
                          "permissions_private":stat.S_IMODE(args.output.stat().st_mode)==0o600}))
    except Exception as error:
        print(json.dumps({"written":False,"error_category":type(error).__name__}))
        raise SystemExit(1)

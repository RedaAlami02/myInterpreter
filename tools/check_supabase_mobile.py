#!/usr/bin/env python3
"""Verify the actual mobile SDK against Supabase with email-free test accounts.

Secrets stay in memory/a mode-0600 temporary fixture. They never enter Dart
defines, command arguments, tracked files or printed test output. Synthetic
users and their dependent records are removed in finally.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import uuid

import psycopg

from check_supabase_auth import api, require
from stage_supabase import ROOT, connection_options, local_config


def check(config):
    identities = []
    report = {"ok":False,"signup_email_sent":False}
    cleanup = True
    try:
        password = secrets.token_urlsafe(32)
        for _ in range(2):
            email = "mobile-check-" + uuid.uuid4().hex + "@example.invalid"
            response = api(config,"POST","/auth/v1/admin/users",
                           {"email":email,"password":password,"email_confirm":True},admin=True)
            require(response.status_code in (200,201))
            identities.append({"id":response.json()["id"],"email":email})
        with psycopg.connect(**connection_options(config)) as connection:
            company = connection.execute("SELECT name FROM public.company ORDER BY id LIMIT 1").fetchone()[0]
        with tempfile.TemporaryDirectory(prefix="myinterpreter-mobile-") as private_dir:
            fixture = Path(private_dir)/"fixture.json"
            fixture.touch(mode=0o600)
            fixture.write_text(json.dumps({"url":config["SUPABASE_PROJECT_URL"],
                "publishable_key":config["SUPABASE_PUBLISHABLE_KEY"],"identities":identities,
                "password":password,"company":company}))
            environment = os.environ.copy()
            environment["MYINTERPRETER_LIVE_FIXTURE"] = str(fixture)
            environment.pop("SUPABASE_SECRET_KEY",None)
            environment.pop("SUPABASE_DATABASE_URL",None)
            # Capture child output rather than risk a future failed assertion
            # printing a credential. The progress file contains phase names only.
            result = subprocess.run(["flutter","test","--no-pub","test/live_supabase_backend.dart"],
                cwd=ROOT/"myinterpreter_app",env=environment,capture_output=True,timeout=180)
            progress = Path(private_dir)/"progress.json"
            phase = json.loads(progress.read_text()).get("phase") if progress.exists() else "test_start"
            report.update({"ok":result.returncode == 0 and phase == "passed","phase":phase,
                           "real_mobile_sdk_exercised":True})
    except Exception as error:
        report["error_category"] = type(error).__name__
    finally:
        for identity in identities:
            try:
                response = api(config,"DELETE","/auth/v1/admin/users/"+identity["id"],admin=True)
                cleanup = response.status_code in (200,204) and cleanup
            except Exception:
                cleanup = False
        report["synthetic_users_deleted"] = cleanup
        report["ok"] = report["ok"] and cleanup
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise-auth",action="store_true")
    args = parser.parse_args()
    if not args.exercise_auth:
        print(json.dumps({"status":"prepared","live_auth_requires_exercise_auth":True}))
    else:
        try:
            report = check(local_config(ROOT/".supabase-migration.env"))
        except Exception as error:
            report = {"ok":False,"error_category":type(error).__name__}
        print(json.dumps(report))
        raise SystemExit(0 if report.get("ok") else 1)

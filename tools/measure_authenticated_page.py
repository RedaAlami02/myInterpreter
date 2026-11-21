#!/usr/bin/env python3
"""Measure a signed-in page without asking anyone to sign in.

Creates a throwaway confirmed account through the Auth admin API, signs in
through the site's own form, reads the ?timing=1 comment from the response, and
deletes the account afterwards whatever happens. The account has no portfolio,
so it measures the server path (auth, renders, shared reads), not personal data.

    SUPABASE_PROJECT_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
        python3 tools/measure_authenticated_page.py \
            --site https://example.com/ --page portfolio.php --loads 3 --wait 60

Needs Playwright with a Chromium build. Prints one line per load.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

TIMING_RE = re.compile(r"<!-- timing: .*? -->")


def admin(base, key, path, payload=None, method="GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        base + path, data=data, method=method,
        headers={"apikey": key, "Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b"null")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True, help="site root, with trailing slash")
    parser.add_argument("--page", default="portfolio.php")
    parser.add_argument("--loads", type=int, default=3)
    parser.add_argument("--wait", type=int, default=60, help="seconds between loads")
    parser.add_argument("--email", default="timing-probe@example.invalid")
    parser.add_argument("--chromium", help="path to a Chromium binary when Playwright's own build is missing")
    args = parser.parse_args()

    base = (os.environ.get("SUPABASE_PROJECT_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SECRET_KEY") or ""
    if not base or not key:
        print("SUPABASE_PROJECT_URL and a service key are required.", file=sys.stderr)
        return 2
    password = "Probe-%d-Aa1" % int(time.time() % 100000)

    from playwright.sync_api import sync_playwright

    user = admin(base, key, "/auth/v1/admin/users",
                 {"email": args.email, "password": password, "email_confirm": True}, "POST")
    uid = user.get("id")
    if not uid:
        print("Could not create the probe account.", file=sys.stderr)
        return 1
    print("probe account:", uid, file=sys.stderr)
    try:
        with sync_playwright() as playwright:
            launch = {"headless": True}
            if args.chromium:
                launch["executable_path"] = args.chromium
            browser = playwright.chromium.launch(**launch)
            context = browser.new_context()
            page = context.new_page()
            documents = {}

            def capture(response):
                if response.request.resource_type == "document":
                    try:
                        documents[response.url] = response.body().decode("utf-8", "replace")
                    except Exception:
                        pass

            page.on("response", capture)
            page.goto(args.site + "index.php", wait_until="load", timeout=120000)
            with page.expect_navigation(wait_until="load", timeout=120000):
                page.evaluate("""([email, password]) => {
                    const marker = document.querySelector('input[name="login_form"]');
                    const form = marker.closest('form');
                    form.querySelector('input[name="email"]').value = email;
                    form.querySelector('input[name="password"]').value = password;
                    form.submit();
                }""", [args.email, password])
            for index in range(args.loads):
                if index:
                    time.sleep(args.wait)
                documents.clear()
                # The counter keeps the browser from answering from its own
                # cache, which would repeat the previous response verbatim.
                page.goto(f"{args.site}{args.page}?timing=1&n={index}",
                          wait_until="load", timeout=120000)
                body = "".join(documents.values())
                found = TIMING_RE.search(body)
                print(f"load {index + 1}: {found.group(0) if found else '(no timing comment)'}")
            context.close()
            browser.close()
    finally:
        admin(base, key, "/auth/v1/admin/users/" + uid, None, "DELETE")
        print("probe account deleted", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

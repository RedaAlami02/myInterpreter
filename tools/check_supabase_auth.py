#!/usr/bin/env python3
"""Exercise real Auth + PHP portfolio with temporary, email-free test users.

Requires --exercise-auth because it temporarily creates confirmed synthetic
accounts through the admin API. No signup email is sent. Their UUIDs are held
only in memory; deletion in finally cascades only these fixtures. Output is
aggregate booleans, never credentials, tokens, identities or financial records.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
import time
import uuid

import psycopg
import requests

from stage_supabase import ROOT, connection_options, local_config


def require(condition):
    if not condition:
        raise ValueError("Authentication integration check failed")


def api(config, method, path, data=None, *, token=None, admin=False):
    headers = {"apikey": config["SUPABASE_SECRET_KEY"] if admin else config["SUPABASE_PUBLISHABLE_KEY"]}
    if token:
        headers["Authorization"] = "Bearer " + token
    return requests.request(method, config["SUPABASE_PROJECT_URL"].rstrip("/") + path,
                            json=data, headers=headers, timeout=(10, 30), allow_redirects=False)


def csrf(response):
    require(response.status_code == 200)
    match = re.search(r'name="csrf_token" value="([a-f0-9]{64})"', response.text)
    require(match is not None)
    return match[1]


def run(config):
    identities = []
    server = None
    report = {"ok": False, "signup_email_sent": False}
    phase = "create_synthetic_users"
    cleanup_ok = True
    try:
        password = secrets.token_urlsafe(32)
        for _ in range(2):
            email = "migration-check-" + uuid.uuid4().hex + "@example.invalid"
            response = api(config, "POST", "/auth/v1/admin/users",
                           {"email": email, "password": password, "email_confirm": True}, admin=True)
            require(response.status_code in (200, 201))
            identifier = response.json()["id"]
            identities.append({"id": identifier, "email": email})

        phase = "real_login_and_refresh"
        logins = []
        for identity in identities:
            response = api(config, "POST", "/auth/v1/token?grant_type=password",
                           {"email": identity["email"], "password": password})
            require(response.status_code == 200)
            tokens = response.json()
            require(tokens["user"]["id"] == identity["id"])
            response = api(config, "POST", "/auth/v1/token?grant_type=refresh_token",
                           {"refresh_token": tokens["refresh_token"]})
            require(response.status_code == 200)
            logins.append(response.json())
        report["real_login_and_refresh"] = True

        phase = "authenticated_market_privacy"
        from check_supabase_market import check as check_market
        market_report = check_market(logins[0]['access_token'])
        require(market_report.get('authenticated_php_api_verified') is True)
        report['authenticated_php_market_reads'] = True
        report['anonymous_market_access_denied'] = market_report['anonymous_access_denied']

        phase = "php_site"
        with tempfile.TemporaryDirectory(prefix="myinterpreter-auth-") as private_dir:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            environment = os.environ.copy()
            environment.update({"MYINTERPRETER_BACKEND": "supabase",
                                "SUPABASE_PROJECT_URL": config["SUPABASE_PROJECT_URL"],
                                "SUPABASE_PUBLISHABLE_KEY": config["SUPABASE_PUBLISHABLE_KEY"]})
            # Secret/database credentials are not provided to the web process.
            environment.pop("SUPABASE_SECRET_KEY", None)
            environment.pop("SUPABASE_DATABASE_URL", None)
            server = subprocess.Popen(["php", "-d", "session.save_path=" + private_dir,
                                       "-S", f"127.0.0.1:{port}", "-t", str(ROOT)],
                                      cwd=ROOT, env=environment, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
            base = f"http://127.0.0.1:{port}"
            for _ in range(50):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            sessions = [requests.Session(), requests.Session()]
            for session, identity in zip(sessions, identities):
                page = session.get(base + "/index.php", timeout=45)
                token = csrf(page)
                denied = session.post(base + "/index.php", data={"login_form":"1"}, timeout=10)
                require(denied.status_code == 403)
                login = session.post(base + "/index.php", data={
                    "csrf_token": token, "login_form":"1", "email":identity["email"],
                    "password":password, "stay":"1"}, timeout=30, allow_redirects=False)
                require(login.status_code == 302)
                cookie = next((c for c in session.cookies if c.name == "mi_sb_refresh"), None)
                require(cookie is not None and cookie.has_nonstandard_attr("HttpOnly")
                        and cookie.get_nonstandard_attr("SameSite") == "Lax")
            report["php_login_csrf_and_cookie_flags"] = True

            phase = "php_atomic_trade"
            with psycopg.connect(**connection_options(config)) as connection:
                name = connection.execute("SELECT name FROM public.company ORDER BY id LIMIT 1").fetchone()[0]
            page = sessions[0].get(base + "/portfolio.php", timeout=45)
            token = csrf(page)
            trade = {"csrf_token":token, "add_buy":"1", "NAME":name, "NUMBER":"2",
                     "PRIX_ACHAT":"100.15", "trade_request_id":str(uuid.uuid4())}
            for _ in range(2):
                response = sessions[0].post(base + "/portfolio.php", data=trade, timeout=45)
                require(response.status_code == 200)
            with psycopg.connect(**connection_options(config)) as connection:
                result = connection.execute("SELECT count(*),sum(number) FROM public.achats WHERE user_id=%s",
                                            (identities[0]["id"],)).fetchone()
                require(result == (1, 2))
                result = connection.execute("SELECT quantity,total_cost FROM public.portefeuille WHERE user_id=%s",
                                            (identities[0]["id"],)).fetchone()
                require(tuple(map(str, result)) == ("2", "200.30"))
            report["php_trade_retry_exactly_once"] = True

            phase = "real_api_owner_isolation"
            for table in ("achats", "ventes", "portefeuille", "benefits"):
                anonymous = api(config, "GET", "/rest/v1/" + table + "?select=id")
                require(anonymous.status_code in (401,403))
                other = api(config, "GET", "/rest/v1/" + table + "?select=id", token=logins[1]["access_token"])
                require(other.status_code == 200 and other.json() == [])
            report["real_api_anonymous_and_cross_owner_denied"] = True

            phase = "concurrent_sells"
            def submit_sale(_):
                return api(config, "POST", "/rest/v1/rpc/record_trade", {
                    "p_request_id":str(uuid.uuid4()), "p_side":"sell", "p_c_name":name,
                    "p_quantity":"1", "p_price":"110"}, token=logins[1]["access_token"]).status_code

            response = api(config, "POST", "/rest/v1/rpc/record_trade", {
                "p_request_id":str(uuid.uuid4()), "p_side":"buy", "p_c_name":name,
                "p_quantity":"1", "p_price":"100"}, token=logins[1]["access_token"])
            require(response.status_code == 200)
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = sorted(executor.map(submit_sale, range(2)))
            require(statuses == [200,400])
            with psycopg.connect(**connection_options(config)) as connection:
                require(connection.execute("SELECT count(*) FROM public.ventes WHERE user_id=%s", (identities[1]["id"],)).fetchone()[0] == 1)
                require(connection.execute("SELECT count(*) FROM public.portefeuille WHERE user_id=%s", (identities[1]["id"],)).fetchone()[0] == 0)
            report["concurrent_sells_cannot_oversell"] = True

            phase = "logout"
            page = sessions[0].get(base + "/portfolio.php", timeout=45)
            response = sessions[0].post(base + "/index.php", data={"logout":"1", "csrf_token":csrf(page)},
                                        timeout=30, allow_redirects=False)
            require(response.status_code == 302)
            response = sessions[0].get(base + "/portfolio.php", timeout=15, allow_redirects=False)
            require(response.status_code == 302)
            require(not any(c.name == "mi_sb_refresh" for c in sessions[0].cookies))
            report["php_logout_and_private_page_redirect"] = True
            for session in sessions:
                session.close()
        report["ok"] = True
    except Exception as error:
        report.update({"failed_phase": phase, "error_category": type(error).__name__})
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        for identity in identities:
            try:
                response = api(config, "DELETE", "/auth/v1/admin/users/" + identity["id"], admin=True)
                cleanup_ok = response.status_code in (200,204) and cleanup_ok
            except Exception:
                cleanup_ok = False
        report["synthetic_users_deleted"] = cleanup_ok
        report["ok"] = report["ok"] and cleanup_ok
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise-auth", action="store_true")
    args = parser.parse_args()
    if not args.exercise_auth:
        print(json.dumps({"status":"prepared", "live_auth_requires_exercise_auth":True}))
        return 0
    try:
        report = run(local_config(ROOT / ".supabase-migration.env"))
    except Exception as error:
        report = {"ok":False, "error_category":type(error).__name__}
    print(json.dumps(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

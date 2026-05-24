# CLAUDE.md

**myInterpreter** — Moroccan Bourse (CDG Capital) stock analysis app.

## Stack
- **App**: Flutter (Android), lives in `myinterpreter_app/`
- **Backend**: Appwrite Cloud (Frankfurt) — auth, database, cloud function
- **Scraper**: Appwrite Cloud Function (`cloud_function/`) — fetches CDG Bourse API on cron `0 8,11,14 * * *` UTC
- **Web**: PHP website (repo root) hosted on InfinityFree — fully migrated to Appwrite REST API
- **CI**: GitHub Actions — builds release APK on every push to master, download from Actions tab

## Key files
| File | Purpose |
|---|---|
| `myinterpreter_app/lib/appwrite_client.dart` | Shared Appwrite client, endpoint, project ID |
| `myinterpreter_app/lib/main.dart` | Auth gate → Login or Home |
| `myinterpreter_app/lib/screens/` | login, home, screener, portfolio, statistics, stock_detail, buy_sell_sheet |
| `cloud_function/functions/getprice/src/main.py` | Scraper cloud function |
| `core/Appwrite.php` | PHP curl-based Appwrite REST helper (no Composer) |
| `core/auth.php` | requireLogin(), requireAdmin(), is_admin() |
| `config/config.php` | Ratio thresholds, ADMIN_USER_ID, CSRF helpers |
| `migrate.py` | One-time MySQL → Appwrite migration (already run) |
| `appwrite_setup.py` | One-time Appwrite collection setup (already run) |

## Appwrite database: `myinterpreter`
| Table | Row security | Access |
|---|---|---|
| `data`, `company`, `format` | off | `read("any")` — public market data |
| `achats`, `ventes`, `portefeuille`, `benefits` | off | `read("users")` — filtered by `user_id` in queries |

All rows in `achats`/`ventes`/`portefeuille` are created with `Permission.read/write(Role.user(userId))`.

## PHP website (InfinityFree)
- **Host**: InfinityFree — PHP only, no Composer, no Node.js
- **FTP**: credentials and upload script stored in session memory (see MEMORY.md)
- **Auth**: Appwrite cookie-based sessions — `POST /account/sessions/email` returns empty `secret`; real session is in `Set-Cookie` headers. Stored in `$_SESSION['aw_cookie']`, forwarded as `Cookie:` header.
- **Admin**: `ADMIN_USER_ID = 6a124b8900257649d4c1` — only admin can access Update.php/results.php
- **Staging**: sync files to `/tmp/myinterpreter_upload/` then run Python FTP script to deploy

## Install APK on phone
```bash
# After downloading artifact zip from GitHub Actions:
unzip app-release.zip
adb install app-release.apk   # use -r to update without uninstalling
```

## Important rules
- **Never use `--release` build locally** — crashes the laptop. Use CI.
- **All table names lowercase** in Appwrite queries.
- **Appwrite query format**: JSON objects — `{"method":"equal","attribute":"field","values":["val"]}`. String format like `equal("field","val")` does NOT work on Appwrite Cloud.
- `orderDesc`/`orderAsc` must NOT have a `values` key. `limit` must NOT have an `attribute` key.
- The `scrapping/` directory is gitignored.
- Gradle cache was removed from `/media/redachen/windows/gradle_home/` — do not recreate locally.
- **statistics.php** FIFO P&L not yet verified with real migrated data — test before relying on it.

# CLAUDE.md

**myInterpreter** — Moroccan Bourse (CDG Capital) stock analysis app.

## Stack
- **App**: Flutter (Android), lives in `myinterpreter_app/`
- **Backend**: Appwrite Cloud (Frankfurt) — auth, database, cloud function
- **Scraper**: Appwrite Cloud Function (`cloud_function/`) — fetches CDG Bourse API every 15 min, Mon–Fri 09:00–15:45 Casablanca time (`*/15 8-14 * * 1-5` UTC)
- **Web**: PHP website (repo root) hosted on InfinityFree — fully migrated to Appwrite REST API
- **CI**: GitHub Actions — builds release APK on every push to master, download from Actions tab

## Key files
| File | Purpose |
|---|---|
| `myinterpreter_app/lib/appwrite_client.dart` | Shared Appwrite client, endpoint, project ID |
| `myinterpreter_app/lib/main.dart` | Auth gate → Login or Home |
| `myinterpreter_app/lib/screens/` | login, home, screener, portfolio, statistics, stock_detail, buy_sell_sheet |
| `cloud_function/functions/getprice/src/main.py` | Scraper cloud function |
| `cloud_function/functions/cleanup/src/main.py` | End-of-day cleanup function |
| `core/Appwrite.php` | PHP curl-based Appwrite REST helper (no Composer) |
| `core/auth.php` | requireLogin(), requireAdmin(), is_admin() |
| `config/config.php` | Ratio thresholds, ADMIN_USER_ID, CSRF helpers |
| `appwrite_setup.py` | One-time collection setup (already run — includes `latest_prices`) |

## Appwrite database: `myinterpreter`
| Collection | Access | Purpose |
|---|---|---|
| `data` | `read("any")` | Historical price records — one doc per company per scraper run |
| `latest_prices` | `read("any")` | One row per company, upserted each scraper run — use this for current price lookups |
| `company`, `format` | `read("any")` | Company fundamentals and symbol mappings |
| `achats`, `ventes`, `portefeuille`, `benefits` | `read("users")` | User portfolio data, filtered by `user_id` |

All rows in `achats`/`ventes`/`portefeuille` are created with `Permission.read/write(Role.user(userId))`.

## Scraper design
- Inserts one doc into `data` per company per run (historical record)
- Also upserts `latest_prices` — one row per company, always current non-zero price
- Suspended stocks (e.g. PROMOPHARM) get last known price from `latest_prices` fallback — never stores `pa=0`
- `latest_prices` is what portfolio.php and Flutter read for current prices — single fast query

## PHP website (InfinityFree)
- **Host**: InfinityFree — PHP only, no Composer, no Node.js
- **FTP**: credentials and upload script stored in session memory (see MEMORY.md)
- **Auth**: Appwrite cookie-based sessions — `POST /account/sessions/email` returns empty `secret`; real session is in `Set-Cookie` headers. Stored in `$_SESSION['aw_cookie']`, forwarded as `Cookie:` header.
- **Admin**: `ADMIN_USER_ID = 6a124b8900257649d4c1` — only admin can access Update.php/results.php
- **Deploy**: rsync to `/tmp/myinterpreter_upload/` then upload via Python ftplib script (see MEMORY.md)

## Install APK on phone
```bash
# After downloading artifact zip from GitHub Actions:
unzip app-release.zip
adb install app-release.apk   # use -r to update without uninstalling
```

## Important rules
- **Never use `--release` build locally** — crashes the laptop. Use CI.
- **All collection names lowercase** in Appwrite queries.
- **Appwrite query format**: JSON objects — `{"method":"equal","attribute":"field","values":["val"]}`. String format does NOT work on Appwrite Cloud.
- `orderDesc`/`orderAsc` must NOT have a `values` key. `limit` must NOT have an `attribute` key.
- **No index on `pa`** in `data` collection — never use `greater_than('pa', ...)` in queries, filter in code instead.
- The `scrapping/` directory is gitignored.
- Gradle cache was removed from `/media/redachen/windows/gradle_home/` — do not recreate locally.
- **statistics.php** FIFO P&L not yet verified with real migrated data — test before relying on it.

# CLAUDE.md

**myInterpreter** — Moroccan Bourse (CDG Capital) stock analysis app.

## Stack
- **App**: Flutter (Android), lives in `myinterpreter_app/`
- **Backend**: Appwrite Cloud (Frankfurt) — auth, database, cloud function
- **Scraper**: Appwrite Cloud Function (`cloud_function/`) — fetches CDG Bourse API on cron `0 8,11,14 * * *` UTC
- **CI**: GitHub Actions — builds debug APK on every push to master, download from Actions tab

## Key files
| File | Purpose |
|---|---|
| `myinterpreter_app/lib/appwrite_client.dart` | Shared Appwrite client, endpoint, project ID |
| `myinterpreter_app/lib/main.dart` | Auth gate → Login or Home |
| `myinterpreter_app/lib/screens/` | login, home, screener, portfolio, statistics, stock_detail, buy_sell_sheet |
| `cloud_function/functions/getprice/src/main.py` | Scraper cloud function |
| `migrate.py` | One-time MySQL → Appwrite migration (already run) |
| `appwrite_setup.py` | One-time Appwrite collection setup (already run) |

## Appwrite database: `myinterpreter`
| Table | Row security | Access |
|---|---|---|
| `data`, `company`, `format` | off | `read("any")` — public market data |
| `achats`, `ventes`, `portefeuille`, `benefits` | off | `read("users")` — filtered by `user_id` in queries |

All rows in `achats`/`ventes`/`portefeuille` are created with `Permission.read/write(Role.user(userId))`.

## Install APK on phone
```bash
# After downloading artifact zip from GitHub Actions:
unzip app-debug.zip
adb uninstall com.myinterpreter.myinterpreter_app   # only if switching build source
adb install app-debug.apk
```

## Important rules
- **Never use `--release` build locally** — crashes the laptop. Use CI.
- **All table names lowercase** in Appwrite queries.
- The PHP/MySQL web app in the root is the old version — reference only, not active.
- The `scrapping/` directory is gitignored.
- Gradle cache was removed from `/media/redachen/windows/gradle_home/` — do not recreate locally.

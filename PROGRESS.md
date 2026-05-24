# myInterpreter — Migration Progress & Vision

## Vision
Rebuild the PHP/MySQL Moroccan Bourse (CDG Capital) stock analysis web app as a
**Flutter Android app** backed by **Appwrite Cloud**, with a **Python Cloud
Function** replacing the local scraper. Goal: install as APK on phone, no
self-hosted server.

## Architecture
- **Client:** Flutter (Dart), Android target. Lives in `myinterpreter_app/`.
- **Backend:** Appwrite Cloud (Frankfurt region).
  - Endpoint: `https://fra.cloud.appwrite.io/v1`
  - Project ID: `6a12447800077d5113ae`
  - Database ID: `myinterpreter`
- **Auth:** Appwrite email/password sessions.
- **Scraper:** Appwrite Cloud Function (Python) fetching CDG Bourse API on a cron.

## Collections (Appwrite DB `myinterpreter`)
`company`, `data`, `format`, `achats`, `ventes`, `portefeuille`, `benefits`
(snake_case field names, mirroring the old MySQL schema lowercased).

## Phase status

### ✅ Phase 1 — Appwrite setup
Project, DB, and 7 collections created via `appwrite_setup.py`.

### ✅ Phase 2 — Collection schema script
`appwrite_setup.py` defines all attributes/indexes.

### ✅ Phase 3 — MySQL → Appwrite migration
`migrate.py` ports all 7 tables. API key + user ID hardcoded. Retry loop with
exponential backoff. Should be re-verified that every table fully migrated.

### ✅ Phase 4 — Cloud Function scraper
`cloud_function/main.py` (and `cloud_function/functions/getprice/src/main.py`):
- Fetches CDG Bourse API with spoofed browser headers.
- Joins `format` (symbol→name) + `company` (fundamentals) + live price.
- Computes ratios (CB, PER, PEG, PR, PB) + green/orange/red rating.
- Inserts into `data` collection (multiple snapshots/day intentional — intraday history).
- Env vars: `APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, `APPWRITE_API_KEY`.
- Cron: `0 8,11,14 * * *` UTC (≈ 09:00, 12:00, 15:30 Casablanca).
- **TODO:** verify it runs via "Execute now" in Appwrite console.

### ✅ Phase 5 — Flutter app (feature-complete, analyze clean)
Project at `myinterpreter_app/`. All APIs use `TablesDB` (non-deprecated).

Files:
- `lib/appwrite_client.dart` — shared Client / Account / Databases / TablesDB instances.
- `lib/main.dart` — auth gate routing to Login or Home.
- `lib/screens/login.dart` — email/password login.
- `lib/screens/home.dart` — bottom-nav shell (Screener / Portfolio / Stats) + logout.
- `lib/screens/screener.dart` — latest snapshot per stock, PER/PEG/PR/PB color dots, search bar, pull-to-refresh, buy button per row.
- `lib/screens/stock_detail.dart` — PA line chart with Today/Week/Month/Year server-side filters, ratio history rows, buy/sell FABs, pull-to-refresh.
- `lib/screens/portfolio.dart` — user holdings, sell button per holding, pull-to-refresh.
- `lib/screens/statistics.dart` — PER rating distribution + realized gains/tax (15%) section, pull-to-refresh.
- `lib/screens/buy_sell_sheet.dart` — shared buy/sell bottom sheet: writes to `achats`/`ventes`, upserts/deletes `portefeuille`.

`flutter analyze`: clean (no issues).

### 🟡 Phase 6 — Build APK & install on phone
APK built and installed on device. Login attempted — failed with:
`ClientException with SocketException: Failed host lookup: 'fra.cloud.appwrite.io'`
This is a DNS/network issue on the phone (no internet at time of test), not a code bug.
Login code is correct — `createEmailPasswordSession` wired up properly.

**Build note:** Use `flutter build apk --debug` for iterative testing (faster, no R8/ProGuard).
Only use `--release` for final distribution.
`--release` build is resource-heavy and may crash low-RAM laptops.

**Gradle cache** is stored at `/media/redachen/windows/gradle_home/` (Windows partition)
to share the cache across OSes and preserve it across Linux reinstalls.

## Dev environment (verified working)
- Flutter 3.44.0 stable, Channel stable.
- Android SDK at `~/Android` (cmdline-tools `latest`, platforms-34, build-tools 34.0.0).
- JDK: openjdk-17.
- `flutter doctor` ✓ Flutter, ✓ Android toolchain, ✓ Chrome, ✓ Network, ✗ Linux desktop (intentionally skipped — Android-only).
- **Note:** `flutter` is at `~/flutter/bin/flutter`; not on default PATH.
  Use `export PATH="$HOME/flutter/bin:$PATH"` in each session, or add to `~/.bashrc`.

## How to resume next session
1. `cd ~/studies_windows/Bourse/myInterpreter/myinterpreter_app`
2. `export PATH="$HOME/flutter/bin:$PATH"`
3. Plug phone in (USB debugging on), or run `flutter emulators`.
4. `flutter run` — verify login works against Appwrite, screener lists stocks.
5. **Debug APK (fast, for testing):** `flutter build apk --debug`
   Install: `adb install build/app/outputs/flutter-apk/app-debug.apk`
6. **Release APK (final distribution only):** `flutter build apk --release`
   Install: `adb install build/app/outputs/flutter-apk/app-release.apk`

## Key file locations
- Migration: `migrate.py`
- Setup: `appwrite_setup.py`
- Cloud Function: `cloud_function/main.py` and `cloud_function/functions/getprice/src/main.py`
- Flutter app: `myinterpreter_app/`
- Original PHP (reference): root + `core/`, `handlers/`, `config/`
- Project guide: `CLAUDE.md`

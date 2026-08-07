# CLAUDE.md

**myInterpreter** — Moroccan stock analysis app (Bourse de Casablanca).

## Stack
- **App**: Flutter (Android), lives in `myinterpreter_app/`
- **Backend**: Appwrite Cloud (Frankfurt) — auth, database, cloud functions
- **Web**: PHP website (repo root) hosted on InfinityFree — <https://myinterpreter.infinityfree.me>
- **CI**: GitHub Actions — builds release APK on every push to master, download from Actions tab

## Cloud functions (`cloud_function/`)
| Function | Schedule (UTC) | Does |
|---|---|---|
| `getprice` | `*/15 8-15 * * 1-5` | Scrapes prices, computes ratios, writes `data` + `latest_prices`, triggers enrichment |
| `dividends` | `0 6 * * 1` (weekly, Mon) | Scrapes the dividend calendar into `dividends`, cross-checks amounts against the fundamentals feed |
| `onboard_company` | on demand | Enriches one company's fundamentals; fired async by `getprice` for new/incomplete listings |
| `cleanup` | `0 16 * * 1-5` | Drops intraday duplicates from `data`, keeping the last snapshot per company |

`cleanup` is deployed but **not declared in `cloud_function/appwrite.config.json`** —
only the first three are. Verify its real schedule with `appwrite functions list`
before trusting the value above.

## Key files
| File | Purpose |
|---|---|
| `myinterpreter_app/lib/appwrite_client.dart` | Shared Appwrite client, endpoint, project ID |
| `myinterpreter_app/lib/main.dart` | Auth gate → Login or Home |
| `myinterpreter_app/lib/dividends.dart` | Dividend model/helpers — mirrors `core/dividends.php`, keep in sync |
| `myinterpreter_app/lib/screens/` | login, home, screener, portfolio, statistics, stock_detail, dividends, buy_sell_sheet |
| `core/Appwrite.php` | PHP curl-based Appwrite REST helper (no Composer) |
| `core/auth.php` | requireLogin(), requireAdmin(), is_admin() |
| `core/dividends.php` | Dividend helpers shared by company page, portfolio and calendar |
| `handlers/market_proxy.php` | Server-side fundamentals fetch; PHP twin of `onboard_company` |
| `config/config.php` | Ratio thresholds, ADMIN_USER_ID, CSRF, company aliases + display names |
| `config/sources.php` | Upstream endpoints — **gitignored**, see below |
| `cloud_function/functions/*/src/sources.py` | Same, per function — **gitignored** |
| `deploy.py` | FTP deploy of the PHP site |
| `watch_errors.py` | Local desktop watcher over the `errors` collection |
| `appwrite_setup.py` | One-time collection setup (already run) |

Website pages: `index.php` (dashboard), `screener.php`, `infoAction.php` (company
detail), `portfolio.php`, `statistics.php`, `dividendes.php`, plus admin-only
`Update.php` and `results.php`.

## Upstream endpoints
Never hardcode a data-provider host or name anywhere tracked by git. Real hosts
live only in `config/sources.php` and each function's `src/sources.py`, both
gitignored; the committed `*.example.*` files carry `example.invalid`
placeholders. Functions fall back to env vars (`MARKET_API_URL`,
`FUNDAMENTALS_BASE`, `CALENDAR_URL`, …) when `sources.py` is absent — see
`.env.example`. Provider names must not appear in UI text, comments, docs or
commit messages either; the exchange itself (Bourse de Casablanca) is fine.

## Appwrite database: `myinterpreter`
| Collection | Access | Purpose |
|---|---|---|
| `data` | `read("any")` | Historical price records — one doc per company per scraper run, plus one MASI doc |
| `latest_prices` | `read("any")` | One row per company, upserted each scraper run — use this for current price lookups |
| `company`, `format` | `read("any")` | Company fundamentals and symbol mappings |
| `dividends` | `read("any")` | One row per company per payment year per type; keyed on `(c_name, type)` within a year |
| `errors` | — | Operational log written by the cloud functions; read by `watch_errors.py` |
| `achats`, `ventes`, `portefeuille`, `benefits` | `read("users")` | User portfolio data, filtered by `user_id` |

All rows in `achats`/`ventes`/`portefeuille` are created with `Permission.read/write(Role.user(userId))`.

## Scraper design
- Inserts one doc into `data` per company per run (historical record)
- Also upserts `latest_prices` — one row per company, always current non-zero price
- Suspended stocks (e.g. PROMOPHARM) get last known price from `latest_prices` fallback — never stores `pa=0`
- `latest_prices` is what portfolio.php and Flutter read for current prices — single fast query
- Fiscal years are **discovered from the data**, never hardcoded. A company's
  published year and its projected year are separate; projections are labelled as
  such and excluded from every ratio.

## Dividends
- A dividend paid in calendar year Y comes from fiscal year **Y-1**. The year on
  a row is the year of *payment*.
- A row is **confirmed** only once the AGM has voted, which the source signals by
  publishing an ex-date. Unconfirmed rows carry a payment *window*, are labelled
  "prévu", and must never render as commitments.
- `div_predict()` estimates an ex-date only for issuers with a regular history;
  it is a prediction, and the UI says so.

## Error monitoring
Cloud functions write to the `errors` collection because Appwrite's own execution
logs scroll away. Severity ladder, mirrored in `watch_errors.py`:

| Level | Meaning |
|---|---|
| `critical` | The site now serves wrong or missing data. Act today. |
| `error` | This run failed but previous data still stands. Act this week. |
| `warning` | Something was suppressed or degraded deliberately. Worth reading. |
| `notice` | Informational record that something unusual happened. |

`critical` and `error` raise a desktop popup; the rest are logged quietly.

The watcher runs automatically as a **systemd user service**,
`~/.config/systemd/user/myinterpreter-watch.service` (enabled, `--interval 300`,
`Restart=always`). It is bound to `graphical-session.target` because the popups
need a desktop session. Not a cron job — do not add one.

```bash
systemctl --user status myinterpreter-watch    # is it alive
journalctl --user -u myinterpreter-watch -f    # follow
tail -f ~/.myinterpreter/errors.log            # the colour-coded log
```

## PHP website (InfinityFree)
- **Host**: InfinityFree — PHP only, no Composer, no Node.js. Serves a JS/AES
  browser challenge, so plain `curl`/fetch gets a challenge page, not the site.
- **FTP**: credentials in `FTP.md` (gitignored), or `FTP_HOST`/`FTP_USER`/`FTP_PASS` env vars
- **Auth**: Appwrite cookie-based sessions — `POST /account/sessions/email` returns empty `secret`; real session is in `Set-Cookie` headers. Stored in `$_SESSION['aw_cookie']`, forwarded as `Cookie:` header.
- **Admin**: `ADMIN_USER_ID = 6a124b8900257649d4c1` — only admin can access Update.php/results.php
- **Deploy**: `python3 deploy.py` (`--dry-run` to preview, `--all` to force, or pass paths).
  It walks the working tree, not git, so the gitignored `config/sources.php` and
  `config/secrets.php` go up with everything else. Never deletes remote files.

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
- A ratio computed from a negative denominator is not a bargain — suppress it, never render it green.
- `core/dividends.php` and `myinterpreter_app/lib/dividends.dart` implement the
  same rules twice. Change one, change the other.
- The `scrapping/` directory is gitignored.
- Gradle cache was removed from `/media/redachen/windows/gradle_home/` — do not recreate locally.
- **statistics.php** FIFO P&L not yet verified with real migrated data — test before relying on it.

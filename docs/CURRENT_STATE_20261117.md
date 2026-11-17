# Current state — 2026-11-17

Authoritative summary of how myInterpreter gets its data today, what runs
automatically, and what is known to be open. Older design documents in `docs/`
describe the migration history; where they disagree with this page, this page
wins.

## Stack

| Layer | What runs |
|---|---|
| Site | PHP 8 on InfinityFree (`myinterpreter.infinityfree.me`), deployed by FTP from `master` via `php-runtime-deploy.yml` / `deploy.py` |
| Database | Supabase Postgres + PostgREST. Service role is read-only on public tables; every write goes through a `SECURITY DEFINER` RPC |
| Automation | GitHub Actions (capture → publish → audit). GitHub disables schedules after 60 days without repository activity; `keepalive.yml` commits weekly to prevent that |
| App | Flutter client in `myinterpreter_app/`, reading the same Supabase project |
| Retired | Appwrite. `core/Appwrite.php` is now a compatibility shim that throws on direct writes and routes reads to Supabase. Anything still calling the Appwrite REST API directly is a bug |

## Data flow

```
casablanca-bourse.com  ─┐
medias24.com           ─┼→ capture (Actions) → snapshot.json/actions.json
cdgcapitalbourse.ma    ─┘        │
                                 ▼
                 service-role RPCs (validate digest, mapping, freshness)
                                 │
      ┌──────────────┬───────────┼──────────────┬───────────────┐
      ▼              ▼           ▼              ▼               ▼
 latest_prices   dividends   market_orderbooks  public.data   format.isin
      │              │           │              │               │
   pages/app      pages/app   company page   charts, MASI,   Medias24 keys
                                              screener, trend
```

`public.data` is the daily history table. It had **no writer** between the
Appwrite scraper retirement and 2026-11-17, which is why charts and the screener
stopped at 21 October while prices stayed current. `apply_exchange_history` now
writes it from the same capture as prices.

## What runs automatically

| Workflow | Schedule (UTC) | Writes |
|---|---|---|
| `exchange-price-publication.yml` | weekdays 16:45 | `latest_prices`, `public.data`, `dividends` |
| `exchange-orderbook-publication.yml` | weekdays every 15 min, 08–16 | `market_orderbooks` |
| `exchange-orderbook-identities.yml` | weekdays 07:40 | `format.isin` |
| `market-health.yml` | daily 06:30 | nothing (audit; exits non-zero on stale prices/history) |
| `exchange-reconciliation.yml` | monthly, 1st 06:17 | stages annual candidates; optional share apply |
| `keepalive.yml` | Mondays 05:00 | `.github/keepalive.txt` commit |
| `database-snapshot.yml` | monthly, 1st 03:30 | nothing in the database; uploads a data-only dump and commits a manifest |

Database snapshots cover the public market tables only. Restoring is manual and
documented in the runbook: an automatic restore into production would be
destructive.

Scheduled jobs are gated by repository variables
(`EXCHANGE_PRICE_PUBLICATION_ENABLED`, `EXCHANGE_ORDERBOOK_PUBLICATION_ENABLED`,
`MARKET_HEALTH_ENABLED`, `EXCHANGE_RECONCILIATION_ENABLED`, `MIGRATIONS_ENABLED`,
`EXCHANGE_WRITES_ENABLED`, `EXCHANGE_DIVIDEND_PUBLICATION_ENABLED`). A missing
variable produces a green no-op run — check it first when a feed stops.

## Freshness contract

- Prices: `latest_prices.date` is the publication time; health fails when it is
  older than `--max-age-days` (7).
- History: one row per company per Casablanca trading day in `public.data`.
- Order books: only changed books are stored; intraday changes kept 7 days,
  then one close per day for 400 days.
- Dividends: combined per company and payment year; `confirmed` means the AGM
  has published the ex-date.

## Repository and deployment

Until 2026-11-17 the repository did not match production: `master` still held
the Appwrite client while the live site ran an uncommitted Supabase rewrite.
That work (547 files, including `core/SupabaseSession.php`-era helpers,
automation modules, migrations, tests and the Flutter client) is now committed
and merged into `master` (merge commit `e3d885e`). Deploying from `master` is
therefore safe again. `design-review/screenshots/` and `research/` stay local
(they are ignored; screenshots can contain signed-in views).

## Known open issues

See [BUGFIX_LOG_20261117.md](BUGFIX_LOG_20261117.md). Remaining highest-impact
items: the dividend `(c_name, year)` unique index conflicts with the per-type
projection writer; the share RPC falls back to a free-text company name; a
replayed share report can revert a newer share count; price rows are stamped at
fetch time; and the dashboard hides a failed load behind zeros.

# Operations runbook

How to deploy, repair and restore myInterpreter. Everything here runs from
GitHub; no local step is required for normal operation.

## Secrets and variables

Repository secrets:

| Secret | Used by |
|---|---|
| `SUPABASE_PROJECT_URL` | every publisher and audit |
| `SUPABASE_SERVICE_ROLE_KEY` | every publisher and audit (`apikey` only when it starts with `sb_secret_`) |
| `SUPABASE_PUBLISHABLE_KEY` | site build/deploy checks |
| `SUPABASE_DB_URL` | migration runner, database snapshots (pooler URL; user must be `postgres.<ref>` on `*.pooler.supabase.com`) |
| `FTP_HOST`, `FTP_USER`, `FTP_PASS`, `FTP_REMOTE_PATH` | PHP deployment |

Repository variables (all must be the string `true` to enable the job; a
missing variable silently skips the job and the run is green):

`EXCHANGE_PRICE_PUBLICATION_ENABLED`, `EXCHANGE_DIVIDEND_PUBLICATION_ENABLED`,
`EXCHANGE_ORDERBOOK_PUBLICATION_ENABLED`, `EXCHANGE_RECONCILIATION_ENABLED`,
`EXCHANGE_WRITES_ENABLED`, `EXCHANGE_APPLY_SHARES`, `EXCHANGE_STAGE_ANNUAL`,
`MARKET_HEALTH_ENABLED`, `MIGRATIONS_ENABLED`.

## Deploy the site

1. `php-runtime-deploy.yml` → *Run workflow*, `apply=false` first (dry run).
2. Re-run with `apply=true` and the file list (default:
   `reconciliation.php core/SupabaseAdmin.php core/SupabaseMarket.php
   core/backend.php core/sidebar.php`). Add any other changed PHP path.
3. `master` now matches production, so a full deploy from the repository is
   safe — it no longer reverts to the Appwrite client.

## Apply a migration

`apply-supabase-migration.yml` → *Run workflow*, set `file` to the path under
`migrations/supabase/`, `apply=true`. Without `apply=true` it validates only.
Migrations are written to be re-runnable. A publisher that reports
`MIGRATION_NOT_APPLIED` (PGRST202) is telling you the RPC has not been applied.

## Run a feed by hand

| Workflow | Inputs | Notes |
|---|---|---|
| `exchange-price-publication.yml` | `symbols` (optional) | Publishes prices, daily history and dividends |
| `exchange-orderbook-publication.yml` | `symbols`, `force` | `force=true` captures outside the session window |
| `exchange-orderbook-identities.yml` | — | Refreshes ticker → ISIN |
| `exchange-reconciliation.yml` | `apply_shares`, `stage_annual`, `symbols` | Monthly; writes only when `EXCHANGE_WRITES_ENABLED=true` |
| `market-health.yml` | `max_age_days` | Read-only; exits non-zero when prices/history are stale |

## Failure signals

- `market-health.yml` fails when `price_stale`, `price_missing`, `price_zero`,
  `history_stale`, `history_missing` or `book_missing` is non-zero. The artifact
  contains `market_health.json`, `books.json`, `history.json` and per-company
  flags.
- `Capture order books` reports `failed`, `empty` and `failures` per symbol.
- Publishers print the RPC result (`applied`, `unchanged`, `skipped`,
  `missing`) and fail on `NOTHING_APPLIED` or `NO_USABLE_PRICES`.
- Reconciliation lists `MISSING_MAPPING` / `SHARE_COUNT_MISMATCH` reasons in
  `market_maintenance.price_publications` (query through the SQL editor).

## Database snapshots

`database-snapshot.yml` runs on the 1st of each month at 03:30 UTC and on
demand. It produces a data-only SQL dump of the **public market tables**
(`company`, `format`, `data`, `latest_prices`, `dividends`, `market_orderbooks`,
`company_profiles`, `market_snapshots`, `market_reference`,
`dividend_source_snapshots`), gzips it, checksums it and:

- uploads it as a workflow artifact (90-day retention);
- commits a small manifest to `backups/db/manifest-YYYYMM.json` with per-table
  row counts, byte size and SHA-256.

Personal data (accounts, portfolios, profiles) is deliberately excluded.

### Restore

Do this in a scratch project or inside a transaction; it replaces the listed
tables.

```bash
# 1. download the artifact from the run page, then:
gunzip -c database-snapshot-YYYYMM.sql.gz > snapshot.sql
# 2. inspect the table order and truncate the same tables first
psql "$SUPABASE_DB_URL" -1 -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
TRUNCATE public.market_orderbooks, public.data, public.latest_prices,
         public.dividends, public.company, public.format,
         public.company_profiles, public.market_snapshots,
         public.market_reference, public.dividend_source_snapshots;
\i snapshot.sql
COMMIT;
SQL
```

The dump is data-only: schema and functions come from `migrations/supabase/`.
Apply migrations before restoring into an empty project.

## Emergency rollback

- Code: revert the commit on `master` and redeploy the previous PHP files with
  `php-runtime-deploy.yml` (`apply=true`).
- Data: restore the most recent snapshot as above, then re-run the price
  publication to catch up.

## What is intentionally manual

- Restoring a snapshot to production. Automatic restore is destructive.
- Approving annual candidates and share updates (`reconciliation.php`).
- Rotating the database password if `SUPABASE_DB_URL` authentication fails.

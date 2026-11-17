# myInterpreter — cloud reconciliation state 2026-11-17

## Where things stand

- `master` carries the reconciliation migration, the admin review page, the price
  publisher and the market-health audit. Service key and RPCs work.
- Share reconciliation applied 16 updates and left 64 unchanged; 47 annual
  candidates are staged and waiting for approval.
- Market health proves the price feed is frozen: all 81 prices were dated
  2026-10-21, 55 fiscal years were 2024, 21 were missing, 16 dividends were
  unconfirmed and 7 shareholder lists were absent.
- The price-publication migration is not applied yet, so
  `apply_exchange_latest_prices` does not exist and `latest_prices` cannot be
  written. The service role only has SELECT on that table.

## Database URL: diagnosis

The stored URL already uses the tenant-qualified pooler user
(`postgres.<project-ref>`), and the workflow now rewrites a bare `postgres` to
that form automatically. PostgreSQL still answers `password authentication
failed for user "postgres"`, which is the tenant's database role behind the
pooler — so the password in `SUPABASE_DB_URL` is wrong, not the username.
Resetting the password and re-saving the secret fixes it; an
alphanumeric-only password avoids URL-encoding mistakes.

## Unblock sequence

1. Apply `migrations/supabase/20261116_exchange_price_publication.sql`.
   - Fastest: Supabase → SQL Editor → paste the file from
     <https://raw.githubusercontent.com/RedaAlami02/myInterpreter/master/migrations/supabase/20261116_exchange_price_publication.sql> → Run.
   - Or reset the database password, then:
     `gh secret set SUPABASE_DB_URL --repo RedaAlami02/myInterpreter`
     with the Session pooler URI, and run
     `gh workflow run apply-supabase-migration.yml --repo RedaAlami02/myInterpreter --ref master -f apply=false`
     then the same command with `-f apply=true`.
   The SQL was compiled and exercised on PostgreSQL 17: the function applies a
   price, records an audit row, rejects a 10x share mismatch and refuses an
   older-than-current date.
2. Publish current prices:
   `gh workflow run exchange-price-publication.yml --repo RedaAlami02/myInterpreter --ref master`
   This captures the exchange universe and calls the RPC. Until the workflow
   variable `EXCHANGE_PRICE_PUBLICATION_ENABLED` is `true`, only manual runs happen.
3. Re-run health and confirm stale prices fall:
   `gh workflow run market-health.yml --repo RedaAlami02/myInterpreter --ref master`
4. Keep the weekday schedule on:
   `gh variable set EXCHANGE_PRICE_PUBLICATION_ENABLED --body true --repo RedaAlami02/myInterpreter`
   The daily job runs at 16:45 UTC on weekdays, after the Casablanca close.
5. Approve the 47 annual rows on
   <https://myinterpreter.infinityfree.me/reconciliation.php> using the new
   select-all box. The evidence is in `docs/ANNUAL_REVIEW_20261117.md`.

## Annual candidates — decision summary

All 47 rows satisfy `bpa = net_profit x 1e6 / shares`,
`roe = net_profit x 1e6 / equity` and `profit_margin = net_profit / revenue`;
equity and revenue are positive throughout. The large year-over-year moves come
from depressed or negative prior-year bases (CMT, RDS, ATH, MNG, T2S, ZDJ) or a
low prior exchange row (IAM). No row needs rejection. Approval writes annual
fields only, never the share count, and recomputes BPA from current shares.

## Still open

1. Review the 35 exceptions: 7 banks, 5 insurers, 16 standalone-account
   companies, 5 stale fiscal years, 2 conflicts (SNA, NRJ).
2. Add the NRJ company mapping before applying its shares or annual row.
3. Historical `data` rows and ratios remain frozen at 2026-10-21. The price
   publisher updates `latest_prices` only; a `data`/ratio publisher or the
   private managed runner is still needed.
4. Legacy `Update.php` and `results.php` still compare the UID in
   `config/supabase.local.php` (`admin_user_id`). Update it only if those pages
   return 403; `reconciliation.php` authorizes through `market_admin.admins`.
5. Do not apply `20261116_public_market_anon_read.sql`; public market pages
   without sign-in were explicitly declined.

## Run IDs

| Run | Purpose | Result |
|---|---|---|
| `43963698404` | Exchange capture and report | success, 82 companies |
| `43976007884` | Apply shares, stage annual | 16 applied, 47 staged |
| `43976023261` | Market health | success, all prices stale |
| `44066487131` | DB URL validate | failed, wrong password |
| `44067790230` | DB URL validate after username rewrite | failed, wrong password |
| `44068004155` | Price publication probe | failed, RPC missing |
| `44068546060` | Review page deploy | success |

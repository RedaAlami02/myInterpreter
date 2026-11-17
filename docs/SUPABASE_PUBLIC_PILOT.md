# Supabase public market pilot

The original five-table pilot below is now supplemented by full profiles,
financial and market snapshots, source calendars, sector references, latest
order books and an admin-only raw archive. See
[ALL_NONPERSONAL_DATA_RESTORE.md](ALL_NONPERSONAL_DATA_RESTORE.md) for the user's
expanded "every non-personal dataset and field" scope and current verification.

Resume guidance: [MIGRATION_HANDOFF.md](MIGRATION_HANDOFF.md). The user now
accepts a fresh account/personal-data reset; legacy user mapping and private
freshness reconciliation are no longer mandatory for that approach.
Implementation is authorized; continue from this completed pilot with fresh
authentication, private portfolios and client integration.

Verified on 2026-10-24. The Supabase destination now has typed public market
tables and a PHP REST reader. The deployed PHP site, Flutter app, authentication,
and Python jobs still use Appwrite. No client configuration or schedules changed.

## Imported tables

| Table | Rows | Mapping |
| --- | ---: | --- |
| `company` | 81 | September public company baseline; numeric fields, nullable fundamentals, fiscal years and estimates remain separate |
| `format` | 81 | Original company names and symbols |
| `data` | 110,067 | All recovered observation IDs, original timestamps, prices, ratios and nulls |
| `dividends` | 350 | September baseline, preserving unknown amounts/dates, estimated date windows and confirmation flags |
| `latest_prices` | 83 | Newest genuine observation per stored series name, selected from baseline quotes and recovered history |

These are **110,662 application rows**, distinct from the 110,668 private staging
documents. Staging also holds fresh source-response objects; those have not been
merged into these application tables. Original payloads and permissions remain
unchanged in private staging. Public columns come exclusively from
`migrations/supabase/market_contract.json`; source-provider fields and original
permission metadata are excluded. The public pages already expose company,
price, ratio and dividend data, but their existing server-side Appwrite keys do
not establish the original collection-level permissions. This migration grants
read access explicitly to the selected public columns and tables.

There are 65,659 company-days, of which 1,968 have multiple observations. No daily
uniqueness constraint or automatic cleanup discards these rows. History indexes
support company/date queries and global recent-history queries. Two historical
series names lack a company-directory entry; they remain intact and require
classification rather than guessed aliases or deletion.

Latest quotes retain their actual source dates. The newest recovered quote is
October 21 at 09:29:37 UTC; the oldest selected series observation is May 25.
These are last-known observations, not a current market feed or verified closes.
Equal-time conflicting prices cause the migration to fail for reconciliation.
None occurred in this import. Dividend source refreshes and the independent
historical-price dataset remain separate pending reconciliation.

## Permissions and verification

All five tables have row-level security enabled, a SELECT policy for `anon` and
`authenticated`, and SELECT-only grants for those roles and `service_role`.
Neither API key is used to grant SQL administrative access. Trusted workers will
need deliberate write grants when their migration is implemented.

The importer checked every normalized value against the destination before
committing its transaction. Numeric fields use PostgreSQL `numeric`; conversion
rejects non-finite numbers, invalid dates, naive timestamps and type coercions.
Negative financial ratios and missing values are preserved. Existing unrelated
tables cannot be replaced; populated pilot tables must match the source to be
accepted on a repeat run. There is no truncation or overwrite of differing rows.
A second live run accepted all five tables as `already_verified`, compared every
typed value again, and left row counts and measured database size unchanged.

The database measured **175,797,939 bytes (175.8 MB)** after API verification,
including private staging, public tables and indexes. This is below the 350 MB
pilot target. It does not establish future storage growth or free-tier egress.

Live role checks ran as `anon`, `authenticated` and `service_role`. Each could
read company data. INSERT, UPDATE, DELETE and private staging access were denied
for every role. Each permission probe used a savepoint that was rolled back
unconditionally, including if permissions had unexpectedly allowed an operation.

Eight live PHP REST comparisons matched direct SQL results and exact counts:
company directory, symbols, recent history, a second history page, company
history, the 2026 dividend calendar, latest quotes, and a date-filtered history
query. They covered **919 returned rows** in total. This proves the PHP/cURL path
from the development environment; actual web-host connectivity and rendered-page
comparisons remain unverified.

## PHP reader and reproducible commands

`core/SupabaseMarket.php` provides `SupabaseMarketReader::listDocuments()` and
`countDocuments()` for these five public tables. It translates the existing
public query-helper JSON, preserves document IDs as `$id`, paginates with a stable
ID tie breaker, and uses only a publishable key. Private collection names,
unapproved fields, oversized page requests and secret keys are rejected. HTTP
errors raise an error instead of being converted into empty market data.

No deployed page imports this adapter yet. The live test passes configuration
through a private stdin pipe rather than command arguments or printed output.
API keys, project addresses, raw response bodies and document contents are not
included in reports.

```bash
# Local source verification and typed mapping; no network writes.
python3 tools/migrate_supabase_market.py

# Transactional public-table import or verification of matching existing tables.
python3 tools/migrate_supabase_market.py --apply

# Role probes roll back; public API probes use GET through PHP/cURL.
python3 tools/check_supabase_market.py

python3 -m unittest discover -s tests -p 'test_*supabase*.py' -v
php tests/supabase_market_test.php
```

Aggregate import, mapping and access reports are in the Git-ignored
`backup_live_recovery_20261022/supabase_market_*_report.json` files.
All 15 Python Supabase regression tests, the PHP adapter checks, PHP syntax
checks, and Python compilation passed.

The first live PHP comparison exposed an incorrect application of compound-filter
quoting to ordinary comparisons. The adapter now URL-encodes literal eq/gt/gte
values, matching the [official filter builder](https://github.com/supabase/postgrest-js/blob/master/src/PostgrestFilterBuilder.ts).
Both a local regression check and the successful live company/date filters cover
the corrected behavior. Read grants and RLS follow the
[Supabase data security model](https://supabase.com/docs/guides/database/secure-data).

## Remaining before switching clients

1. Reconcile fresher source data and recover a current Appwrite export when reads
   become available. Recovery candidates cannot reveal subsequent deletions.
2. Establish explicit legacy-user-to-auth-UUID ownership mapping and determine
   whether private trades or holdings changed after September 19. User accounts
   and hashes have not been exported; do not bind data using guessed identities.
3. Implement and test authentication, owner-isolated private tables and portfolio
   transactions. Integrate PHP and Flutter behind an explicit backend selection.
4. Migrate and observe cloud collectors, email delivery, backup and restore, then
   validate both clients before the final cutover. The PC is not a job host.

# Saved personal-data recovery evidence

Initially investigated October 24, 2026. On October 25 the user clarified that
the backup contains **two real accounts** and both should be preserved, with
assignment to each new login deferred. Both portfolios are now restored to
admin-only Supabase staging and fully verified. No names, emails, passwords,
owner IDs or financial amounts appear here.

## October 25 restore: both owners preserved

All **55 original private records** are now in `migration_stage.documents`,
across four separately identified source datasets. Every complete payload was
read back and matched, including original owners, permissions, dates, quantities,
prices, cost snapshots and P&L. A second, independent read-only verification
passed. Application roles `anon`, `authenticated` and `service_role` have no
schema/table access; staging RLS is enabled without policies. Historical permission
strings are evidence inside inaccessible JSON, not active client grants.

The import is atomic across all four collections, verifies source hashes/counts
before and after writing, preserves original IDs and uses content-based dataset
identity for safe reruns. It changes no Auth identities or application portfolio
tables and does not replay old trades at today's timestamp. No accounts were
combined. Owner→new Auth UUID assignment is explicitly for later, as requested.

```bash
python3 tools/restore_saved_portfolios.py            # local validation/counts
python3 tools/restore_saved_portfolios.py --apply    # isolated recovery import
python3 tools/restore_saved_portfolios.py --verify   # read-only full comparison
python3 -m unittest discover -s tests -p 'test_restore_saved_portfolios.py' -v
```

Ignored aggregate reports are `personal_staging_preparation.json`,
`personal_staging_restore.json` and `personal_staging_verification.json` under
`backup_live_nonpersonal_20261024/`. No raw private data or owner ID is printed.
The original source files remain untouched. The source-selection checks retain
both portfolios even when a holding has incomplete saved trade history.

## Recoverable saved portfolio records

The **September 19 Appwrite backup** contains these private records:

| Collection | Total rows | Saved owner 1 | Saved owner 2 |
| --- | ---: | ---: | ---: |
| Buys (`achats`) | 16 | 13 | 3 |
| Sells (`ventes`) | 4 | 3 | 1 |
| Holdings (`portefeuille`) | 12 | 8 | 4 |
| P&L snapshots (`benefits`) | 23 | 22 | 1 |

Owner labels are placeholders, not verified identities or new account mappings.
All four source files match the original manifest's SHA-256 and byte sizes.
Every private row has an owner identifier. Original files remain untouched;
none of their rows was included in the public Supabase tables. The separate
admin-only staging restore described above now preserves them in the replacement.

Saved buys span January 9–July 27, sells April 23–June 17, and P&L snapshots
February 7–September 2, 2026. These are record dates in the September 19 save;
they do not establish that nothing changed after September 19, or that every
intervening trading/P&L date was recorded.

Quantity-only reconciliation found:

- Owner 1: all saved holding quantities agree with buys minus sells. No invalid
  positive-quantity/price inputs, oversells, missing positive positions, holdings
  without any recorded trade, or duplicate P&L owner-days were found.
- Owner 2: two saved holdings have no corresponding saved trade history. The
  snapshot is useful, but reconstructing it only from the ledger would lose
  positions. No opening trades should be invented to fill the gap.

This is not a full cost-basis/FIFO/P&L validation. Multiple trades share dates;
their within-day ordering has not been established. Preserve both source ledger
and saved holding/cost snapshots until those semantics are reconciled.

## What the older finds add

`stock.sql` contains 12 buys, 3 sells, 8 holdings, 18 P&L records and two legacy
MySQL account rows. Every buy/sell and every P&L business record in this current
SQL dump matches the September backup. All 15 trades match saved owner 1;
none matches saved owner 2. This supports continuity of the migrated portfolio,
but transaction similarity alone does not prove account ownership.

Seven old holding payloads match exactly; one is an older, differing snapshot
and must not overwrite the later holding automatically. The initial Git SQL
version has 27 P&L rows but only 16 distinct business records; those 16 are
already present in the later backup. Its 11 duplicate copies are not additional
unique history. Git copies do not establish new personal trades here.

The August `backup_rename_MANAGER_20260806_161501.json` file has **empty** buys,
sells and holdings sections. Its newly found market observations help public
history; this specific file adds no personal rows. The useful personal source
is primarily the September export, which was already preserved locally.

The legacy SQL includes account/password fields. No credential values were
printed or copied to a new extract. These MySQL accounts are not exported
Appwrite Auth users; no current Appwrite Auth identity/password recovery is
established. Existing tracked SQL history should continue to be treated as
sensitive material.

## How this changes the migration options

A **new Supabase login does not require discarding saved portfolio history**.
After identifying the correct saved owner and destination Auth UUID, a dedicated
private import can retain original dates, quantities, prices, cost snapshots
and P&L under that UUID, with owner RLS intact. Keep provenance/idempotency and
use an atomic import; do not replay old trades through the current-time trading
RPC or assign both owners to whichever account is created first.

The earlier empty-portfolio reset is superseded for recovery scope: both saved
portfolios must be retained. Fresh Auth logins still work independently from
preserving original private data. Before activating records in application
tables, map each original owner to the correct destination account and preserve
the second owner's saved holdings even where trades are missing. Assignment is
deferred by the user; it is not a blocker to continued data/backend work.
Unsaved post-backup changes remain unknown.

Aggregate-only findings are saved in ignored
`backup_live_nonpersonal_20261024/earlier_database_search/personal_backup_counts.json`.
The existing non-personal importers do not select this report or personal tables.
See [EARLIER_DATABASE_BACKUPS.md](EARLIER_DATABASE_BACKUPS.md) for the public-data
search and [SUPABASE_PRIVATE_PORTFOLIO.md](SUPABASE_PRIVATE_PORTFOLIO.md) for the
implemented owner-isolated destination schema.

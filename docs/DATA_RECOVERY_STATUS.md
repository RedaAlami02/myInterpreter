# Data recovery and source refresh status

October 25 update: the user clarified that **both original accounts must be
preserved, with new-login assignment later**. All 55 saved private portfolio
records are now fully verified in admin-only staging. Seven newly found public
backup extracts (including 23 additional market IDs) are byte-verified in the
protected archive. Staging totals are 16 datasets/110,723 documents; archive
totals are 1,797 files; database size approximately 282.9 MB. No owners were
merged and canonical market/application portfolio tables were unchanged.
See [PERSONAL_DATA_RECOVERY.md](PERSONAL_DATA_RECOVERY.md) and
[EARLIER_DATABASE_BACKUPS.md](EARLIER_DATABASE_BACKUPS.md). The older descriptions
of an accepted empty-portfolio reset below are superseded for recovery scope.

Expanded scope: [ALL_NONPERSONAL_DATA_RESTORE.md](ALL_NONPERSONAL_DATA_RESTORE.md).
All non-personal datasets/fields are required. Supplemental company profiles,
full financial charts/tables, complete market responses, sector references,
source calendars and order-book data are now populated as well. Known raw
archives and privacy-screened diagnostics are in protected Supabase storage
tables; the destination now measures approximately 282.5 MB, including 56,756
queryable daily references with explicit quality flags. Original five-table
recovery rows remain unchanged. Consult the expanded ledger for gaps rather
than treating the older five-table counts below as a complete project inventory.
See [DATA_RECONCILIATION.md](DATA_RECONCILIATION.md) for official issuer details
recovered after that checkpoint and dividend-period validation across clients.

Latest checkpoint: [DATABASE_RESTORE_STATUS.md](DATABASE_RESTORE_STATUS.md).
The user prioritized the database before automation. A fresh October 24 live
audit matched all **110,662 public application rows** to the saved Appwrite
recovery with no missing, changed or extra values. Every one of 81 companies has
history. Independent reference comparison identified 725 additional daily-bar
candidates and 364 unresolved price differences; both lists are saved privately.
The exact saved restore is present; source reconciliation/current-data catch-up
is next. Auth and opt-in PHP/Flutter integration are already implemented and tested.

Latest user direction (2026-10-24): a new account and fresh personal portfolio are
acceptable. The feasibility assessment is complete and **implementation is
authorized**; continue building after compaction without asking again. Old
account/private-record export is no longer a hard prerequisite.
See [MIGRATION_HANDOFF.md](MIGRATION_HANDOFF.md) for the authoritative resume
state and [APPWRITE_FREE_REBUILD_FEASIBILITY.md](APPWRITE_FREE_REBUILD_FEASIBILITY.md)
for the completed assessment. The export gaps below remain factual recovery
limits, not blockers to the accepted fresh-start approach.

Updated 2026-10-24. Verified public recovery datasets are in private Supabase staging and typed public market pilot tables. The PHP REST reader has passed live SQL/API comparisons. Production Appwrite data, schedules, billing, and client backend configuration have not been changed.

## Completed

| Dataset | Verified result | Local artifact |
| --- | --- | --- |
| Saved application database | All 11 September collection files copied and verified against original hashes, sizes, and row counts, including the private portfolio collections | `backup_live_recovery_20261022/baseline/` |
| Market observations recovered from local Appwrite responses | **110,067 distinct original document IDs**, 65,659 distinct company/day combinations, 83 names including indices and historical naming variants | `backup_live_recovery_20261022/recovered_market.jsonl.gz` |
| Recovery provenance | SQLite integrity/foreign-key checks passed; source capture dates, source hashes, original row payloads and permissions retained | `backup_live_recovery_20261022/recovery.sqlite` and `sources.json` |
| Independent daily history | A verified copy of **56,756 rows for 81 symbols**, 2023-09-22 through 2026-09-18; kept separate from Appwrite observations | `backup_live_recovery_20261022/independent_daily_history.parquet` |
| Current market feed | Successfully fetched **81 ticker rows and 38 stock-detail rows** during the session, plus index and market-status responses | `backup_live_public_20261022/market_snapshot.json` |
| Public dividend calendars | Successfully fetched and parsed **296 source rows across payment years 2022–2026**, preserving raw page evidence | `backup_live_public_20261022/dividends/` |
| Company-fundamentals feasibility check | One company successfully refreshed with 23 computed fields and no reported source-request failures. This is a sample, not a completed universe refresh. | `backup_live_public_20261022/fundamentals_sample.json` |
| Live storage and functions | All 1,686 enumerated private archive files and eight active function source archives downloaded; function settings, variables, and deployment metadata saved | `backup_live_20261022_101401/` |
| Export tooling | Read-only, resumable database/schema/user/team exporter implemented. Live smoke run correctly records quota/scope blockers and does not claim success. | `tools/export_appwrite.py`, `backup_live_database_20261022/summary.json` |
| Supabase private staging | **110,668 records across 12 datasets imported and fully read back**; every payload matches its verified local source. Application roles have no schema or table privileges; both staging tables have RLS enabled without policies. | `backup_live_recovery_20261022/supabase_import_report.json`, `supabase_verification_report.json` |
| Supabase public market pilot | **110,662 typed rows in five tables** verified against the recovery sources; eight PHP REST comparisons passed; all three API roles were denied writes and private staging access | [SUPABASE_PUBLIC_PILOT.md](SUPABASE_PUBLIC_PILOT.md), `backup_live_recovery_20261022/supabase_market_import_report.json`, `supabase_market_access_report.json` |

All recovery and refreshed-data directories are ignored by Git. Private data, function variables, password hashes, and upstream source details must stay there rather than in tracked documentation or commits.

## What “recovered” means

Market recovery starts with the verified September 19 export and processes 1,165 local raw Appwrite response files, totaling approximately 932 MB. It selects the latest server revision per original document ID, using capture time as the tiebreaker. It preserves complete documents without recalculating financial values or changing permissions.

The recovered market observations begin **2023-05-29 15:30 UTC** and end **2026-10-21 09:29:37 UTC**. The latest local response was captured at 09:30:31 UTC on October 21. This is not a complete October 21 closing snapshot.

Saved observations cannot reveal which records were later deleted by Appwrite cleanup. The recovery copy can contain intraday rows no longer present in the live database. It is a recovery candidate with provenance, not an exact current database snapshot. Reconcile it or explicitly select daily records before production use.

The 2027 calendar attempt failed validation. It must not be interpreted as zero dividends or overwrite existing projected records. Current source calendars also need issuer mapping, duplicate handling, and confirmation-state review before import; their 296 raw rows are not a replacement count for the older 350-row Appwrite dividend collection.

Independent historical prices remain separate because corporate actions, adjustments, and source disagreements require reconciliation. Original intraday observations and historical fundamental snapshots cannot be assumed reproducible from current public APIs.

## What remains private or unavailable

- Private trades, holdings, and portfolio history are only verified as of **September 19**. Whether later user changes exist is pending clarification. Public websites cannot reconstruct these records.
- User accounts and password hashes have not been exported. The current project keys lack `users.read` and `teams.read`.
- The current live database and complete schemas remain inaccessible: Appwrite returns HTTP 402, `limit_databases_reads_exceeded`.
- Full fresh company fundamentals, current database corrections, and post-snapshot user edits have not been reconstructed.
- Public recovery payloads and typed market tables have been restored and verified, including public PHP REST reads. Authentication, private ownership mapping, deployed-client behavior, and reconciliation with current Appwrite data remain unverified.

## Next implementation sequence

Supabase staging was populated on **October 23** using `tools/stage_supabase.py` and `migrations/supabase/001_private_staging.sql`. The import contains **110,668 staging documents across 12 datasets**: recovered market documents, four public baseline collections, and seven newly fetched source-response objects. Source-response objects can contain multiple observations; this is not a count of normalized financial records. Private portfolio collections remain excluded. Ten focused staging, connection, and verification tests pass.

The database measured **125,253,299 bytes (125.3 MB)** after the October 23 staging verification, including **114,401,280 bytes** for staging tables and indexes. On October 24, after adding typed public tables and their indexes, total database size measured **175,797,939 bytes (175.8 MB)**, below the 350 MB initial pilot target. Approximately 174 MB remains to that target. This is not a production growth forecast, bandwidth assessment, or guarantee of free operation. Staging should not be retained indefinitely alongside duplicate production history without measuring the combined size.

`tools/verify_supabase_staging.py` reads every imported payload in a read-only repeatable-read transaction and checks it against the source, including original IDs, permissions, nested fields, and numeric values. JSON object ordering and equivalent PostgreSQL number formatting are ignored. Missing, extra, duplicate, or changed documents fail verification. It also checks schema/table privileges for `anon`, `authenticated`, and `service_role`, table RLS, and absence of staging policies. Reports contain aggregate results, not credentials or document contents, and remain ignored by Git.

```bash
# Local validation only: does not connect to Supabase.
python3 tools/stage_supabase.py

# Create private staging or verify existing dataset counts without duplicates.
python3 tools/stage_supabase.py --apply

# Read back every payload and verify staging isolation without remote writes.
python3 tools/verify_supabase_staging.py
```

The importer verifies that the database connection belongs to the configured project and requires TLS. Dataset identity is content-based, so repeating the same import verifies the saved counts rather than adding duplicates. Staging receives no application-role grants; the import performs an explicit access check after loading. No application tables or auth accounts are created in this phase. Connection tests accepted both configured API keys, confirmed client TLS and read-only SQL execution, and printed no credential values.

A second live import run recognized all 12 datasets as `already_verified`, retained the same 110,668 records, and left measured database size unchanged. The saved import report describes this successful repeat run; the separate verification report records the complete payload read-back.

1. Private staging and public market tables are populated and verified; the PHP public reader has passed live checks. See [SUPABASE_PUBLIC_PILOT.md](SUPABASE_PUBLIC_PILOT.md) for mappings, freshness limits, tests and pending client integration.
2. Keep recovered original documents and newly fetched source data distinguishable. Generate normalized destination records with source and observation timestamps, and validate financial/date rules before import.
3. Refresh all company fundamentals with bounded concurrency only after the sample and reviewed local corrections are reconciled. Preserve fiscal-year selection and projection separation.
4. Reconstruct current prices using the full ticker universe, genuine current stock observations, and explicitly dated last-known values where necessary. Do not manufacture zero prices or closing prices.
5. Preserve private portfolio data separately, confirm post-September changes, and map original owner IDs explicitly when creating destination auth accounts.
6. When Appwrite reads return, run a fresh complete export to reconcile missing updates/deletions. Use `--resume` for an interrupted snapshot; a new timestamped directory is appropriate when starting a newer inventory.

## Reusable commands

```bash
# Local recovery only; does not contact Appwrite or public sources.
python3 tools/recover_appwrite_market.py

# Capture current public market data and calendar pages without backend writes.
python3 tools/refetch_public_data.py --output backup_live_public_NEW_TIMESTAMP

# Export all discoverable databases, schemas/documents, users and teams.
# Uses .appwrite-export-key first, then existing scoped project key files.
python3 tools/export_appwrite.py --output backup_live_database_NEW_TIMESTAMP

# Resume verified pages after an interruption.
python3 tools/export_appwrite.py --output backup_live_database_NEW_TIMESTAMP --resume

# Focused recovery and exporter regression checks.
python3 -m unittest discover -s tests -p 'test_*appwrite*.py' -v
```

Live smoke verification on October 22 produced no database pages and accurately recorded the quota and missing auth scopes. A key with sufficient read scopes is necessary for the complete export; it cannot remove the quota by itself. The positive export path has regression coverage but remains unverified against the locked live database.

A fresh October 24 attempt in `backup_live_database_20261024_recheck/` confirmed
the same blockers: database HTTP 402, and user/team HTTP 401 with missing
`users.read` / `teams.read`. No current database or identity pages were exported.
The ignored `.appwrite-export-key` file is prepared but has no configured key.
The user was asked to supply a temporary read-only key or report that Console
access to API Keys is also blocked. The exporter now captures users and teams
first and prioritizes the four private portfolio collections before market
history. Eleven exporter regression tests pass, including account capture while
database quota is blocked and private-collection ordering. A support request
for a temporary export allowance or assisted export, including account access,
is ready in [APPWRITE_EXPORT_ACCESS_REQUEST.md](APPWRITE_EXPORT_ACCESS_REQUEST.md).
It has not been sent, and billing has not been changed. The earlier priority to
restore current private records/accounts was subsequently superseded by the
user's acceptance of a fresh account and personal-data reset.

The saved incremental response files contain **963,192 returned rows captured during the current billing cycle**, including repeated observations. This is evidence of substantial research-sync read volume, not a complete or definitive reconciliation of the Appwrite usage meter.

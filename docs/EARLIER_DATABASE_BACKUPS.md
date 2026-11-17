# Earlier database saves found in this project

Searched October 24, 2026 after the user recalled importing/saving the database
once or twice. This was a local investigation: no SQL was executed, no migration
script was run, and no Appwrite/Supabase records were changed. Personal rows
were excluded from the saved public extracts; source files remain intact.

Personal-data follow-up: [PERSONAL_DATA_RECOVERY.md](PERSONAL_DATA_RECOVERY.md).
The September export has recoverable private portfolio records across two
owners; the August rename file's personal sections are empty. Current private
restore status is documented there and in the October 25 continuation below.

**October 25 continuation:** both saved portfolios have now been imported and
fully read back in separate admin-only staging datasets (55 records, two owners).
The user explicitly deferred new-login assignment. Seven public-only extracts
from the older SQL/August backups are also now byte-verified in
`recovery_archive.files`, preserving the 23 additional original market records,
old quote, mapping field and price variants. Canonical market tables, latest
quotes and cleanup markers remain unchanged. The earlier local-only search
description below records the investigation before these imports.

```bash
python3 tools/archive_earlier_backups.py             # local validation/extraction
python3 tools/archive_earlier_backups.py --apply     # protected archive only
```

The durable `tools/legacy_sql_reader.py` parses only company/data/format literal
INSERTs, supports explicit/implicit column order and exact decimals, and executes
no SQL. Statement-aware parsing excludes private literals even when they contain
SQL-like text. Mixed original SQL/account tables are not uploaded by this tool;
the newly generated public extracts live in ignored
`backup_live_nonpersonal_20261024/earlier_database_archive/`.

## Relevant finds

| Project artifact | Verified contents | Comparison with the current recovery |
| --- | --- | --- |
| `backup_live_20260919/` | Eleven Appwrite collections, 80,555 total documents; public tables include 78,739 market rows, 81 companies, 81 mappings, 350 dividends and 82 saved last prices | Already used as the baseline for the existing recovery and Supabase restore. The original also contains personal sections; do not upload it indiscriminately. |
| `stock.sql` | Legacy MySQL dump: 1,978 market rows, 81 companies and 81 symbol mappings; market dates January 2–May 22, 2026 | 1,912 rows have the same company/day/price somewhere in recovered history; 64 have a different price on a recovered company-day; two use the old `DELETE` cleanup name. No additional mapped company-day was found. |
| `migrate.py` | MySQL-to-Appwrite migration code | Reads company/data/format and personal tables. Its format query selects only `NAME, SYMBOL`, omitting the SQL dump's extra `TINCKER_CODE` field. Script presence establishes the migration path, not proof of a completed historical run. Do not execute it during this investigation. |
| `backup_rename_MANAGER_20260806_161501.json` | Before-rename snapshot: 907 market rows, one company, one mapping, one last quote, plus personal sections | **23 original market IDs and one old quote ID are absent from the current recovery.** 884 shared market IDs show `MANAGER` becoming `MANAGEM`. |
| `backup_company_20260806_223153.json` | 81 Appwrite company documents | All IDs are already present; 61 older revisions and 20 identical update timestamps. No newer revision found. |
| `backup_delete_rows.json` | One old mapping and one market document under `DELETE` | These IDs are absent; this is cleanup evidence, not a company to resurrect. |

The 23 additional before-rename market records are from **August 6, 2026,
09:01:04–15:00:53 UTC**. That company-day is already in recovered history.
None has an identical business payload after allowing for the verified name
change; 22 have prices not present among that day's retained `MANAGEM`
observations. These are additional saved intraday snapshots, not 23 newly
recovered trading days, and are not automatically price corrections. Later
cleanup may explain why they are absent. Their original IDs/values are retained
in the ignored public-only extract pending archival restoration/reconciliation.
The old quote must not replace the October last-known quote.

`stock.sql` also retains **81 populated `TINCKER_CODE` values**, a legacy field
absent from the Appwrite `format` contract. Preserve this as original evidence;
do not guess its meaning or expose provider-specific mapping details publicly.
The 64 price discrepancies also remain evidence, not automatic corrections.

## Git and backup cross-checks

- `403c2ce` (May 23): `stock.sql` is byte-identical to the current file.
- `abdf116` (May 22): the dump format differs, but parsed public tables are
  identical to the current file. This version uses implicit INSERT column order.
- `2e77a31` (May 22): 939 price rows, all present in the current SQL dump; 162
  company rows representing 81 names, with every company payload matching the
  current dump (duplicates, not additional financial variants).
- `backup_20260528_234926/` and `backup_20260528_235019/` are empty.
- `backup_live_20260806_180800/` contains website/CSS backups, no database dump.
- The September safety archive contains design files, no candidate database
  files. All refs in its repository bundle point to commits already available
  in the current repository.

The inventory included ignored/hidden project files and Git history, excluding
dependency/build trees. It does not establish that no backup exists elsewhere
on the computer or in an external account.

## Saved evidence and next migration step

Ignored directory: `backup_live_nonpersonal_20261024/earlier_database_search/`:

- `candidate_inventory.json`: local candidate paths/sizes.
- `legacy_sql_comparison.json`: source hashes, counts and comparison results.
- `*_public_tables.json`: only explicitly selected legacy company/data/format
  records; no account/trade/portfolio tables.
- `*_market_candidates.json`: SQL discrepancies and unmapped cleanup records.
- `rename_public_tables.json`: public-only rename snapshot, with ownership
  permissions omitted and original mixed-file hash recorded.
- `rename_backup_comparison.json`: ID/name/price comparison summary.
- `inspect_legacy_sql.py`: reproducible local parser/comparison. It accepts
  literal INSERT values only, validates row/column counts and SQL escaping,
  reads implicit columns from CREATE TABLE, and executes no SQL.

The newly found public artifacts are now preserved in the protected archive.
Further classify the 23 original market IDs, 64 SQL price differences and legacy
mapping field before considering changes to canonical application history.
Preserve the previously
audited recovery as an immutable reference; do not silently mutate its counts
or restore deliberate cleanup markers. No credentials or personal data belong
in tracked documentation or public projections.

# Complete non-personal data scope

Non-personal scope: **every dataset and field**, not
only the original five public tables. This supersedes the narrower dataset list
in the earlier database checkpoint. Work is in progress; do not claim the locked
latest Appwrite database has been fully reproduced.

**October 25 public archive continuation:** [EARLIER_DATABASE_BACKUPS.md](EARLIER_DATABASE_BACKUPS.md).
An August rename backup contains 23 market IDs and one old quote ID absent from
the current restored set. Legacy SQL preserves an extra mapping field and price
variants. Seven public-only extracts are now byte-verified in Supabase's protected
archive. They preserve this evidence without changing canonical tables/latest
quotes or resurrecting cleanup markers. Existing canonical restore counts remain
valid for their original selected inputs; reconciliation is separate from archiving.

The user also explicitly asked to preserve **both original users' portfolios**
and assign new logins later. Their 55 complete records are now verified in a
separate admin-only staging area. They are excluded from the public/non-personal
archive pipeline. See [PERSONAL_DATA_RECOVERY.md](PERSONAL_DATA_RECOVERY.md).

Latest continuation: [DATA_RECONCILIATION.md](DATA_RECONCILIATION.md) records
queryable daily history, recovered official issuer details and dividend quality
handling. Current database size is approximately 282.9 MB after the October 25
private-staging/public-archive continuation.

## Restored and verified so far (2026-10-25)

- The original five public tables retain all 110,662 verified recovery rows.
- MASI: 1,425 observations across 842 days, May 29, 2023–October 21, 2026.
- New `public.company_profiles`: 81 symbol profiles, with full accessible annual
  tables/charts, forecasts kept distinct from reported years, quarterly/interim
  tables, descriptions and shareholder data. Five symbols do not match the current
  source registry: BAL, DIS, REB, SAM, ZDJ. Their sector/shareholder details were
  subsequently recovered through dated official issuer records; financial
  histories remain missing from that source. Retained baseline data is preserved.
- New `public.market_snapshots`: both earlier and fresh complete market responses,
  preserving MASI/index breadth, capitalization, volume, trade/issuer counts,
  year highs/lows, session state, stock details, tickers and untruncated charts.
- New `public.market_reference`: sector catalog, issuer classifications, publication
  date and reviewed public issuer disclosures.
- New `public.market_orderbooks`: latest reconstructed snapshots for 81 symbols.
- New `public.dividend_source_snapshots`: five original source calendars for
  2022–2026 (296 rows), separately from the 350 canonical recovered dividend rows.
- New `public.daily_price_reference`: all 56,756 independent daily rows for 81
  symbols, retaining numeric fields/nulls, provenance and measured quality flags.
  Date-only references remain separate from original ticks and ratios.
- Admin-only `recovery_archive.files`: original 1,686 order-book files containing
  136,562 full snapshots; original file metadata; complete captured source JSON;
  raw calendar evidence; independent 56,756-row history parquet; privacy-screened
  1,167 diagnostic records. Every selected file was verified byte-for-byte after
  restoration. Function variables/sources, auth and personal collections are excluded.

At the latest aggregate verification there were **1,797 archived files**,
**33,932,670 original bytes**, and total database size **282,932,915 bytes**. Later
capture revisions may add preserved archive versions; consult the current ignored
reports rather than treating these figures as immutable.

The earlier bulk import verified 1,789 selected files plus a previously verified
superseded capture. The October 25 continuation byte-verified seven additional
public-only backup extracts. Superseded evidence is retained.

| Non-personal content | Verified populated coverage |
| --- | ---: |
| Original recovered public rows | 110,662, unchanged |
| MASI | 1,425 observations / 842 days |
| Company profile records | 81 |
| Descriptions / sectors / public shareholder disclosures | 74 / 81 / 80 companies |
| Annual financial charts / full statement tables | 61 companies |
| Quarterly / interim data | 59 / 57 companies |
| Complete market/index responses | 2 captures; all 30 index fields retained |
| Source dividend calendars | 5 payment years / 296 source rows, separately preserved |
| Known order-book archive | 1,686 files / 136,562 full snapshots |
| Reconstructed latest order books | 81 symbols |
| Independent historical-price archive / queryable references | 56,756 rows, full parquet and typed reference table preserved |
| Official supplemental issuer records | 5, with original disclosure dates |
| Non-personal diagnostics | 1,167 records |

Counts distinguish populated values from empty source responses. Missing source
fields are not fabricated. Public shareholder disclosures are market information;
the user's personal account, holdings, trades and P&L are excluded.

Field-by-field source inventory is saved in ignored
`backup_live_nonpersonal_20261024/completeness_inventory.json`. All original
business fields are accounted for. Original provider/permission metadata remains
in protected staging rather than being exposed as public columns. All raw captured
tables—including metadata not used in charts—are retained in the protected archive.

Public supplemental tables have RLS and SELECT-only grants. Raw files remain
unavailable to `anon`, `authenticated` and `service_role`. Anonymous REST reads
passed for all six supplemental tables. The actual PHP financial aggregator
successfully loaded annual charts, reviewed 2025 figures and interim periods
from Supabase. In Supabase mode it reads captured profiles instead of fetching
those tables from upstream on each page request.

## Known gaps and active follow-up

- **Resolved:** LHM changed its source registry name. Its financial history was
  recovered through the verified saved issuer-name alias. The current display
  name remains intact; lookup identity/provenance and both captures are retained.
- Five unmatched symbols and banks with no published corporate tables need
  financial source alternatives. All five now have official sector/shareholder
  records; missing financial histories remain explicit. Do not overwrite retained
  Appwrite scalar fields with nulls.
- The restored baseline lacks latest cloud corrections and post-October-21 price
  history. The independent archive comparison identified 725 daily candidates
  and 364 different overlap prices. References are now separately queryable;
  724/725 absent days have no positive activity evidence. 16,489 source OHLC
  ranges are inconsistent and flagged. Canonical prices remain unchanged.
- The restored dividends include 45 payment-year conflicts, 43 labeled 2027
  with 2025 dates. Client projections withhold those financial claims and mark
  them for review; original records remain intact and replacement claims need
  dated evidence. Collector validation prevents reinserting conflicting periods.
- Full current database/schema/bucket discovery and original collector run/batch
  database records remain inaccessible under Appwrite quota/scope restrictions.
  Saved objects and reconstructed latest snapshots are preserved; unavailable
  original operational rows must not be invented or counted as recovered.

Some source gaps also existed in the baseline; they are not evidence of rows
lost during transfer. Every saved public row was restored and matched. The
unavailable latest cloud inventory and unsaved later changes are the remaining
barrier to claiming an exhaustive copy of the current Appwrite project.

User accounts, passwords, old personal trades/holdings/P&L remain excluded from
the replacement, per the accepted reset. Original local backups are retained.
Diagnostic export removes permission ownership metadata, omits personal records
when detected and redacts recognized credentials; the checked baseline required
no record omissions or credential redactions.

## Code and reproducibility

```bash
python3 tools/capture_nonpersonal_data.py
python3 tools/reconcile_profile_aliases.py
python3 tools/restore_nonpersonal_data.py             # local validation
python3 tools/restore_nonpersonal_data.py --apply
python3 tools/check_supabase_supplemental.py            # read-only live checks
python3 tools/restore_daily_reference.py                # local validation
python3 tools/restore_daily_reference.py --apply
php tools/audit_dividend_quality.php
python3 tools/refresh_recovery_inventory.py
python3 -m unittest discover -s tests -p 'test_restore_nonpersonal_data.py' -v
```

Captures and reports are Git-ignored under `backup_live_nonpersonal_20261024/`.
The capture tool preserves the complete raw responses behind the existing
enrichment adapter, reusing its audited year-selection calculations; it performs
no Appwrite or destination writes. It uses one company at a time with the
adapter's bounded eight-request concurrency and sanitized progress output.

`004_nonpersonal_archive.sql` installs the isolated archive and five supplemental
tables. Import uses verified file manifests, a transaction/advisory lock, unrelated
object guards, full read-back and the existing 350 MB recovery size target. It
never changes the five original recovery tables. Source refreshes and reviewed
filings are explicitly distinguishable from original Appwrite baseline data.
`005_daily_reference.sql` adds the separately verified date-only reference table.

`supplemental_contract.json` is separate from the original five-table contract
so existing import/audit semantics remain stable. PHP reads both contracts;
the generated Dart allowlist covers both. Deployment includes both JSON files.
All 26 Flutter tests and app analysis passed after adding the supplemental
data boundary. The previously built APK predates these latest reader additions;
device testing and production deployment remain pending.

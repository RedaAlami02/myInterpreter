# Database restoration checkpoint

Verified 2026-10-24 at the user's request to prioritize the old Appwrite data
before continuing background-job work. This is the current data work entry point.

Scope was subsequently clarified to **all non-personal data and fields**.
Read [ALL_NONPERSONAL_DATA_RESTORE.md](ALL_NONPERSONAL_DATA_RESTORE.md) for the
expanded tables, complete MASI/profile/financial coverage, archive restoration
and unresolved source/cloud-inventory gaps. The five-table audit below remains
valid for that saved baseline; it is not the whole restored scope anymore.
Latest continuation: [DATA_RECONCILIATION.md](DATA_RECONCILIATION.md), including
56,756 queryable daily reference rows, official issuer gap recovery and 45
dividend-period conflicts quarantined in the client projection. Current database
size is approximately 282.5 MB; original five-table values remain unchanged.

## What is already populated in Supabase

The recovered public Appwrite data is in real application tables, not only local
files or an empty schema. A fresh read-only, repeatable-read SQL reconciliation
compared every restored typed value and original ID with the verified recovery
files. It found **zero missing, extra or changed rows**:

| Application table | Rows verified | Saved source |
| --- | ---: | --- |
| `company` | 81 | September 19 company export |
| `format` | 81 | September 19 name/symbol export |
| `data` | 110,067 | Latest saved revision per original market document ID, recovered from the baseline and local Appwrite responses |
| `dividends` | 350 | September 19 dividend export |
| `latest_prices` | 83 | Newest genuine retained observation per original series name |
| **Total** | **110,662** | Fully matched during the live audit |

All **81 companies** have a symbol mapping and history. Each has a retained
October 21, 09:29:37 UTC observation. Per-company history contains 542–1,422
observations. History spans **2023-05-29 through 2026-10-21** across 83 series and
65,659 company-days, including the index and older naming variants.

No restored price was missing or nonpositive. Original null and negative ratios
were preserved: 57,907 observations have no PER and 5,183 have a negative PER.
Current fundamentals must not be copied backward into these historical nulls.

Private recovery staging still has **110,668 documents in 12 datasets**. Source
hashes, sizes, registered counts and actual staging counts matched. Original
payloads were fully verified in the earlier staging pass; this audit avoided
downloading those duplicate payloads again. Application roles cannot read staging.

Total measured database size is **176,494,259 bytes**, including staging,
application data/indexes and the new private portfolio foundation.

## What this does and does not establish

This establishes complete copying of the **verified saved public recovery**.
It does not establish an exact copy of the locked, latest Appwrite database.
Appwrite's current updates/deletions could not be exported. Some retained
intraday documents may since have been removed by Appwrite cleanup.

The company/dividend baseline is from September 19. Public history ends during
the October 21 session, not at that day's verified close. More recent source
probes are not automatically imported financial records.

The August company backup and additional public research snapshots were checked
for newer original revisions. The August copy was older; the checked research
copies had no new IDs or later company/symbol/dividend/quote revisions relative
to the baseline. They do not provide a newer company export.

The four old personal collections remain in the verified local backup, following
the accepted new-account/empty-portfolio reset: 16 buys, 4 sells, 12 holdings and
23 P&L records. Diagnostic collections contain 1,167 error records and an empty
error log; they are preserved locally rather than exposed as application tables.
No personal backup or Appwrite record was deleted by this work.

## Measured remaining data work

The independent daily-history archive contains **56,756 rows for 81 symbols**,
ending September 18. Its saved hash/size were checked before comparison:

| Comparison with recovered Appwrite company-days | Rows |
| --- | ---: |
| Overlapping company-days | 56,031 |
| Exact close versus latest retained capture match | 55,667 |
| Different close versus latest retained capture | 364 |
| Company-days absent from recovered Appwrite history | 725 |
| Unknown symbols / invalid reference prices | 0 / 0 |

A difference is not automatically an incorrect Appwrite price: the original
capture may be intraday and the reference may use a corporate-action adjustment.
A daily date is not an exact timestamp. None of these rows was inserted into
the tick/history table or used to overwrite an original observation.

Private, Git-ignored reconciliation artifacts:

- `backup_live_recovery_20261022/supabase_recovery_audit.json` — live database comparison and coverage totals.
- `backup_live_recovery_20261022/supabase_company_coverage.json` — per-company history bounds/counts.
- `backup_live_recovery_20261022/missing_daily_bar_candidates.json` — 725 complete reference rows with symbols, company mapping, daily observation kind and source-file hash; no artificial trade timestamps.
- `backup_live_recovery_20261022/daily_price_conflicts.json` — 364 unresolved price differences, retaining original record IDs/timestamps and reference closes.

The restored dividend table contains 60 rows labeled 2027, including 43 inherited
`confirmed=true` flags and 14 unknown amounts. Those flags are **unverified future
payment claims**, not evidence of 2027 AGM approval. The fresh 2027 calendar
parser previously rejected that page. Preserve the original copy and reconcile
these rows before production use; do not silently treat the parser failure as
an empty calendar or the inherited flags as independently confirmed payments.

Core company inputs are retained: BPA, ROE, share count and equity are present
for all 81 companies, growth for 80 and dividend-per-share for 59. Reported fiscal
year is present for 60. These are saved baseline values, not independently
verified current accounts. Bank and unmatched-symbol source gaps remain.

## Priority order from this checkpoint

1. Preserve the verified Appwrite recovery as the immutable reference. All known
   public recovery rows are already copied; repeated imports should not add them again.
2. Reconcile the 725 independent daily candidates and 364 differing prices, with
   explicit daily-versus-intraday provenance and corporate-action handling. Keep
   original observations intact and make source/period semantics clear to readers.
3. Capture and validate missing post-October-21 market days and current quotes.
   Validate coverage against actual observations, not guessed weekday calendars.
4. Reconcile company fundamentals and dividend corrections, especially 2027
   confirmation flags. Preserve unknown values and distinguish annual accounts,
   estimates and historical snapshots.
5. Re-run client/data checks, then resume managed scheduling and cutover work.

Historical intraday/depth records never saved anywhere cannot be guaranteed
reconstructible. Do not describe these aggregate checks as 100% recovery of the
unavailable current cloud database.

## Reproduce the audit

```bash
python3 tools/audit_supabase_recovery.py
python3 -m unittest discover -s tests -p 'test_audit_supabase_recovery.py' -v
```

The audit uses project-bound TLS, read-only SQL and an explicit public-column
allowlist. It contacts no Appwrite endpoints and prints only counts/dates/status.
The five regression tests check changed/missing/extra values, precise numeric
comparisons, duplicate identity rejection and daily/intraday gap classification.

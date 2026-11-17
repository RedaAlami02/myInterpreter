# Non-personal data reconciliation checkpoint

Verified October 24, 2026. Scope remains every recoverable non-personal
dataset/field. Personal accounts, holdings, trades and P&L remain excluded.
Read [ALL_NONPERSONAL_DATA_RESTORE.md](ALL_NONPERSONAL_DATA_RESTORE.md) for the
full inventory and [MIGRATION_HANDOFF.md](MIGRATION_HANDOFF.md) for client setup.

## Additional data now in Supabase

`public.daily_price_reference` contains **56,756 fully verified rows for 81
symbols**, September 22, 2023–September 18, 2026. These separately queryable
date-only observations retain every numeric bar field and null. They do not
replace recovered Appwrite ticks, historical ratios, or last-known prices.
Original source identity/path stays in the protected parquet archive; public
records reference its SHA-256.

| Measured property | Rows |
| --- | ---: |
| Exact reference close / latest recovered price match | 55,667 |
| Different reference close / latest recovered price | 364 |
| No recovered company-day | 725 |
| Inconsistent original OHLC range | 16,489 |
| Zero reported volume | 7,814 |

Categories overlap. Original values remain intact; inconsistent ranges have
`usable_ohlc_range=false`. Adjustment basis and independent close verification
are unknown/unverified. Agreement is not proof of an official closing price.
**724 of the 725 absent company-days have no positive trade-activity evidence**
in this source. Do not count them as missing executions or fabricate ticks.
Only one has positive reported activity; its date/close still needs verification.
Date-only periods never acquire invented trade timestamps. Actual capture times
remain attached to recovered observations used in comparisons.

BAL, DIS, REB, SAM and ZDJ now have official issuer disclosures in
`company_profiles`, with complete HTML byte-verified in the protected archive.
Sector coverage is **81/81**, public shareholder coverage **80/81**, and
descriptions **74/81**. All official characteristics/governance tables and
shareholder disclosure dates are retained. Some dates are many years old;
capture time must not be presented as a new ownership date. Financial capture
time remains distinct. These five issuers remain unmatched in the original
financial-table source; their missing financial histories are not yet recovered.

Latest live verification measured **1,790 archived files / 31,666,518 original
bytes** and **282,457,779 database bytes**, below the 350,000,000-byte target.
Anonymous SELECTs passed for all six supplemental tables; mutation grants are
absent for all three API roles. Actual PHP profile and daily-reference reads
passed. Raw archive access remains admin-only. No personal dataset was imported.

## Dividend defects and client behavior

The audit found **45 payment-year conflicts** among 350 recovered rows:
43 labeled 2027 have both detachment and payment dates in 2025. Two IMMORENTE
INVEST rows labeled 2022/2023 have payment dates in 2021/2022 respectively.

Original records, amounts, dates and flags stay unchanged in the database and
backups. PHP and Flutter use a client projection that marks these records for
review and withholds conflicting amounts/dates/confirmation from income, yields,
history totals and forecasts. Unknown values stay null. The calendar displays
**à vérifier**. A valid December detachment/January payment is accepted;
invalid dates and reversed ranges are rejected.

The Python parser retains invalid raw evidence with `verification_issue`;
the collector skips marked rows and logs the issue before upsert. This prevents
a wrong-year source page from recreating misleading claims. That collector
change is local; no Appwrite function was deployed. All three implementations
share nine regression fixtures. This quarantines conflicting claims; it does
not supply replacement 2027 amounts/dates. The other 17 saved 2027 records remain
unconfirmed.

## Reproduce

```bash
# Offline evidence/quality checks; source URL configuration remains ignored.
python3 tools/capture_issuer_disclosures.py
python3 tools/restore_daily_reference.py
php tools/audit_dividend_quality.php
python3 tools/refresh_recovery_inventory.py

# Explicit destination imports with transactional read-back verification.
python3 tools/restore_nonpersonal_data.py --apply
python3 tools/restore_daily_reference.py --apply

# Read-only live SQL / anonymous REST / PHP integration.
python3 tools/check_supabase_supplemental.py

php tests/dividend_quality_test.php
python3 -m unittest discover -s tests -p 'test_dividend_quality.py' -v
python3 -m unittest discover -s tests -p 'test_restore_daily_reference.py' -v
python3 -m unittest discover -s tests -p 'test_issuer_disclosures.py' -v
```

`capture_issuer_disclosures.py --fetch` fetches only missing configured public
pages with host restrictions, bounded responses, identity checks and resumable
hash verification. Existing evidence is never silently overwritten. The daily
importer rejects duplicate identities/nonfinite values and unrelated tables,
requires project-bound TLS, verifies every typed value, checks RLS/grants and
enforces the size target. Repeat imports verify unchanged rows; differing
existing rows fail instead of being overwritten.

Ignored reports under `backup_live_nonpersonal_20261024/`:
`daily_reference_restore.json`, `dividend_quality.json`,
`supplemental_verification.json`, `completeness_inventory.json`,
`issuer_gaps/manifest.json`. Inventory refresh preserves the original audited
Appwrite field mapping while updating source coverage and quality counts.

Validation passed: 26 Flutter tests/clean analyzer, nine shared PHP dividend
cases, twelve focused Python tests across restore/disclosure/dividend handling,
PHP reader/lint checks, deployment-manifest checks and generated-contract check.
A 24-file scan found none of the configured credential values in implementation
files. No production deployment, release APK, commit or push was performed.
The existing debug APK predates these changes.

## Next work

1. Capture verified post-October-21 observations/current quotes with genuine
   observation timestamps and explicit price/status semantics.
2. Verify the one positive-activity daily gap and investigate source-price/OHLC
   disagreements before treating the reference as authoritative bars.
3. Review replacement dividend periods/amounts using dated evidence.
4. Fill remaining descriptions, one shareholder disclosure and missing issuer
   financial histories through alternative filings where available.
5. Keep inaccessible latest Appwrite inventory/unsaved changes explicit, then
   finish managed scheduling, device tests and cutover.

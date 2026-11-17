# Dividend accuracy and consistency — 2026-11-17

## What was wrong

The `public.dividends` table is the live store behind the dividend page
(`core/dividends.php` reads it through the migrated Supabase adapter). An audit
against the Bourse de Casablanca capture found:

- **60 rows for 2027.** 43 were exact copies of the 2025 row (same amount, same
  ex-date, same payment date) marked confirmed; the rest were undated or dated
  predictions. A 2027 dividend cannot be known in November 2026.
- **3 duplicate 2026 rows.** SALAFIN, TOTALENERGIES and ARADEI each had two rows
  with the same amount and dates, differing only in the type label. The page sums
  amounts, so those companies displayed a doubled total.
- **1 orphan company name.** Six dividend rows used `TOTALENERGIES MAROC`, while
  the company row is `TOTALENERGIES MARKETING MAROC`, so TMA appeared to have no
  dividend at all.
- **2 mislabelled payment years.** IMMORENTE INVEST rows for 2022 and 2023 held
  December 2021 and December 2022 payments.
- **Wrong 2026 values.** MANAGEM showed 5.5 instead of 55 (tenfold), CMGP had no
  amount, and COLORADO, SALAFIN and three type labels differed from the exchange.

Sixteen companies report no dividend because the exchange has no dividend row
for them; they are non-payers, not missing data.

## What changed

Repair migration `20261117_dividend_reconciliation.sql`:

- copied and deleted the 60 future rows (audit: `market_maintenance.dividend_repairs`);
- renamed the six TOTALENERGIES rows;
- relabelled the two IMMORENTE rows to their payment years;
- added `market_maintenance.dividend_publications` and
  `apply_exchange_dividends(snapshot, sha, years)`.

The RPC builds **one row per company and payment year**: amounts are summed
across ordinary and exceptional components, the row keeps the earliest payment's
ex and pay dates, `type` names the components, and `confirmed` is true only when
every component has an ex-date. It deletes duplicate rows for the processed year,
audits every insert, update and duplicate removal, and is idempotent.

`tools/publish_exchange_dividends.py` calls it from the daily capture workflow.
`EXCHANGE_DIVIDEND_PUBLICATION_ENABLED=true` keeps the scheduled run active; the
manual run works without the variable.

`20261117_dividend_constraints.sql` adds the guards that would have caught the
bad rows: one row per company and year, payment year must equal the row year (or
a December ex-date with a January payment), positive amounts, and a confirmed row
must carry an ex-date.

## Result

Run `44076167396`: 7 updated, 3 duplicates removed, 52 unchanged, 0 missing.
Health run `44076935964`: dividends recent 61 (was 60), unconfirmed 2 (was 16,
both genuinely awaiting an AGM), missing 16 (all verified non-payers), stale 4
(INV, CMT, SNP, UMR — the exchange has no newer payment).

MANAGEM now shows 55, CMGP 6.5, SALAFIN 30, COLORADO 3.5, TOTALENERGIES is
attached to its company, and no 2027 rows remain.

# dividends

Weekly scraper for the Casablanca dividend calendar.

Source: `<calendar-host>/calendrier-des-dividendes/annee/YYYY/` — a plain
server-rendered HTML table, no JS and no auth. Verified stable across the
2022-2026 calendars: identical header, exactly 7 cells in every row.

Fills the `dividends` collection, which `dividendes.php`, `portfolio.php` and
`infoAction.php` all read.

## Why weekly, not yearly

The calendar fills in progressively as each AGM votes, roughly March to July.
On 7 August 2026, twelve issuers still had no confirmed ex-date. A yearly poll
would be months stale for a large minority of the market. Weekly costs ~52
executions a year.

## Why we never predict a date ourselves

Measured across 197 company-pairs from five calendars, the year-over-year drift
of the ex-date is a **7-day median**, with 26% of companies moving more than a
fortnight (TAQA moved 87 days; IMMORENTE went from December to April). Our own
guess would be worse than the source's.

The source already distinguishes the two cases: a voted dividend has a real
ex-date and a single payment date, an unvoted one has no ex-date and a payment
*range*. That distinction is stored as `confirmed` and shown in the UI as
"confirmé" vs "prévu". Where a company has no confirmed date, the page falls
back to a habitual **month** drawn from past years — and only when at least 60%
of prior years agree.

Amounts are never predicted either: 51% of dividends move more than 10% a year
and only 25% are unchanged.

## Cross-check

The dividend paid in calendar year Y comes out of fiscal year Y-1, so
the calendar's Y amount should equal the upstream feed's `dpa-corpo[Y-1]`. Verified: CTM 26,
IAM 4, LABEL VIE 120 all match exactly. The function re-checks this each run and
logs a `warning` when the two sources drift more than 2% apart.

## Known quirks handled

* **Duplicate listings.** Some issuers appear twice under two spellings — one
  complete entry, one dateless stub (`AFMA` / `AFMA SA`). Present 2022-2024,
  cleaned up by 2025. `dedupe()` keeps the more complete row; without it the
  portfolio panel would double-count.
* **A company can legitimately have two rows in one year** (ordinary plus
  exceptional), so the collection is deliberately *not* unique on
  company + year.
* **IMMORENTE INVEST pays quarterly.** Its amount is the annual total and its
  payment "range" spans the whole year.
* **TIMAR** appears in the 2022 calendar but is not in our `company` collection
  (delisted). It is reported as unmatched, which is correct.

## Collection setup

The `dividends` collection was created with the CLI — a document-scoped API key
cannot create collections or attributes.

```bash
cd cloud_function
D="--database-id myinterpreter --collection-id dividends"

appwrite databases create-collection $D --name dividends \
  --permissions 'read("any")' --document-security false

appwrite databases create-string-attribute  $D --key c_name       --size 128 --required true
appwrite databases create-string-attribute  $D --key issuer       --size 128 --required false
appwrite databases create-integer-attribute $D --key year         --required true
appwrite databases create-float-attribute   $D --key amount       --required false
appwrite databases create-string-attribute  $D --key ex_date      --size 10  --required false
appwrite databases create-string-attribute  $D --key pay_date     --size 10  --required false
appwrite databases create-string-attribute  $D --key pay_date_end --size 10  --required false
appwrite databases create-boolean-attribute $D --key confirmed    --required false
appwrite databases create-string-attribute  $D --key type         --size 64  --required false
appwrite databases create-string-attribute  $D --key frequency    --size 32  --required false
appwrite databases create-string-attribute  $D --key source       --size 64  --required false
appwrite databases create-string-attribute  $D --key updated_at   --size 32  --required false

# Indexes must wait until the attributes leave `processing`.
appwrite databases create-index $D --key idx_c_name   --type key --attributes c_name   --orders ASC
appwrite databases create-index $D --key idx_year     --type key --attributes year     --orders DESC
appwrite databases create-index $D --key idx_pay_date --type key --attributes pay_date --orders ASC
```

## Backfill

The function only touches the current and next year, since settled years never
change. History came from `backfill_dividends.py` in the repo root — dry-run by
default:

```bash
python3 backfill_dividends.py            # shows what it would write
python3 backfill_dividends.py --write    # commits
```

287 rows loaded for 2022-2026 (53 / 56 / 58 / 59 / 61).

## Deploy

```bash
cd cloud_function
appwrite push function --function-id dividends --activate true
```

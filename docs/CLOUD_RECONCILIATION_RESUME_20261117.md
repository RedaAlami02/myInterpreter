# myInterpreter — cloud reconciliation state 2026-11-17

## Automatic operation

- Weekdays at 16:45 UTC, `exchange-price-publication.yml` captures the exchange,
  publishes prices and reconciles the current-year dividends. Both are gated by
  `EXCHANGE_PRICE_PUBLICATION_ENABLED` and `EXCHANGE_DIVIDEND_PUBLICATION_ENABLED`,
  both true. No local machine is involved.
- `keepalive.yml` writes a timestamp every Monday so GitHub does not disable the
  schedules after 60 days without repository activity.
- Monthly `exchange-reconciliation.yml` applies verified shares and stages annual
  candidates. Daily `market-health.yml` audits freshness without writing.

## Current data state

- Prices: 81 published, `price_stale=0`.
- Dividends: repaired and reconciled. 61 recent, 2 unconfirmed (ADH, LES - waiting
  for an AGM), 16 companies with no declared dividend, 4 stale (INV, CMT, SNP,
  UMR). See `docs/DIVIDENDS_20261117.md`.
- Annual queue: 47 auto candidates plus 29 reviewed rows were staged; the page
  shows the current pending count. All pass the BPA and ROE identities. Evidence:
  `docs/ANNUAL_REVIEW_20261117.md`.
- `SNA` resolved through the action-nominal rule; `REB` margin dropped as noise.
- Five stale fiscal years stay out: DIS (2011), DLM (2021), IBC (2021), INV
  (2023), SAM (2014).
- `NRJ` (JET ENERGY) still needs a company mapping; its row reports 1,050,000
  shares against 13,125,000 implied, a 12.5x difference.

## Database URL

`SUPABASE_DB_URL` authenticates. Validate `44071540279` and apply `44071617554`
both succeeded. Migrations can be applied with `apply-supabase-migration.yml`
and `apply=true`.

## Next actions

1. Approve the remaining staged annual rows on
   <https://myinterpreter.infinityfree.me/reconciliation.php> with select-all.
2. Map NRJ and reconcile its share count.
3. Historical `data` rows and ratios remain frozen; the price publisher updates
   `latest_prices` only.
4. Seven companies still have no shareholder list.
5. Legacy `Update.php` and `results.php` compare the UID in
   `config/supabase.local.php`; update it only if those pages return 403.
6. Do not apply `20261116_public_market_anon_read.sql`.

## Run IDs

| Run | Purpose | Result |
|---|---|---|
| `44069602847` | Daily price publication | 81 applied |
| `44070285419` | Market health | `price_stale=0` |
| `44071540279` | DB URL validate | success |
| `44071617554` | Price migration via psql | verified |
| `44072458281` | Stage review classes | 28 staged |
| `44073193487` | Fresh report, SNA staged | 1 staged |
| `44076077350` | Dividend repair migration | 60 deleted, 8 updated |
| `44076167396` | Dividend publication | 7 updated, 3 duplicates |
| `44076935964` | Health after dividends | 2 unconfirmed, 16 non-payers |
| `44077086510` | Dividend constraints | applied |

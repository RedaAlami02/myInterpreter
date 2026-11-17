# myInterpreter — cloud reconciliation state 2026-11-17

## Automatic operation

- Prices publish automatically on weekdays at 16:45 UTC through
  `exchange-price-publication.yml`, gated by `EXCHANGE_PRICE_PUBLICATION_ENABLED=true`.
  No local machine is involved.
- `keepalive.yml` writes a timestamp every Monday so GitHub does not disable the
  schedules after 60 days without repository activity.
- Monthly `exchange-reconciliation.yml` captures the full universe, applies
  verified shares and stages annual candidates.
- Daily `market-health.yml` audits freshness without writing.

## Current data state

- Price publication run `44069602847`: 81 applied, 0 skipped, 1 missing (NRJ).
  Market health run `44070285419`: `price_stale=0`, `price_ok=81`.
- Annual queue holds **76 pending rows**: 47 auto candidates, 7 banks, 5 insurers,
  17 standalone-account companies. All satisfy the BPA and ROE identities.
  Evidence: `docs/ANNUAL_REVIEW_20261117.md`.
- `SNA` was reclassified after the engine learned to use a capital action's own
  nominal. Its 17,695,150 shares are confirmed by capitalization/price and by the
  2024 action (353,903,000 at nominal 20).
- `REB` no longer carries a profit margin; its revenue is 30 thousand MAD.
- Five stale rows stay out of the queue: DIS (2011), DLM (2021), IBC (2021),
  INV (2023), SAM (2014). The exchange has no newer filing.
- `NRJ` (JET ENERGY) has no company mapping and its annual row reports 1,050,000
  shares against 13,125,000 implied by capitalization, a 12.5x difference. Map
  the company and reconcile the row before applying it.

## Database URL

`SUPABASE_DB_URL` now authenticates. Validate run `44071540279` reported
`Connection OK`, and apply run `44071617554` re-ran the price migration and
verified `apply_exchange_latest_prices`. Future migrations can use
`apply-supabase-migration.yml` with `apply=true`.

## Next action

Approve the 76 staged rows on
<https://myinterpreter.infinityfree.me/reconciliation.php> with the select-all
box. Approval writes annual fields only, never the share count, and recomputes
BPA from current shares. Approving lifts most of the 59 stale fiscal years.

## Still open

1. Map NRJ, then reconcile its share count and annual row.
2. Historical `data` rows and ratios remain frozen. The price publisher updates
   `latest_prices` only; a `data`/ratio publisher or the private managed runner
   is still needed.
3. Dividends: 17 missing, 4 stale, 16 unconfirmed. Shareholder lists missing for
   7 companies.
4. Legacy `Update.php` and `results.php` compare the UID in
   `config/supabase.local.php`; update it only if those pages return 403.
5. Do not apply `20261116_public_market_anon_read.sql`.

## Run IDs

| Run | Purpose | Result |
|---|---|---|
| `44069602847` | Daily price publication | 81 applied, 1 missing |
| `44070285419` | Market health | `price_stale=0` |
| `44071540279` | DB URL validate | success |
| `44071617554` | Price migration via psql | verified |
| `44072388042` | Stage review classes | applied |
| `44072458281` | Stage bank/insurer/standalone | 28 staged |
| `44072539854` | Read RPC with class | applied |
| `44072646277` | Page deploy | success |
| `44073118618` | Margin guard | applied |
| `44073193487` | Fresh report, SNA staged | 1 staged |

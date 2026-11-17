# myInterpreter — cloud reconciliation state 2026-11-17

## Where things stand

- Prices are live again. The price-publication migration is applied and the
  exchange capture run `44069602847` published 81 prices: `applied=81`,
  `skipped=0`, `missing=1`. Market health run `44070285419` now reports
  `price_stale=0`, `price_ok=81`, `price_missing=0`.
- The one missing symbol is the new NRJ listing, which still has no app company
  mapping; add the mapping before its price or annual row can be applied.
- Service key and RPCs work. Share reconciliation applied 16 updates and left 64
  unchanged; 47 annual candidates are staged and waiting for approval.
- Health after the price fix: 81 companies, 1 fiscal year current, 59 stale, 21
  missing; dividends 60 recent, 4 stale, 17 missing, 16 unconfirmed; 7
  shareholder lists missing. Annual approval will lift 47 of the stale years.
- `EXCHANGE_PRICE_PUBLICATION_ENABLED=true`: weekday capture at 16:45 UTC,
  after the Casablanca close.

## Database URL

The URL uses the tenant-qualified pooler user, and the workflow rewrites a bare
`postgres` to `postgres.<project-ref>`. The diagnostic step reports
`password_length=11 percent_encoded=False`, no reserved characters and no query
or fragment, and PostgreSQL still answers `password authentication failed for
user "postgres"`. The stored password is therefore simply wrong; reset the
database password, copy the value from the reset dialog, and re-save the secret.
This only affects future database migrations, not the running site.

## Open items

1. Approve the 47 annual rows on
   <https://myinterpreter.infinityfree.me/reconciliation.php> with the
   select-all box. Evidence and the per-row decision are in
   `docs/ANNUAL_REVIEW_20261117.md`. All 47 pass the BPA, ROE and margin
   identities; approve all.
2. Review the 35 exceptions: 7 banks, 5 insurers, 16 standalone-account
   companies, 5 stale fiscal years, 2 conflicts (SNA, NRJ).
3. Add the NRJ company mapping.
4. Historical `data` rows and ratios are still frozen. The price publisher
   updates `latest_prices` only; a `data`/ratio publisher or the private managed
   runner is still needed.
5. Legacy `Update.php` and `results.php` compare the UID in
   `config/supabase.local.php`; update it only if those pages return 403.
6. Do not apply `20261116_public_market_anon_read.sql`.

## Run IDs

| Run | Purpose | Result |
|---|---|---|
| `43963698404` | Exchange capture and report | success, 82 companies |
| `43976007884` | Apply shares, stage annual | 16 applied, 47 staged |
| `43976023261` | Market health before fix | all 81 prices stale |
| `44068546060` | Review page deploy | success, select-all |
| `44069602847` | Daily price publication | 81 applied, 1 missing |
| `44070285419` | Market health after fix | `price_stale=0` |
| `44070449079` | DB URL diagnostic | password length 11, rejected |

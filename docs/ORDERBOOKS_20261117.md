# Order books: sources, pipeline and retention (2026-11-17)

## Why

The stock detail page could not show a current order book: the stored rows in
`public.market_orderbooks` came from the retired Appwrite-era PC collector, and
the newest one was 22 October. The page also had no depth display, so the gap
was invisible.

The pipeline below captures depth for every listed symbol on every weekday and
publishes it through a service-role RPC. It runs entirely in GitHub Actions.

## Sources verified today (all probes 2026-11-17, Casablanca session)

| Source | Endpoint | Depth | Notes |
|---|---|---|---|
| Medias24 (primary) | `GET https://medias24.com/content/api?method=getBidAsk&ISIN=…&format=json` | **10 bids + 10 asks** | Plain HTTPS, no token, no cookies. Keyed on ISIN. `method=getAllStocks` lists the 76 instruments it covers, with ISIN. |
| CDG Capital (fallback) | `POST https://www.cdgcapitalbourse.ma/api/` action `VALEUR-PROFONDEUR`, `Top_=10` | 10+ levels (up to 20 observed) | Covers all 82 tickers (`TICKER` action). Response items do not echo the symbol, so one symbol per request. |
| Casablanca Bourse (official, for identity/prices) | Server-rendered `drupal-settings-json` on `/live-market/actions` and `?symbol=…&ce=…` | Best bid/ask only | No depth. Gives `instrument_details.isin`, `shares_count`, `nominal_value`; used to map ticker → ISIN. Page uses an incomplete TLS chain; the capture tool completes it via the AIA URL rather than disabling verification. |
| Wafabourse | Same `VALEUR-PROFONDEUR` action | 10 levels | Requires a browser session; not cloud-safe. Not used. |
| BMCE Capital Bourse (HTML) | `/bkbbourse/details/<id>` | 5 levels | HTML parsing only; not used. |

Medias24 does not cover six small caps that CDG does (for example NRJ), which is
why the fallback exists. A symbol failing both sources is reported, never
invented.

**Runner egress:** Medias24 answers `403` to GitHub Actions addresses even with
a browser-faithful request, so in the cloud the capture falls through to CDG for
every symbol (still ten levels). The Medias24 path stays first in code: from an
allowed network — or behind a proxy someone adds later — it is used
automatically. The capture summary records which source served each run.

### Medias24 methods observed in the page bundle

`getAllStocks`, `getBasicStocksInfo`, `getStockInfo`, `getBidAsk`,
`getTransactions`, `getStockIntraday`, `getStockHistory`, `getStockOHLC`,
`getMasiInfo`, `getMarketIntraday`, `getSectorInfo`, `getSectorHistory`,
`getBestPerformers`, `getWorstPerformers`.

## Pipeline

1. `.github/workflows/exchange-orderbook-identities.yml` (weekdays 07:40 UTC)
   captures the exchange universe and publishes `symbol -> ISIN` into
   `public.format.isin`. A contradictory ISIN is recorded as `ISIN_CONFLICT`,
   never overwritten.
2. `.github/workflows/exchange-orderbook-publication.yml` (every 15 minutes,
   08:00–16:59 UTC, weekdays) runs
   `tools/capture_exchange_orderbooks.py`, which:
   - refuses to run outside 08:50–15:40 Casablanca time (manual runs can pass
     `--force`);
   - reads identities from `public.format`;
   - asks Medias24 for every mapped symbol, then CDG for the rest or for any
     Medias24 failure;
   - writes `snapshot.json`, `report.json` and `SHA256SUMS`.
3. `tools/publish_exchange_orderbooks.py --apply` sends the snapshot text and
   its SHA-256 to `public.apply_exchange_orderbooks`.
4. `market_health.book_health` reports `book_fresh` / `book_stale` /
   `book_missing` per symbol in the daily health run.

### What the RPC enforces

- service role only; the submitted digest must match the submitted text;
- every row: valid symbol, known source, `captured_at` within the last 7 days
  and not more than 5 minutes in the future;
- bids strictly descending, asks strictly ascending, at most 20 levels, prices
  in `(0, 1e9)`, non-negative quantities, at least one side populated;
- symbol must exist in `public.format`, otherwise `MISSING_MAPPING`;
- a capture older than the newest stored row is `OLDER_THAN_CURRENT`;
- a book identical to the newest stored one (same content hash) is
  `UNCHANGED` — the archive stores changes, not a poll log;
- every outcome is written to `market_maintenance.orderbook_publications`.

A malformed batch is rejected whole, so a bad capture never leaves half a
session in the archive.

### Retention

`market_maintenance.prune_market_orderbooks(7, 400)` runs on the first trigger
after the close (the 16:00 UTC slot, flagged by `--prune`):

- keep every intraday change for 7 days;
- after that, keep the last capture of each Casablanca trading day;
- delete everything older than 400 days.

At 81 symbols and changes-only storage this stays in the low tens of MB.

## Page contract (unchanged)

`core/company_market.php` reads the newest row per symbol and needs
`snapshot.symbol == symbol` and `snapshot.bids/asks[].price/quantity`. The RPC
writes exactly that shape, plus `source`, `content_hash`, `levels`,
`market_time`, `status` and `phase` for provenance. The page already labels the
book as a recorded snapshot and warns when it is not from today.

## Deployment

1. Apply `migrations/supabase/20261117_exchange_orderbook_publication.sql` in
   the Supabase SQL editor. Until it is applied the publisher reports
   `MIGRATION_NOT_APPLIED` (PGRST202).
2. Set repository variable `EXCHANGE_ORDERBOOK_PUBLICATION_ENABLED=true`.
   `SUPABASE_PROJECT_URL` and `SUPABASE_SERVICE_ROLE_KEY` are already used by
   the price workflows.
3. Run *Exchange instrument identities* once (`workflow_dispatch`) to fill
   `format.isin`, then run *Exchange order-book publication* once with
   `force=true` to verify a snapshot lands.

## Failure signals

- Capture summary lists `failures` with the symbol and error, capped at 20.
- `MISSING_MAPPING` counts symbols absent from `public.format` (NRJ today).
- Health run shows `book_missing` / `book_stale` per symbol in `books.json`.
- Both sources down: capture exits non-zero and publishes nothing.

## Data-rights note

Public accessibility is not a redistribution licence. These captures are for
this site's own display; confirm the exchange's market-data terms before any
commercial redistribution.

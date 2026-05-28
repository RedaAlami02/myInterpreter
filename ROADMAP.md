# myInterpreter — ROADMAP

Local planning file. Not deployed (excluded by rsync `--exclude='*.md'`).

---

## Data stored in Appwrite but NOT yet displayed anywhere

### `company` collection (new fields — populated by sync_companies.php)

| Field | Content | Where to use |
|---|---|---|
| `ext_name` | External registry name | Key for API lookups — internal use only |
| `sector` | corporate / banque / assurance | Screener filter, infoAction header ✓ (if synced) |
| `description` | Company description paragraph | infoAction header ✓ (if synced), otherwise JS-loaded |
| `shareholders` | JSON `[{"name":"RMK SA","pct":65.4}]` | infoAction shareholders chart ✓ (JS-loaded) |
| `beta_3y` | 3-year beta | infoAction fundamentals grid ✓ (if synced) |
| `beta_5y` | 5-year beta | Not shown anywhere yet |
| `revenue` | Latest annual CA (MMAD) | infoAction fundamentals grid ✓ (if synced) |
| `ebitda` | Latest annual EBE (MMAD) | infoAction financial chart ✓ (JS-loaded) |
| `ebit` | Latest annual EBIT (MMAD) | infoAction financial chart ✓ (JS-loaded) |
| `net_profit` | Latest annual RNPG (MMAD) | infoAction grid + chart ✓ (if synced / JS) |
| `fcf` | Latest Free Cash Flow (MMAD) | infoAction financial chart ✓ (JS-loaded) |
| `net_debt` | Latest dette nette (MMAD) | infoAction fundamentals grid ✓ (if synced) |
| `net_cash` | Latest trésorerie nette (MMAD) | Not shown anywhere yet |
| `total_assets` | Latest actif total (MMAD) | Not shown anywhere yet |
| `profit_margin` | Net profit margin % | Not shown anywhere yet |
| `rev_growth_5y` | CA CAGR 5 years % | Not shown anywhere yet |
| `rnpg_growth_5y` | RNPG CAGR 5 years % | Not shown anywhere yet |
| `dpa` | Dividende par action | infoAction fundamentals grid ✓ (if synced) |

### `data` collection (scraper fields — populated every 15 min)

| Field | Content | Where to use |
|---|---|---|
| `data_chart` | 30-day price points `"p1;p2;…\|G"` | Per-stock intraday/30-day sparkline in infoAction |
| `open_price` | Today's opening price | infoAction detail row, screener column |
| `high` | Today's intraday high | infoAction detail row, screener column |
| `low` | Today's intraday low | infoAction detail row, screener column |
| `cours_ref` | Yesterday's closing price | Historical PER denominator check |
| `volume` | Trading volume in MAD | infoAction detail, screener sort |
| `qty_traded` | Number of shares traded | infoAction detail |
| `market_cap` | Market capitalisation | infoAction detail, screener column |
| `variation_v` | Absolute MAD change (e.g. -12.10) | Dashboard table column "Δ MAD" |
| `symbol` | Ticker (ATW, BCP…) | Already used for ticker badges ✓ |
| `variation` | % change today | Already used in screener/dashboard ✓ |

### Financial proxy data (fetched live, NOT stored in Appwrite)

| Data | Endpoint | Where to use |
|---|---|---|
| `sem-corpo` | Semi-annual RNPG (S1/S2) | infoAction semi-annual chart (fetched but not charted) |
| `coursref-corpo` | Annual stock closing price | Historical PER over time in infoAction |
| `inv-ca-corpo` | Capex/CA ratio by year | Capital intensity chart in infoAction |
| `fcf` chart | FCF by year | infoAction FCF chart (fetched but rendered standalone only) |

---

## Features planned but NOT yet implemented

### High priority

1. **Per-stock sparkline in infoAction** using `data_chart` field
   - The 30-day price points are stored per snapshot — render as small inline chart

2. **Screener enhancements** — add columns: Volume, High/Low, market cap
   - Data already in `data` collection: `volume`, `high`, `low`, `market_cap`

3. **Sector filter in screener** — filter by `company.sector` (banque/assurance/corporate)
   - Need to join `company` and `data` tables in screener query

4. **Semi-annual RNPG chart** in infoAction
   - `sem-corpo` data is fetched by market_proxy but not yet charted

5. **infoAction URL by symbol** — `?symbol=ATW` instead of `?name=ATTIJARIWAFA BANK`
   - More reliable, shareable links

### Medium priority

6. **Dashboard watchlist** — sidebar watchlist is currently empty (no nav items)
   - Option A: derive from user's portfolio (top 4 holdings by value)
   - Option B: dedicated Appwrite collection `watchlist` per user
   - Data available: `variation` field per stock in `data` collection

7. **Scraper fallback** — if primary market data source fails, use secondary source
   - Secondary source: `get_all_data` endpoint has same price/variation/volume data
   - Implement in scraper: try primary, except → try secondary

8. **Historical PER chart** in infoAction
   - Use `coursref-corpo` (yearly stock price) + `company.bpa` to calculate PER per year

9. **Dividend yield** — `company.dpa / current_price × 100`
   - Show in infoAction fundamentals grid as "Rendement %"

10. **Save enrichment from Update.php** stores description/sector/beta automatically ✓ (DONE)

### Low priority / future

11. **Price alerts** — notify user when a stock crosses a threshold
    - Needs new `alerts` Appwrite collection + email/push notification integration

12. **Portfolio analytics** — IRR, time-weighted return vs MASI benchmark
    - MASI data now stored per day — comparison is feasible

13. **Analyst projections** display — `2025p`/`2026p` from `rnpg-corpo` and `dpa-corpo`
    - These appear in infoAction financial chart ✓ but could be highlighted more prominently

14. **beta_5y** — 5-year beta stored but not displayed anywhere
    - Add to infoAction fundamentals grid alongside beta_3y

15. **net_cash / total_assets** display
    - Add to infoAction fundamentals grid

16. **inv-ca-corpo** (Capex intensity) — fetched but never shown
    - Could add as a small metric chip in infoAction

---

## Schema: `idb_name` field (legacy)
The field `idb_name` was created in an earlier schema run before the rename.
It's now unused — the correct field is `ext_name`.
Can be deleted from the Appwrite console if desired (no data in it).

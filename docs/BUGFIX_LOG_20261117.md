# Bug log — 2026-11-17

Bugs found while tracing why "synchronized data is always wrong". Items marked
**fixed** are on `master` and, where applicable, verified in production. Items
marked **open** were confirmed by reading the code but are not yet changed.

## Fixed

| # | Defect | Effect | Fix |
|---|---|---|---|
| 1 | `public.data` had no writer after the Appwrite scraper was retired | Every chart, the MASI panel, the screener and Δ% showed 21 October rows while prices were current | `apply_exchange_history` RPC + `tools/publish_exchange_history.py`, run inside the price job. 81 rows written for 2026-11-17; health `history_fresh=81`, age 0 |
| 2 | `keepalive.yml` diffed an untracked file | The guard always exited "No change", so no commit was made and every schedule would have been disabled after 60 days | Stage the file, then `git diff --cached` |
| 3 | Price publisher printed COMPLETE and exited 0 with zero rows applied | All prices could freeze while the workflow stayed green | Fail on `NO_USABLE_PRICES`, and on `NOTHING_APPLIED` when rows were skipped or unmapped |
| 4 | Dividend publication only sent the current UTC year | A prior-year correction was never republished | Default years are now current and previous |
| 5 | Order-book retention could never run | The only prune slot (16:00 UTC) was outside the session window, and the skip branch exited first | Independent prune step + `prune_exchange_orderbooks` RPC |
| 6 | Reconciliation never loaded saved company/format rows | `share_updates` was structurally always 0 and every row looked like a change | `tools/export_reference_rows.py` + `--companies/--format` |
| 7 | Health audit downloaded all of `market_orderbooks` and died past 20 000 rows | The only staleness monitor would fail permanently once retention lagged | Order newest-first, cap rows; report per-company history and book age |
| 8 | Health audit always exited 0 | A failed publication was indistinguishable from a healthy day | Exit non-zero when prices or history are stale |
| 9 | Zero/negative ratios scored as "Attractif" | Missing or loss-making companies were badged green on the results page | `Action::test()` returns `none`; page renders "non applicable" |
| 10 | Order-book levels with zero/fractional quantity | The detail page rejects a whole book on one invalid level | Dropped at capture; sorted, capped at 10 |
| 11 | Repo did not match production | `master` held the Appwrite client; the live site ran an uncommitted Supabase rewrite | Migration work committed and merged (`e3d885e`), 451 tests pass |

## Open — worth fixing next

Severity is impact on displayed data. Line numbers refer to the working tree at
the time of the audit.

1. **Company-page PER uses the reported share count** (`infoAction.php`),
   `$mcap = $price × $company['na']`. After a split the share count is stale and
   PER is wrong by the split factor (MANAGEM 10:1, SOTHEMA, CASH PLUS were hit
   before the same bug was fixed in the scraper). Use the exchange
   capitalisation from the latest `data` row, as the screener does.
2. **Dividend yield has no price-date check** (`dividendes.php`). The footer
   says yields use the day's price; a stale or suspended price is presented as
   today's. Carry `latest_prices.date` and suppress or label old yields.
3. **Annual approval can overwrite reviewed financials**
   (`20261117_roe_guard_and_isolation.sql`). It checks the fiscal year but not
   `market_admin.financial_review_receipts`, which the protection migration uses
   to block later writes. A re-staged stale report can roll corrections back.
4. **One malformed dividend date aborts the batch**
   (`20261117_dividend_reconciliation.sql`). `('' )::timestamptz` or
   `'2025-13-01'` raises and rejects every company and year. Use the existing
   `try_timestamptz` helper and drop unparseable components.
5. **Dividend dedupe deletes components the snapshot never mentions.** A
   partial capture (ordinary only) deletes a stored exceptional row. Delete only
   types present in the snapshot, or merge per type.
6. **Dividend identity mismatch.** `20261117_dividend_constraints.sql` adds
   `UNIQUE (c_name, year)` while the projection publisher keys on
   `(c_name, year, type)`. Either drop per-type rows before writing or index the
   three columns.
7. **Share RPC falls back to a free-text company name**
   (`20261116_cloud_exchange_reconciliation.sql`). A symbol missing from
   `format` updates whichever company matches the string. Require the mapping.
8. **Replaying an old share report can revert `na`.** There is no
   generated-at guard; the audit insert happens after the update.
9. **Price rows are stamped at fetch time**, so a suspended instrument (whose
   quote never changes) is restamped as fresh every publication.
10. **Dashboard swallows a failed load** (`index.php`) and renders "0 sociétés",
    "— PER". A transient outage looks like an empty market.
11. **Screener "previous session"** is the second row of a newest-first window —
    the previous 15-minute run, not the previous session (`screener.php`).
12. **Shareholder names injected into `innerHTML` unescaped**
    (`infoAction.php`) — stored XSS in a signed-in page.
13. **No unique constraints on `company.name` / `format.symbol`**, while updates
    and price mapping select by them.
14. **Order-book receipt counts a replay as applied** (insert uses
    `ON CONFLICT DO NOTHING`, then increments unconditionally).
15. **Suspended symbols have no book** (DIS, DLM, SAM). This is correct data,
    but the health report lists them as `book_stale`; the page shows no book.

## Not a bug, but worth knowing

- The 3 order-book-free symbols above are suspended, not missing.
- NRJ has no `format` row, so its price and book are skipped at publish (same
  mapping gap).
- Medias24 rejects CI egress; CDG serves cloud order books with the same depth.

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
| 12 | Company-page PER used `price × reported shares` | A split made reported PER wrong by the split factor | Market cap taken from the newest `data` row; implied share count survives splits |
| 13 | Dividend yield ignored the price date | Footer promised a yield on today's price; a stale or suspended price was presented as current | Yield shown only when the price is from today (Casablanca); otherwise "—" with the price date as a tooltip |
| 14 | Annual approval could overwrite reviewed financials | A re-staged report for an already-reviewed year replaced `roe/cp/revenue/net_profit` | `20261118_annual_review_guard.sql`: same-year candidates are skipped with `FINANCIAL_PERIOD_REVIEWED` when a review receipt exists |
| 15 | Malformed dividend dates aborted the whole batch | One bad `paiement`/`detachement` rejected every company and year | `20261118_dividend_hardening.sql`: safe cast, unparseable components dropped, rows without a payment date skipped |
| 16 | Dividend dedupe deleted components the snapshot did not mention | A partial capture erased a stored exceptional dividend | Groups whose stored types are not fully covered are left untouched and reported as `skipped_partial` |
| 17 | Dividend index contradicted the projection writer | `(c_name, year)` unique clashed with per-type rows and could not even be built on real duplicates | `20261118_dividend_key.sql`: index moved to `(c_name, year, type)` |
| 18 | Share RPC fell back to a free-text company name | An unmapped or misspelled symbol could update the wrong company | Both share functions now skip unmapped symbols |
| 19 | Replaying an older share report reverted a newer share count | `na` rolled back; every BPA derived from it was wrong | Reports generated before the newest applied one are skipped (`skipped_older_report`) |
| 20 | Prices were restamped with the publication time | A suspended instrument looked freshly priced forever | Capture emits `traded`; untraded instruments keep their stored date (`NOT_TRADED`) |
| 21 | Dashboard hid a failed load behind zeros | An outage looked like an empty market | Visible banner; failure logged |
| 22 | Screener/dashboard "previous" row was 15 minutes old | Δ% labelled as a session change was intraday noise | Previous row selected by trading day |
| 23 | Shareholder names interpolated into `innerHTML` | Stored XSS in a signed-in page | DOM built with `textContent` |
| 24 | MASI chart stopped at 21 October; 1M showed almost nothing | Nothing published the index; the chart had no new points | Daily capture of `/live-market/indices` and MASI/MASI20 rows in `public.data` (`20261118_history_indices.sql`) |
| 25 | Deploying one page without its helpers took `infoAction.php` down | New page required `company_market.php`, `latest_sessions.php` and `current_prices.php` that were never uploaded | Helpers deployed; deploy the full include set when a page changes |
| 26 | MASI history had a month-long hole | Even with daily publication, 1M/3M still had almost no points | `backfill_index_history.py` imported 739 CDG closes (735 applied), replacing 1 267 legacy duplicate rows |
| 27 | Daily valuation was never saved automatically | The official-close path is disabled, so "Valorisation du jour" only changed when the button was pressed — and that path returned DISABLED | New valuation from published closes; autosave once per Casablanca day, a service-role sweep after each publication, and a conservative backfill |
| 28 | Old valuation days were missing | The P&L history had gaps | `valuations-backfill.yml`: 86 days restored (63 since January + 23 in the October gap). Days after a later trade are skipped because today's holdings are not that day's holdings; company closes were backfilled first (57 227 rows) |
| 29 | A market holiday produced a fake session | The public pages keep the previous session's aggregates when closed, so `quantite` looked non-zero; an early-morning run wrote 81 history rows and valuations dated 2026-11-18 | Capture probes CDG `DateCours`; prices, history and order books publish `NO_SESSION` when the exchange's last trade is not today. `20261118_remove_holiday_rows.sql` deletes the fake rows |
| 30 | The holiday rows came back | The purge migration ran at 20:11 while a manually dispatched publication was still in flight; that run wrote 82 rows for 2026-11-18 at 20:15, after the delete | Re-applied the (re-runnable) purge migration on 2026-11-20; `data` for 18 November is empty again |
| 31 | The release app shipped a dead market feed | `MYINTERPRETER_MARKET_PREVIEW` was enabled in the migration commit, but nothing has written `app_feed` since the Appwrite retirement: the Marché tab fell back to a recorded-price list with no ratios, no navigation and no buy action | Build now sets the preview flag off; the screener (prices, PER/PEG badges, company detail, buy sheet) is the market screen again. A Supabase-backed feed is the follow-up |
| 32 | The app showed loss-making PER as a headline | `PER -3.9` on the Marché cards, the same defect the website fixed for its badges | PER line is hidden unless the ratio is positive; regression test in `mobile_review_test.dart` |
| 33 | Dividend position count had no singular | "1 titres" | "1 titre" |
| 34 | One untraded holding blanked the whole portfolio | The totals required every price to share one day; PROMOPHARM did not trade on 2026-11-20, so the website showed "Valeur actuelle —" / "Gain / Perte —" and the app showed "Estimation incomplète" | Value each line at its latest close on or before the day: `20261120_valuation_last_known_close.sql` for the saved valuation, `portfolio_reference_totals` (PHP and Dart) for the display. Only a line with no price at all withholds the total, and the pages state the oldest/newest close used |
| 35 | Saved daily valuation was skipped for the same reason | `value_from_history` demanded an exact-day `data` row and returned `PRICE_UNAVAILABLE`, leaving a hole in the P&L history | Same migration: the lookup is "latest close on or before the day"; the basis stays `HISTORY_CLOSE` |
| 36 | Sector allocation received zero values | `$sectorHoldings` was built with `current_value => 0, has_price => false`, so the sector donut and its per-company values were empty even when prices existed | Pass the computed position value and whether a price was found |
| 37 | Order-book receipt counted a replay as applied | The insert uses `ON CONFLICT (id) DO NOTHING` but `applied` incremented regardless, so re-sending a capture looked like new data | `20261120_orderbook_receipt_counter.sql`: `ROW_COUNT` decides; a replay counts as unchanged |
| 38 | Company and ticker keys were not unique | Updates and price mapping select by `company.name` and `format.symbol`; a duplicate would silently hit the wrong row | `20261120_market_key_uniqueness.sql`; checked first (81/81 rows, no duplicates or blanks) |
| 39 | Signed-out visitors reached market pages | `screener.php` answered an anonymous request with the internal string "Erreur DB : Please sign in again.", and the dividend calendar and the daily-close preview were reachable too | Only `index.php` and `infoAction.php` are public; the screener and calendar call `requireLogin()`, and the preview — a development page — is limited to PHP's built-in server |
| 40 | The app's Marché tab had no feed, and NRJ had no identity | `app_feed` stopped being written at the Appwrite cutover, so the preview answered DISABLED and the app fell back to a flat list; NRJ was missing from `company`/`format`, so its price and order book were skipped at publish | `20261121_public_application_feed.sql` serves the same `app-market-preview/v3` contract from the public tables the site publishes; the app already calls it, with a parser test over a fixture taken from real output. The preview flag is now **on**: the Marché tab was checked on a Galaxy A32 (live quotes, ratios, rating chips, search, navigation). NRJ was created as `JET ENERGY` (`NRJ`, ISIN `MA0000012874`, 13 125 000 shares) and mapped to `ELC` |
| 41 | Every portfolio load called a retired feed | `MYINTERPRETER_MARKET_PREVIEW` was on in the site configuration, so each load spent 288–1200 ms on a shadow-feed RPC that has returned nothing since the cutover | Flag off; the stage disappears and the page is unchanged, because it was already rendering recorded prices |
| 42 | The Marché tab never refreshed, and its quotes expired in place | One fetch at open: an hour later every quote was past its window, so the tab silently swapped itself for the recorded-price list with no way back except pull-to-refresh | `MarketPreviewList` polls every 60 s while mounted, refetches on resume, backs off to 10 min on trouble, and keeps the last good snapshot when a poll fails |
| 43 | The index disappeared from the app | MASI was in the retired Appwrite feed; the public feed joined `format`, which holds companies only, so the app showed 82 stocks and no index | The feed emits `index:MASI` from `data` with `instrument_type INDEX` (no ratios, no symbol in its fields, price rounded to the published two decimals) |
| 44 | The app's market list could not be sorted | The web screener sorts by column; the app was alphabetical only, which 82 rows makes awkward | Sort chips: société, Δ% (desc), PER (asc), cours (desc); the index stays on top and ties fall back to name |
| 45 | The app's Marché tab still read the retired RPC | `read_shadow_application_feed` (and its recurring twin) answer `DISABLED`, so the tab fell back to the dated recorded-price list even with the preview flag on. The previous fix had been applied to `ShadowMarketFeedClient`, which nothing instantiates | `SupabaseBackend.readMarketDisplay()` calls `read_public_application_feed`; the dead `recurringMarketFeed` flag and its build plumbing are gone; `supabase_backend_test.dart` asserts the new RPC |
| 46 | A frozen index and a row named `test` sat in `latest_prices` | Neither maps to a company; the app's after-hours fallback listed a 21 October MASI value as a recorded price | `20261124_remove_orphan_latest_prices.sql` deletes rows with no matching company (2 removed). Indices are served from `data` by the app feed |

## Open — worth fixing next

Nothing outstanding at the time of writing. The 188 KB screener HTML is the
only remaining size problem, and shrinking it means redesigning the table, not
a tweak.

## Not a bug, but worth knowing

- Three order-book-free symbols (DIS, DLM, SAM) are suspended, not missing.
- Medias24 rejects CI egress; CDG serves cloud order books with the same depth.
- The app discards a quote whose capture time is later than the device clock. A
  phone one hour behind (an unsynced Galaxy A32 was) therefore shows the
  recorded-price fallback with no explanation, even though the feed answered
  normally. Auto time corrected it; the fallback message does not say so.

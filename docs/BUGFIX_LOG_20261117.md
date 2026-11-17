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

Severity is impact on displayed data.

1. **No unique constraints on `company.name` / `format.symbol`**, while updates and
   price mapping select by them. Adding them needs a duplicate check first.
2. **Order-book receipt counts a replay as applied** (insert uses
   `ON CONFLICT DO NOTHING`, then increments unconditionally). Reporting only.

## Not a bug, but worth knowing

- Three order-book-free symbols (DIS, DLM, SAM) are suspended, not missing.
- NRJ has no `format` row, so its price and book are skipped at publish.
- Medias24 rejects CI egress; CDG serves cloud order books with the same depth.

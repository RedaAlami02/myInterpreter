# LCP investigation and changes

Commit scope: the performance commit isolates the changes from pre-existing UI work. Its `infoAction.php` batches company/symbol reads and reuses detail data. The directory-specific third parallel price request and price reuse remain in the working tree with the uncommitted directory UI. The measurements below describe the complete working tree, not an isolated checkout of the performance commit.

Measurements taken 2026-10-15; final review 2026-10-18. Changes are local, not deployed.

## Findings

- `dividendes.php`: server response dominates. A separate production diagnostic measured TTFB 4.951 s and LCP 5.264 s, with `P.div-cycle-note` as the largest element. The PHP page waits for year dividends, current prices, banner history, and sequential per-issuer prediction history before emitting HTML. The latter can repeat for an issuer whose prediction is null. There were two distinct unconfirmed issuers in the checked current-year records. This is network/database request latency, not evidence of a slow database execution plan. Browser rendering after TTFB took about 0.31 s in that production sample.
- `infoAction.php`: the local directory's sequential company, symbol, and price reads dominated the baseline: desktop TTFB 0.985 s versus LCP 1.064 s. Production varied considerably: the normal route-order runs were about 2.7 s, while a separate fresh-browser diagnostic had TTFB 0.477 s and LCP 0.856 s. The source bottleneck is established locally, but a precise breakdown of the original production 2.64 s sample is unavailable.
- `index.php`: logged-out rendering is already quick and skips dashboard data loading. The authenticated path performs sequential database reads, paginated five-year MASI history, and a live market-status request with a three-second timeout.
- `portfolio.php`: the public audit follows its redirect to the login page; it does not measure holdings. Authenticated rendering performs sequential holdings, sync-date, earnings, price, dividend, company-list, and FIFO transaction reads. The FIFO tab is rendered even when hidden.
- External font/icon CSS and the font `@import` remain render-blocking work, but the target pages' local timing and the production dividend sample support prioritizing server reads. Neither target LCP element is populated late by JavaScript. No CSS, markup, assets, or financial calculation rules were changed.

## Changes

1. `dividendes.php`: fetch selected-year dividends and prices concurrently with the existing `aw_multi_list_docs` helper. Deduplicate issuers needing prediction history, including null predictions, and fetch histories in batches of at most six concurrent requests. Preserve the 50-row per-company limit and year ordering. On a transport exception in a history batch, fall back to the existing per-company helper.
2. `infoAction.php`: fetch company and symbol lists concurrently, adding current prices to that batch for the directory. Reuse the company list for resolved-company lookup and the symbol map for symbol fallback, avoiding two redundant detail-page requests.
3. `index.php`: fetch recent records and the oldest record concurrently; reuse the recent records' first row for the newest date, eliminating one request.
4. `portfolio.php`: fetch holdings, last-sync record, and earnings concurrently. Preserve each private request's session cookie and `user_id` filter.
5. `statistics.php`: fetch purchases and sales concurrently for the portfolio FIFO panel, preserving session, user filter, ordering, limits, and FIFO calculations.
6. `tools/lcp_audit.mjs`: diagnostic derivative of the user's saved script, with `LCP_ORIGIN`, a ten-second observation window, final URL, ready state, TTFB, and resource completion times. The original script was not edited.
7. `tests/lcp_queries_test.php`: explicit CLI-only, read-only integration check of sequential/parallel public record and prediction equivalence.

## Controlled local before/after

Same local PHP server, live configured Appwrite data, Chromium viewport settings and route order, no throttling. One sample per page/profile per version; these are not medians or field percentiles. The browser cache is reused across routes and between desktop and mobile, matching the original script. Desktop's first page is therefore colder than mobile's first page.

| Route | Desktop before → after | Mobile before → after |
|---|---:|---:|
| index.php, logged out | 0.392 → 0.456 s | 0.048 → 0.048 s |
| infoAction.php, directory | 1.064 → 0.452 s | 0.964 → 0.312 s |
| portfolio.php, logged out redirect | 0.056 → 0.052 s | 0.044 → 0.040 s |
| screener.php, unchanged control | 1.300 → 1.160 s | 1.068 → 1.304 s |
| dividendes.php | 1.260 → 1.004 s | 1.248 → 0.876 s |

Target-page TTFB also fell: dividends desktop 1.192 → 0.942 s, mobile 1.198 → 0.834 s; directory desktop 0.985 → 0.378 s, mobile 0.905 → 0.260 s. Logged-out index/portfolio changes are noise, not measured benefits from the authenticated optimizations.

The complete local-before output is in `lcp-local-before.json`. The after values above were transcribed from the completed audit output; its full resource trace was not persisted before the session resumed.

## Original saved script: production control

Ran `node /home/redachen/ig_transcripts/lcp_audit.mjs` before and after local edits. Both runs hit the unchanged production deployment; the second run is **not** a measurement of the optimized code.

| Route | Desktop first → second run | Mobile first → second run |
|---|---:|---:|
| index.php | 0.580 → 0.604 s | 0.116 → 0.112 s |
| infoAction.php | 2.700 → 2.660 s | 2.720 → 5.744 s |
| portfolio.php, logged out | 0.200 → 0.216 s | 0.216 → 0.192 s |
| screener.php | 1.920 → 1.964 s | 1.816 → 0.720 s |
| dividendes.php | 3.948 → 6.124 s | 5.864 → 5.856 s |

The original script waits four seconds after `Page.navigate` returns; that navigation command can itself wait for the response, so an LCP above four seconds does not by itself invalidate the sample. The diagnostic copy waits longer and records completion/final URL. All controlled local samples reported `ready: complete` and the expected final route (index for portfolio).

## Verification and limitations

- PHP syntax checks passed for all five changed runtime PHP files and the new integration check; Node syntax and `git diff --check` passed.
- `php tests/sector_allocation_test.php` passed.
- `php tests/lcp_queries_test.php` passed against real public records, including both unconfirmed issuers' histories and predictions.
- Before/after server-rendered HTML for the public directory and dividend calendar matched after trimming trailing whitespace. This comparison was completed before the interruption; temporary before-source copies are no longer present after resuming.
- Existing unrelated worktree edits were preserved. No commit, push, deployment, or database mutation was performed.
- Authenticated dashboard/portfolio performance and interactions were not measured. No user account or real holdings were accessed. The detail page's enrichment request and full history are also outside the directory LCP measurements.
- No guarantee is made about production improvement until deployment and repetition of the same audit. Local PHP-to-Appwrite latency differs from hosted PHP-to-Appwrite latency. The existing parallel helper falls back to sequential reads if cURL multi is unavailable.
- Existing query limits, hidden-tab rendering, dashboard history pagination, live market status, and external font/icon dependencies remain potential follow-up work. Shared private-data caching was not introduced.

Reproduce locally:

```sh
php -S 127.0.0.1:8018
# In another terminal:
LCP_ORIGIN=http://127.0.0.1:8018/ node tools/lcp_audit.mjs
php tests/lcp_queries_test.php
```

The runtime deployment scope for this work is `dividendes.php`, `infoAction.php`, `index.php`, `portfolio.php`, and `statistics.php`. Some contain pre-existing user changes, so review their complete contents before deploying them. No production deployment was attempted as part of this task.

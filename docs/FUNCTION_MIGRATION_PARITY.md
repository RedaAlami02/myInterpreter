# Migration parity correction — October 29

**Latest October 30:** [ENRICHMENT_JOB_COORDINATION.md](ENRICHMENT_JOB_COORDINATION.md)
records the tested opt-in enrichment executor, per-company v3 completion,
durable publication retry and remaining fresh-context/new-listing/scheduling
wiring. SQL017 and gateway changes remain local; hosted services stay disabled.

**October 30 update:** read [PRICE_REFRESH_PARITY.md](PRICE_REFRESH_PARITY.md).
The full stock/index row port and enrichment decisions now match the original
job for all 82 saved-capture rows; 230 managed tests pass. The existing preparation
CLI connects these calculations offline. New-listing decisions are also ported.
Application-table publication, hosted enrichment dispatch and recurring execution
remain incomplete. The disabled SQL015/publisher upgrade is already installed;
older staged-only statements below describe the earlier checkpoint.

The owner clarified that this is a migration of the existing website, phone app,
data and functions, not an invitation to replace their architecture. Preserve the
existing behavior and reuse its implementation. Prefer finishing missing parity
over adding general infrastructure. The earlier 80% estimate was not a reliable
measure of usable migration completion.

## Confirmed reuse and omissions

The PHP site, Flutter screens, portfolio calculations and financial rules remain
the existing application with backend adapters. Managed dividend parsing is an
explicit copy of the archival function's rules. Managed fundamentals preserve
the archival enrichment's pure calculations and compare them in tests. Supabase
Auth/storage/data APIs required replacement adapters; the application was not
entirely rewritten. No defensible whole-project reuse percentage has been measured.

However, the initial quote preview omitted an existing price fallback. The original
tracked collector already used this precedence:

1. A returned quote.
2. A price from the full instrument list for stocks absent from the quote view.
3. An original saved last-known price when needed.

That logic exists in Git HEAD as well as the preserved current collector. The
October 29 response already contains positive instrument-list prices for all 17
stocks absent from its quote view. Their instrument entries have no trade dates.
Calling them simply "missing prices" was incomplete: their **fresh quote rows**
were missing, while last-reported display values were available.

## Concrete correction implemented locally

`automation/managed/app_feed.py::build_display_prices()` now ports that precedence
using the existing verified archive, normalizer, identity mapping and quote builder.
This is an opt-in display calculation; it creates no storage framework or tables.

- Existing observed quotes stay first, with their actual dates and stale status.
- Missing quote rows use positive instrument prices labeled INSTRUMENT_REFERENCE.
  Their source event/trade date stays unknown. Capture time is preserved as capture
  time and is never claimed as the time of the last trade.
- An absent instrument price can use an explicitly supplied, original last-known
  record. Its original ID/record date stay visible; future records and wrong-symbol
  matches are excluded. A record date is not invented as a trade timestamp.
- Conflicting prices stay explicit. Missing MASI never uses a stock-price average.
- Fallbacks remain ineligible for predictions and automatic portfolio valuation.
  Full-session acquisition completeness stays INCOMPLETE.
- The accepted `build()` quote-candidate output is unchanged, including its 17
  unavailable quote rows. Original raw bytes and the actual published candidate
  were compared and remain exactly unchanged.

A **local historical replay** of the saved genuine capture now yields display
values for **81 stocks + MASI**: 65 observed quote values (64 stocks + index) and
17 instrument references. This derivation is explicitly labeled a replay and
stored separately; it is not a second genuine capture or a backdated prediction.

**205 managed-worker cases pass**, including 12 new price-fallback cases. Tests
cover precedence, unknown dates, preserved saved identities, no future leakage,
source conflicts, stale display labels, invalid prices, missing index and tampered
archive denial. The first focused test invocation had an import-order error,
corrected before the successful focused/full runs.

This correction is **not deployed or connected to active website/mobile displays**.
The installed services remain disabled. The immutable reviewed runtime bundle was
not rewritten; the working app_feed.py now differs from that older bundle only as
an expected staged change. Repackage/review the actual release delta when needed.

## Existing secondary collectors

The configured collector project exists locally. Its shared source factory
registers **five concrete provider adapters** and has a reusable source router.
Four quote methods call their existing snapshot implementations; one requires
an injected request transport and otherwise explicitly reports it unconfigured.
They are not all newly verified live services. Source identities, native module
paths, class names, domains and identifying aliases remain in ignored private maps.

The additional candidate the owner recalled was not present in the inspected
Python source factory/adapters/scripts. This does not prove it never existed
elsewhere or in earlier research; its working integration remains unconfirmed.
No new provider request was made, and no external collector project was modified.

## Five original website jobs: actual parity state

| Original job | Existing replacement / reuse | Still required |
| --- | --- | --- |
| getprice | Existing recipe/normalization; live archive/shadow path verified; display fallback now ported locally | Connect complete display/ratio behavior to app persistence/readers; restore new-listing and enrichment coordination; recurring execution |
| onboard_company | Original pure calculations copied into managed fundamentals; staged publisher and SQL013 installed off | Verify actual hosted enrichment and original trigger/refresh behavior |
| dividends | Original parser/payment rules retained in managed copy; staged publisher installed off | Positive hosted calendar update and recurring schedule |
| daily_pnl | Existing private financial logic and reviewed SQL012 valuation draft | SQL012 not installed; live daily valuation/schedule not active |
| cleanup | Original job kept only each day's latest row by deleting intraday duplicates | Decide retention for new operational data; never run that deletion against original recovery evidence |

None of these recurring jobs is currently enabled. The presence of collector,
publisher or SQL code is not proof that the old workflow is operational end to end.
Do not describe the whole automation migration as finished.

## Resume in parity order

First finish getprice display/ratio persistence and reader parity from saved data,
then restore its existing enrichment/new-listing coordination. Use existing
provider adapters where appropriate, with explicit price type/time and coverage.
Finish the other jobs against the table above, then verify user-driven signup /
email and app acceptance. Hosted activation and production cutover retain the
agreed scope gates; no permission to repeat the consumed one-capture trial exists.

Private evidence: `private/fallback-trace-20261029/` contains hashed source maps,
local collector/factory inventory, native timestamp-field inspection, historical
display replay and the 205-case regression log. No credentials, source identities
or native endpoints are included in this public-facing handoff.

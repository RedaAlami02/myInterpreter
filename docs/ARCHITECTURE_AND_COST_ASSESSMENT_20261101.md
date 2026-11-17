# Architecture and cost assessment — November 1, 2026

## Recommendation

Improve the existing PHP website, Flutter Android app, Supabase/Postgres backend
and Python automation incrementally. A language rewrite is not the highest-value
next step. Complete reliable data delivery, reduce unnecessary reads, synchronize
client state, and simplify the application boundaries first.

This assessment is based on current source and the latest migration/publication
checkpoints. It does not certify production readiness. No authenticated browser
session, live billing dashboard, fresh database measurement, or physical-device
profile was used. The browser tool failed to connect to its local browser server.
Previously recorded tests are supporting evidence, not tests rerun for this review.

## Existing assets worth preserving

- Supabase integration is already implemented in both clients. Current backend
  selection retires the old runtime rather than offering automatic fallback.
- Atomic/idempotent trade submission, owner-derived database operations, RLS,
  secure mobile session storage, and recovery checks already exist.
- Financial helpers and regression fixtures cover several historical edge cases.
  Current Flutter statistics uses FIFO helpers; older documentation describing
  average-cost statistics is superseded by the implementation.
- Collection, immutable archives, projections and durable retries have substantial
  implementation and synthetic verification. Activation and real acceptance are
  distinct outstanding tasks.
- Existing responsive web styles, local translation catalogs, and native Flutter
  navigation can be improved without discarding them.

The latest migration checkpoint records website publication and a genuine first
owner login/portfolio claim. Mobile/device acceptance, remaining authentication
flows, fresh jobs, and verified official-close valuation remain separate work.

## Website evaluation

| Finding in source | Benefit of changing it | Suggested change |
| --- | --- | --- |
| Root pages mix requests, data transformation, markup and embedded scripts; company detail is 1,212 lines and dashboard 950 | Smaller changes become easier to review and verify | Extract page controllers, data services and reusable templates while keeping PHP |
| `aw_multi_list_docs` now runs sequentially despite a parallel-request comment | Potentially reduce accumulated remote latency | Prefer one aggregate read where suitable; otherwise batch independent reads after profiling |
| Dashboard and other views derive summaries from bounded history reads | Reduce transfer and avoid treating an arbitrary history window as a complete company universe | Read a validated latest snapshot/catalog and purpose-built dashboard summaries |
| Compatibility helpers retain retired backend names | Reduce misleading concepts and maintenance burden | Replace callers gradually with domain methods such as company history and portfolio summary |
| Some scripts/styles use external CDNs; Chart.js URL is unversioned | More predictable rendering and dependencies | Pin versions, bundle assets where useful, and consolidate shared page components |

Measure response time, request count, transferred bytes and chart interaction
before selecting a new runtime. No measured evidence currently establishes PHP
execution as the bottleneck. Fixing data-access patterns may matter much more.

Preserve the selected visual direction. Improve search/filter persistence,
keyboard access, readable narrow-screen tables, consistent loading/error states,
and explicit recorded-price/freshness labels. Their priority should be validated
with actual usage and device checks rather than inferred solely from code.

## Phone app evaluation

Keep Flutter. Replacing it with React Native or native Android would require
rebuilding working screens and integrations without an established user benefit.

- **Shared data ownership:** `HomeScreen` retains four tabs in an `IndexedStack`.
  Their separate initialization loads create redundant startup work. Preserve tab
  state but initialize expensive tabs on demand and share cached market data.
- **Refresh across screens:** trade callers reload their own screen; other retained
  tabs have independent futures. A successful trade should invalidate portfolio
  and statistics data consistently. Add refresh on resume with a bounded freshness
  policy rather than constant background polling.
- **Purpose-built reads:** screener/statistics fetch up to 500 history rows and
  deduplicate them locally. Return one validated row per company instead. Existing
  500-trade/position bounds need explicit completeness and eventual pagination;
  retain current protections against displaying misleading totals.
- **Typed models and repositories:** screens currently handle many
  `Map<String, dynamic>` values and generic collection queries. Introduce company,
  quote, trade and portfolio types and repositories around the existing backend.
  Separate presentation state from widgets incrementally. This follows
  [Flutter's architecture recommendations](https://docs.flutter.dev/app-architecture/recommendations).
- **Localization/accessibility:** current mobile text mixes French and English,
  while the website has French, English, Arabic and Darija catalogs. Add consistent
  localization, RTL, number/date formatting, text scaling and screen-reader checks.
- **Offline reads:** optional last-successful market/portfolio snapshots can improve
  weak-network use. Display their actual timestamps, isolate private caches by
  account, clear them appropriately, and keep trade submission online initially.
- **Charts:** current company charts use list positions for the X axis. Real
  timestamps would represent irregular gaps accurately; derive labels from the
  same filtered points. Load appropriate daily/intraday ranges rather than just
  increasing row limits.
- **Device acceptance:** verify confirmation/reset links, resume/session refresh,
  logout, slow-network retries, large text and trade retry behavior on a real
  Android phone. Existing unit/widget coverage cannot establish device behavior.

## Shared architecture priorities

1. Complete fresh-data and official-close integration under existing activation
   decisions. A new UI language cannot supply missing authoritative prices.
2. Define stable application operations rather than exposing storage-shaped
   queries everywhere. Supabase RPCs/views and existing services can supply these;
   an always-running extra API server is not automatically necessary.
3. Keep authoritative persisted money calculations in exact decimal arithmetic.
   Share rule versions and fixtures across PHP/Dart/Python. Centralize persisted
   results where appropriate; local display estimates may remain local.
4. Retain private compressed archives separately from frequently queried typed
   application tables. Establish measured growth, retention/export and restore
   checks without deleting original historical evidence.
5. Add focused pull-request checks for the shared financial/data contracts. The
   root workflow currently builds release APKs but does not run analysis/tests
   first. Avoid running every costly integration suite on every cosmetic change.
6. Update the README and consolidate active handoff entry points: several old
   documents still describe retired backend behavior and superseded financial
   differences. Treat current source and latest checkpoints as the authority.

## Stack options

| Option | Suitability | Hosting consequence |
| --- | --- | --- |
| Refactor PHP + keep Flutter | Best near-term return, least duplicated work | Current free PHP hosting remains usable |
| TypeScript browser app on static hosting + keep Flutter | Reasonable later if browser interactions remain difficult to maintain | Can stay free; authenticated reads still consume backend quotas |
| Node.js application server + keep Flutter | Useful if a demonstrated server requirement or team preference justifies it | Requires a compatible host; current free PHP host is not a Node runtime |
| React Native replacement | Little demonstrated benefit for this project | Adds migration effort; store fees are independent of UI framework |
| PWA replacing the native app | Worth considering only if reducing two interfaces is the explicit goal | Can reduce ongoing UI maintenance, but requires mobile/browser behavior acceptance |

A static TypeScript frontend does not require a deployed Node.js server. A server
is needed only for operations that actually require it. Cloudflare Workers offers
Node compatibility, but it is not an unrestricted conventional Node server;
[compatibility must be checked](https://developers.cloudflare.com/workers/runtime-apis/nodejs/).

## Cost assessment

Prices below are USD, checked November 1, 2026, before taxes. Account allowances,
student benefits and current usage were not independently inspected.

| Area | Can improvements stay at $0 additional monthly cost? | Relevant limit or cost trigger |
| --- | --- | --- |
| PHP refactoring, Flutter architecture, localization, accessibility and caching | Yes | Engineering time and existing service usage |
| PHP website hosting | Yes on the existing offering | [InfinityFree advertises free PHP hosting](https://www.infinityfree.com/); changing server runtime needs a hosting decision |
| Static browser frontend | Yes | [Cloudflare Pages static requests are free and unlimited](https://developers.cloudflare.com/pages/functions/pricing/); functions/backend traffic have separate limits |
| Supabase | Potentially at current small usage | Free: 500 MB database, 5 GB egress plus 5 GB cached egress, 1 GB file storage; inactivity pausing. Pro starts at $25/month with one project included. [Pricing](https://supabase.com/pricing) |
| Small optional edge API | Potentially | Workers Free has request/CPU limits; paid subscription starts at $5/month plus applicable usage. [Pricing](https://developers.cloudflare.com/workers/platform/pricing/) |
| Private automation/builds | Depends on shared account usage | Current GitHub allowance is $12 compute/500 MB Actions storage on Free, $18/1 GB on Pro. Hard-stop budgets can prevent overage spending. [Included usage](https://docs.github.com/en/billing/reference/product-usage-included) |
| Authentication emails | Possibly | Built-in Supabase SMTP is restricted and limited to 2 emails/hour. Custom SMTP is needed for general users. [SMTP documentation](https://supabase.com/docs/guides/auth/auth-smtp) |
| Custom SMTP example | Service tier can be free | Resend lists a free tier with a 100/day cap; sender domains require DNS verification. A domain may add annual cost if one is not already available. [Pricing](https://resend.com/pricing), [domains](https://resend.com/docs/dashboard/domains/introduction) |
| Google Play distribution | No, if enrolling for the first time | $25 one-time registration; improving Flutter does not itself require Play distribution. [Google](https://support.google.com/googleplay/android-developer/answer/6112435) |
| Optional iOS store distribution | No, normally | Apple Developer Program is $99/year; Mac/build/device needs are additional considerations. [Apple](https://developer.apple.com/programs/) |

The latest local checkpoint records 334,026,419 database bytes: approximately
334 MB, roughly two-thirds of the nominal free allowance. This is a recorded
measurement, not a fresh capacity check or an estimate of remaining days.
Indexes, metadata and update patterns also consume space. Measure daily growth
before enabling continuous collection. Preserve raw evidence in private storage
and retain compact application projections to avoid paying for duplicate data.

The managed-worker planning document budgets 1,882 private runner minutes/month
including manual allowance, based on an existing Pro plan. That is not measured
live workload or a guarantee under GitHub Free; current included compute is
expressed in dollars. Existing benefits can mean zero additional spending today
while still creating a future dependency if they expire. Private worker code and
source details must remain private regardless of public-runner pricing.

Free-tier exhaustion may stop work or restrict service rather than automatically
produce a bill. On metered paid plans, configure actual hard-stop controls where
available; alerts alone do not cap spending. A paid database and edge API would
start around $30/month together before other services and overages, but neither
upgrade is required merely to refactor the application.

## Suggested order and effort

Planning ranges for one developer familiar with the project, with AI assistance;
these overlap and exclude an unknown wait for valid external data or approvals.

| Phase | Focused effort |
| --- | --- |
| Baseline measurements, current-state documentation and quota/growth inventory | 2–4 days |
| Purpose-built reads, mobile lazy loading/shared refresh, targeted web request improvements | 1–2 weeks |
| PHP separation and Flutter typed repositories/presentation state | 2–4 weeks |
| Mobile localization, optional read cache, chart and device acceptance work | 1–3 weeks |

A useful first milestone is two weeks of improvements with measured before/after
request counts, payload sizes, screen readiness and cross-screen correctness.
A broader modernization is approximately 4–8 focused weeks, with scope trimmed
to the most useful items. Fresh data activation is a parallel dependency whose
completion time cannot be inferred from source alone. A full web rewrite retains
the earlier 8–16-week planning range and needs stronger justification.

No code, configuration, deployment, hosted data, account or paid plan was changed
for this assessment.

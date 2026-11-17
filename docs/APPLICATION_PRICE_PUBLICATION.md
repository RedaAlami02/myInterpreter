# Full current-price publication — October 30

**Later frontend checkpoint:** read [MARKET_SCREEN_INTEGRATION.md](MARKET_SCREEN_INTEGRATION.md).
The website dashboard/selection and phone screener/detail now have a tested opt-in
preview, with source-date/reference labels and expiry behavior. 80 Flutter cases,
four controller cases and 16 browser layouts pass; flags remain off and no new
deployment or hosted change occurred. Older "screens not connected" notes below
describe the earlier backend-only checkpoint; actual cutover is still pending.

The original price-job port now has a private persistence and authenticated read
path for its full display rows. It extends the existing shadow feed. Recovered
`data`, `latest_prices`, portfolios, archives and genuine prediction/outcome
ledgers retain their original contents and meanings.

## Implemented

- `price_refresh.publication()` binds full stock/index rows to the exact quote
  candidate and archive. Stale or saved-price rows are excluded from publication.
  Quote → instrument-reference display precedence stays explicit; references
  keep unknown trade dates and remain ineligible for automatic valuation/models.
- The existing Python publisher accepts explicit company inputs and private field
  bindings, checks the approved field-profile hash, and submits both exact
  documents. Its CLI adds `--companies` and `--application-bindings`; both are
  required together. Legacy invocation/receipt behavior is unchanged.
- The existing managed publisher has an additional opt-in
  `APP_APPLICATION_ROWS_ENABLED` switch. It validates the full document hash and
  its quote-head/archive/capture bindings after authenticating the scoped caller.
  Original independent archive/quote checks remain. Its service key stays inside
  the managed function.
- SQL016 adds only `app_feed.application_control`,
  `app_feed.application_latest`, a service-only publish RPC and an authenticated
  read RPC. All table access is denied to application roles. The control starts
  off with no approved field pin; there is no anonymous read API.
- Publication requires an active lease bound to the same original archive with
  **both** shadow-feed and projection capabilities, plus the existing enabled
  source/feed controls and the new full-row control. The consumed earlier
  quote-only acceptance cannot enable this feature.
- SQL checks exact accepted quote SHA, archive, company identity, prices,
  capture dates, fundamental availability, allowed field shapes, capacity and
  retries. A conflicting document for the same accepted capture is rejected.
- The new read RPC composes the existing preview and clips full-row lifetime to
  quote/reference and lease expiry. Changed quote heads or field pins invalidate
  old full-row heads. It returns `app-market-preview/v3`, strips private bindings
  and observation IDs, and leaves all eligibility flags false.
- PHP and Flutter feed readers accept v3 through an explicit opt-in RPC choice.
  They validate identity, date, price, field types and expiry; strip unknown
  fields; preserve reported-date/source-event metadata separately from capture
  time; and expose display rows without legacy valuation-document conversion.
  Dart field maps are immutable. Older v1/v2 readers retain their behavior.

## Exact validation and trust limits

The worker re-derives full market fields/ratios from the verified raw archive and
known company inputs, using the rules compared with the original job. The edge
independently binds price evidence to the archive. Additional financial/market
fields are worker-derived and SQL shape-checked; they are **not independently
re-derived by the edge**. This is shadow display acceptance, not official source
authority or production valuation/prediction certification.

Quote publication and full-row publication use **two sequential RPC commits**.
A quote head can commit before full-row publication fails. The combined request
returns failure without a successful combined receipt; retrying the same bytes
is supported. Readers require the matching quote head and cannot display an old
full-row head against a new quote head. No claim of a two-RPC atomic commit is made.

Independent review found a missing-control/NULL-pin case in the initial SQL. It
was fixed with explicit control existence, enabled-state and nonnull hash checks,
and a regression. The reviewer independently passed 10 new SQL cases with zero
skips, 22 Deno cases, 17 Python publisher cases and PHP v1/v2/v3 checks, and inspected
the Dart parsing/expiry changes. No remaining blocker was found in the reviewed
local implementation. This review does not constitute production activation.

## Verification

| Check | Result |
| --- | --- |
| Managed Python regression suite | 232 pass |
| Managed publisher Deno suite | 22 pass |
| SQL016 + inherited v1/v2/manual-gate regressions | 42 pass on fresh disposable PostgreSQL |
| PHP | Syntax and v1/v2/v3 cases pass |
| Flutter | 72 pass; clean analysis |
| Exact SQL response in both clients | PHP and the two new Flutter cases pass |
| Complete synthetic chain | Python transport → managed archive/price binding → service-role SQL → authenticated read → PHP passes |

SQL cases include missing controls/pins, wrong evidence/identity/date/price,
reference-event forgery, old lease capabilities, disabled controls, role denial,
unchanged recovered table fingerprints, exact retry, conflicting retry, capacity,
interruption rollback and revocation. Test databases use a `/tmp/` Unix socket
with TCP disabled and are dropped afterward. No genuine ledgers/models or live
market providers are used. This continuation also rebuilt the temporary test
cluster after the environment restart; no system PostgreSQL service was installed.

## Hosted release state

The reviewed four-file disabled upgrade is pinned privately under
`private/application-rows-20261030/disabled-package/`. Manifest SHA-256:
`6dd4d228357e386e23ac520a50bc8f5696697419da6bb5a855f7318d39482234`.
It contains SQL016 and the three existing publisher source files, 48,720 bytes.
SQL016 committed and the existing app publisher was upgraded from version 7 to
**version 8**. All nine hosted source files match the pinned packages; archive
and projection functions remain version 6. All three endpoints return their
exact disabled HTTP 503 responses. The new control is off with no field pin and
the new application-row head table is empty. No secrets were written.

Fresh verification rechecked the protected recovery backup SHA-256 and all 15
original application-table fingerprints. Existing archive/feed/projection/trial
rows and all existing SQL function bodies/ACLs are unchanged. Anonymous exposed
application relations: zero. Database size: **333,534,899 bytes**, an increase of
98,304 bytes from the preceding checkpoint. Collection, schedules and source
requests remain off. Receipt: the successful `install-*/receipt.json` under the
private evidence directory. This completed disabled upgrade must not be repeated.

The Python publisher, PHP/Flutter changes and private-worker distribution are
separate from that hosted function package. Main website/mobile screens have not
switched to this preview. Collection and schedules remain disabled. No new market
capture, real email, account assignment, APK build, Git commit or push occurred.

## Remaining work

1. The disabled backend upgrade/readback is complete. Do not request its approval
   or install it again; its active use remains a separate acceptance step.
2. Make a real user-driven account and verify confirmation/reset delivery and
   authenticated preview under a newly authorized acceptance window.
3. Connect opted-in market-screen display components to the full-row reader,
   including visible price-basis/date labels. Keep history and valuation separate.
4. Integrate new-listing persistence and enrichment dispatch through existing
   collectors; verify fundamental/dividend jobs, daily P&L and safe retention.
5. Distribute the updated private worker, verify free-tier budgets and durable
   cross-run state, then enable explicitly approved recurring schedules/cutover.

Provider identities, credentials, native bindings, raw responses and private
account mappings remain in ignored private files. Full evidence and reproducible
local harnesses: `private/application-rows-20261030/`.

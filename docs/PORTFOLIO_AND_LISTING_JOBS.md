# Portfolio and listing continuation — November 1

**November 2:** SQL020/021 have now been installed after explicit approval, still
disabled/unpinned. No official-close batch/source is admitted. Website sorting,
recent sessions and separately annotated purchase days are live; a Supabase APK
was built. See [APP_CONTINUATION_20261102.md](APP_CONTINUATION_20261102.md) for
verified runtime state and remaining work. The staged status below is historical.

**Owner decision: saved daily P&L requires verified official closing prices.**
An intraday or late-session estimate does not satisfy this requirement. Existing
saved history remains unchanged. Informational recorded-price estimates on the
screens are explicitly labeled and cannot authorize a saved valuation.

## Completed locally

Portfolio screens previously discarded price timestamps, treated recovered rows
as current and could subtract all purchase costs from a partial price total.
Both clients now retain recorded-date context, reject conflicting/invalid/future
records and show portfolio totals only with complete holdings and one common
recorded UTC date. Unknown current values, P&L and estimated exit/total fees stay
unavailable. Purchase costs/quantities remain visible; price-fetch failure does
not hide the phone's holdings. Reference yields carry an indicative label/date.
The 500-position read cap suppresses portfolio-wide totals and allocation charts.

The website's daily-record action starts disabled and its server-side gate also
blocks a forged POST. Public-key refresh preserves that explicit setting. The
local valuation and market-preview flags were verified false. Real GET-controller
and template fixtures run without loading runtime keys/configuration.

`listing_plan.py` reuses `price_jobs.new_listings` against exact archived catalog
bytes and private field bindings. SQL020 adds a database-owner-only transaction
which preserves existing companies/mappings, rejects conflicts, verifies the
catalog fingerprint and stored archive metadata, and records an idempotent receipt.
New bare companies get no invented financial values or timestamps. Controls must
be off; provider profiles/pins are deliberately not changed by this transaction.
`tools/review_listing_updates.py` prepares read-only by default. Explicit apply
requires a reviewed plan digest, verified TLS, fresh archive/catalog checks and
exact rederivation before the first write. An unknown commit is journaled before
commit; fresh receipt readback follows success. No real plan was applied.

SQL021 provides the staged v3 official-close-only valuation path. It does not
depend on installing SQL012 and never reads recovered `latest_prices`, shadow
candidates or instrument references. A separate private source-policy pin,
reviewed batch and activation control are required; all start unset/off.

- Prices retain exact decimals, company identities and original evidence hashes.
  One observation cannot be assigned to two companies. Session/capture metadata
  must agree with the stored raw archive; unknown source close/publication clocks
  remain NULL rather than being invented. Actual capture time is mandatory.
- A distinct zero-argument authenticated `record_official_close_valuation` RPC
  derives the owner. The website requires an official-close receipt basis and
  cannot fall back to an older intraday writer. Legacy callers are also routed
  through the strict path when SQL021 is installed. The same owner lock as
  trades/recovery, READ COMMITTED isolation and one captured holdings array keep
  inputs coherent. Pending saved-account recovery blocks new valuation writes.
- Complete coverage, approved-policy/batch identity, current session day, approval
  timing and stored archive state are checked before writing. The legacy 17–19
  Casablanca execution window is retained, using installed timezone rules.
- Benefit and exact consumed-input provenance commit together. Retrying returns
  the saved value; existing unverified history is preserved and is not relabeled
  as official-close valuation. Numeric rounding preserves the original half-up
  rule, including negative values. Capacity and 500-position bounds fail closed.
- Holdings mean **holdings at execution**, valued with approved official closes.
  This is unrealized P&L against remaining purchase cost, not a one-day return or
  a reconstruction of positions at exchange close. No incomplete trade history
  is filled in to manufacture that reconstruction.

## Verified evidence and limits

| Check | Result |
| --- | --- |
| Managed Python regression | 301 passed |
| Flutter full regression | 102 passed, including 17 shared price cases and 3 phone-width widgets |
| Flutter analysis | clean |
| Shared PHP reference/coverage cases | 17 passed |
| Real PHP controller/template tests | 5 passed, including GET/no-write, disabled POST and capped holdings |
| Listing SQL transactions | 9 passed on isolated synthetic PostgreSQL |
| Official-close valuation SQL | 25 passed on isolated synthetic PostgreSQL |
| Web configuration / deployment boundaries | 7 / 3 passed |
| PHP syntax / locale checks | passed |
| Earlier immutable review bundle v3 | all 51 files and external pin reverified |

Independent review found and closed the repeatable-read stale-holdings edge and
render-fixture config isolation issue. The reviewer independently reran the PHP
cases/controller/templates; SQL tests were parent-run and code-reviewed, not
independently rerun. An initial SQL fixture incorrectly assumed a fixed UTC
offset; corrected tests resolve Casablanca wall times using installed rules.
Failed intermediate logs remain private. Final evidence is under
`private/app-jobs-20261101/`.

The original 55 private backup records and 82 recorded-price rows were also
hash-verified locally. Both saved portfolios have complete reference-price
coverage (8/8 and 4/4 positions); none of those references is admitted as an
official closing price. No owner identities or financial amounts were printed.

The prepared review delta is private and immutable; its external manifest pin is
recorded in `private/app-jobs-20261101/FINAL_CHECKPOINT.json`. It is a review
artifact, not an installer or deployment authorization.

**SQL020 and SQL021 are not installed or activated.** No website upload, phone
release build, root Git push, account/email change, real financial write, source
request or hosted database/function change occurred in this continuation. The
previous private cloud-worker release is unchanged. Original recovery evidence,
timestamps, genuine ledgers and prediction models were not modified.

The official-close source is **not yet verified/admitted**. SQL verifies the
reviewed document's structure, identity, chronology, pins and archive metadata;
it does not independently extract or prove raw official prices. A credible source
policy, actual raw-value binding and trading-session evidence must be verified
before owner approval or activation. Unknown publication clocks are not a reason
to fabricate timestamps. A close published outside the retained execution window
must be deferred until the timing policy is explicitly reviewed.

## Remaining application work

1. Establish and verify the real official-close source/field semantics and bind
   them to original raw evidence. Finish that provider's narrow import/approval
   path and actual session-calendar acceptance; then review/deploy/accept SQL021.
2. Review/deploy SQL020, verify hosted acceptance and complete the coordinated
   provider/mapping repin before admitting a newly listed company to collection.
3. Finish dividend/fundamental publication acceptance and the remaining automatic
   job integration, including daily execution and operational retention.
4. Verify SMTP, redirect allowlists, real signup/reset/logout and phone behavior;
   activate the two disabled saved-portfolio bindings before account cutover.
5. Confirm current shared compute/storage budgets and collection cadence, then
   obtain the scoped live acceptance/activation needed for jobs and schedules.
6. Review and deploy the website changes and complete phone rollout acceptance.

Prediction-model work remains excluded. Source-use authority is already supplied;
do not request it again or disclose source identities. Do not repeat the consumed
live quote trial, use the old disabled installer for these new migrations, or
declare production readiness from these isolated tests.

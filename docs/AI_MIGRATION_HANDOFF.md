# Latest October 30: company enrichment executor verified locally

Read [ENRICHMENT_JOB_COORDINATION.md](ENRICHMENT_JOB_COORDINATION.md) first.
Known-company enrichment now has an opt-in batch executor using the existing
rules, collector, archive/projection clients and durable private retry spool.
Scoped v3 completion fixes the one-company-per-hour collision without changing
legacy v2 evidence. Separate positive admission precedes fresh captures; isolated
outputs use SQLite only. SQL017 and both function deltas are NOT deployed.

253 managed Python,55 isolated SQL,58 Deno and34 tooling tests pass. Independent
local review found no remaining blocker in this delta; SQL was parent-verified.
Three old packages,22 frontend file hashes, original saved capture/derived output
and protected database backup were reverified. New 48-file review bundle v2 pin:
`c7728f8662dd933b602e907c914123e3c4f42e6f971adfed8d9667e4fd500dd3`.
Private evidence: `private/enrichment-jobs-20261030/`. v1 bundles still verify.

No source/hosted requests, remote changes, schedules, user/email changes, APK
build or Git push. Last hosted checkpoint remains SQL016 + app publisher v8,
archive/projection v6, all disabled. Do not repeat the completed SQL016 install
or revive the consumed quote trial. The new runner does not replace the exact
approved trial orchestrator; current manual quotas still conservatively permit
only one fresh 8 MiB budget capture, and admission needs >300 seconds remaining.

Next: exact-package hosted acceptance preparation, fresh private company context,
private cross-run queue transport/price-job invocation, new-listing persistence,
remaining job/email/device checks and independently approved recurring execution.
Owner-only navigation and private account assignment remain deferred.

# Latest October 30: website and phone market preview connected locally

Read [MARKET_SCREEN_INTEGRATION.md](MARKET_SCREEN_INTEGRATION.md) first. Existing
web dashboard/selection and phone screener/detail now use the full-row reader
behind an opt-in flag, with explicit reference/date labels, expiry clearing and
MASI in points. Historical/portfolio paths stay separate; unavailable previews
do not fall back to old prices. Current detail survives historical load/error.

Both local preview settings are verified OFF. No deployment, hosted request,
source collection, email/account change, schedule, APK build or Git push occurred.
Last hosted checkpoint remains SQL016 + publisher v8, installed disabled; do not
repeat that completed install or approval. 80 Flutter tests,4 controller tests,
11 config tests,3 deployment-boundary tests and16 browser layouts pass; analysis
is clean and independent local review is complete. Evidence is private.

Next: real user/email and hosted/device acceptance, remaining original job
coordination, private worker distribution/budgets and approved recurring jobs.
Rare owner-only admin navigation and account assignment remain deferred.

# Latest October 30: full display-row backend installed and verified disabled

Read [APPLICATION_PRICE_PUBLICATION.md](APPLICATION_PRICE_PUBLICATION.md) first.
SQL016 + existing publisher v8 are installed; all nine hosted files match the
pinned packages, all three endpoints remain disabled, and anonymous application
access remains denied. All 15 original table fingerprints, existing archive/feed/
projection/trial records and existing SQL functions/ACLs are unchanged. Private
full-row control is off, unpinned and empty. Do not repeat the completed install
or its approval. No source requests, schedules, secrets or main app cutover.

Python→edge→private persistence→authenticated PHP/Flutter display now works in
isolated tests: 232 Python,22 Deno,42 SQL,72 Flutter pass with clean analysis.
Independent review passed after a missing-control/NULL-pin fix. Quote and full
rows commit via two RPCs; partial quote commit is explicit and exact retry works.
Additional financial fields are worker-derived, not independently edge-rederived.
Next: real user/email and preview acceptance, opt-in market-screen integration,
new-listing/enrichment dispatch, remaining original jobs and private scheduling.

# October 30: full original price-row parity verified locally

Read [PRICE_REFRESH_PARITY.md](PRICE_REFRESH_PARITY.md) first. The existing
preparation CLI now derives all 82 full stock/index rows exactly as the original
job on the saved genuine capture; enrichment decisions match too. 230 managed
tests pass. New-listing decision code is ported with explicit identity conflicts.
This is labeled offline shadow output, with zero source requests/remote writes;
application-table publication, hosted job dispatch and recurring execution remain.
The earlier SQL015/publisher upgrade is already installed disabled. Do not repeat
its completed approval or deploy. Original evidence and model/ledger state remain
unchanged. No app-screen cutover, real signup/email or device acceptance yet.

**October 29 hosted update supersedes staged-only statements below:** SQL015 and
app publisher v7 are installed with owner approval. All nine source files were
verified, original 15 app tables and archive/candidate/trial rows are unchanged,
all endpoints/controls remain off, and anonymous application access is denied.
No source requests, schedules or app-screen cutover. Read
`docs/DISPLAY_FALLBACK_INTEGRATION.md`; do not request the completed approval again.

# Start here: website, phone app and backend migration

**Newest local checkpoint:** read `docs/DISPLAY_FALLBACK_INTEGRATION.md` first.
Existing feed producer/publisher/RPC/PHP+Flutter readers now support opt-in v2
instrument references, with v1 quote behavior preserved.209 Python,18 Deno,32 SQL
and70 Flutter cases pass; analysis is clean, and the exact SQL fixture reaches
both readers. Pure price ratios match the old job for all81 preserved inputs.
Independent local review passed. A pinned, disabled-only upgrade package exists;
SQL015/publisher v2 are NOT installed and no source or hosted calls occurred.
Screen cutover and price/ratio application-table persistence remain incomplete;
continue old-function parity rather than claiming the whole migration finished.

**Newest owner priority:** read `docs/FUNCTION_MIGRATION_PARITY.md` first. The
owner challenged unnecessary rebuilding: prioritize old-function behavior and
reuse. Existing quote → instrument-list → saved-price fallback was omitted from
the new preview. It is now ported locally in app_feed.build_display_prices; saved
capture replay covers all81 stocks + MASI, with17 date-unknown instrument references
clearly distinct from fresh quotes. All205 worker tests pass; original published
candidate is exactly unchanged. Five existing provider adapters/router are present
in the configured collector project; no additional source requests were made.
The helper is not deployed/connected to app displays. The five original website
jobs still need the concrete parity/activation work recorded in that handoff.

**Newest live checkpoint:** read `docs/LIVE_CAPTURE_HANDOFF.md` first. Updated
secret permission worked: one genuine capture archived and byte-verified, exact
82-row shadow candidate published (64 stock quotes + MASI,17 explicitly missing).
Full acceptance remains incomplete because no real Auth user exists for preview.
All controls/endpoints are off, provider/lease revoked and trial secrets removed;
original 15 table fingerprints and privacy still pass. No automatic repeat trial
or reactivation of its old evidence. Next: user-driven real signup/email and
signed-in acceptance, source-coverage investigation from saved bytes, then the
separately gated recurring jobs/app cutover.

**Latest hosted continuation:** read `docs/TRIAL_ACTIVATION_HANDOFF.md` first.
The owner approved the bounded trial; exact SQL014 is installed, original data /
function integrity passed, and no-op service RPC / anonymous preview checks pass.
Owner screenshots clear the bounded Storage headroom check. No source collection
or active lease exists. Caller-secret provisioning returned HTTP403: the owner
was asked to update the saved token to Edge Function Secrets Read-write. Continue
from that capability update; do not repeat trial permission or installation.

**Latest continuation:** read `docs/MANUAL_TRIAL_HANDOFF.md` first. Local-only
SQL014 adds expiring owner-issued trial gates and immutable trial/object bindings;
27 isolated SQL and 10 private-package cases pass. A pinned five-minute,
one-capture quote/MASI proposal is prepared. Fresh hosted read-only checks match
all 81 company/format mappings and confirm the existing backend remains disabled,
private and empty. The authorized independent reviewer reran all 37 new cases,
verified the final pins and conditionally accepted local preparation. SQL014 and
the trial are NOT installed/activated; new scoped enablement approval, hosted
timeout/quota checks and Secrets Write provisioning remain separate.
Approximate app/backend progress remains 80% / 20% left; model work is excluded.

**Latest live checkpoint:** read `docs/DISABLED_BACKEND_INSTALL_HANDOFF.md` first.
The owner authorized the narrow disabled installation and supplied the scoped
Management token privately. Private bucket + SQL009/010/013 and three functions
are now installed; all controls remain off, providers/pins unseeded, no collection
or schedules. Nine hosted source files match the reviewed bundle and all three
endpoints return their exact disabled responses. Fresh privacy/preservation checks
pass; SQL011/012 remain deliberately absent. Approximate app/backend progress is
80% complete / 20% remaining, excluding prediction work. Do not ask again for
the completed disabled-install permission; enablement/cutover remain separate.

**Latest reviewed checkpoint:** read `docs/DEPLOYMENT_REVIEW_FIXES.md` first.
The owner authorized an independent AI review; five real issues were found,
fixed and independently re-reviewed closed. The revision-2 bundle is pinned;
193 worker, 47 packaged function, 84 isolated SQL and 23 tooling cases pass,
plus the real-local-SQL publishing integration. No deployment or activation
occurred. The proposed first disabled install excludes SQL011/012; it still
requires scoped owner permission and Management access.

**Latest October 29 continuation:** read `docs/DEPLOYMENT_REVIEW_HANDOFF.md`.
A fixed 41-file generic deployment bundle is prepared privately and hash-verified.
142 test cases passed, including the five packaged SQL scripts installed together
and interruption rollback. Fresh hosted read-only checks confirm all 15 app API
relations deny anonymous access, database size is 332,740,275 bytes, and all 145
sampled timezone conversions match. Services/bucket remain absent; nothing was
deployed or enabled. Independent review, deployment authorization, Management
access and the outstanding quota/hosted/device gates remain.

**October 29 continuation:** read `docs/MOBILE_EMAIL_AUTH_HANDOFF.md` first.
Opt-in Android email confirmation/resend/recovery is now implemented; clean
analysis and **65 full Flutter tests** passed (23 new). It remains disabled and
unverified on a device/hosted SMTP. No emails, deploys, schedules, account
assignments or APK builds were performed. The implementation and private evidence
in that newer checkpoint supersede older mobile-"not implemented" statements below.
Current rough app/backend progress: **75% complete / 25% remaining**, excluding
prediction work. The remaining cloud/review/deployment gates are unchanged.

Handoff prepared **2026-10-28**, at the owner's request to transfer work to another
AI. This is a documentation checkpoint, not permission to deploy or activate jobs.
Read this whole file, then the linked recent checkpoints and repository guidance.
The next AI needs project access to verify/edit these files. Do not replace that
access by pasting credentials or uploading the entire private evidence directory.
New explicit owner instructions supersede this checkpoint; retain approvals already
granted later instead of repeatedly requesting them.

## Goal and priorities

Replace the permanently unavailable Appwrite backend with Supabase and independent
managed data collection for the PHP website and Flutter Android app. The owner
wants managed services that work while their PC is off, with minimal maintenance,
private automation and no additional monthly spending.

**Current priority is the website/app and their automation, before prediction-model
work.** Continue implementing the missing application services. Do not restart the
earlier alternatives research or try to regain access to Appwrite.

Latest owner-facing estimate: **80% complete / approximately 20% remaining**
for website/mobile/backend migration. This is a rough engineering estimate, not a
measured completion rate, data-recovery percentage or production-readiness claim.
It excludes prediction-model work. Much of the remaining effort is integration,
email handling, operational testing and reviewed activation.

## Non-negotiable instructions

- **Never contact Appwrite.** Old files/commands are archival references. Legacy
  commands in AGENTS.md do not override the owner's later no-Appwrite instruction.
- **Source-use authority/approval is already supplied.** Do not ask again merely
  because the market source is private. Its names, domains, identifying aliases,
  native bindings and URLs must stay out of public code/docs/logs/screenshots,
  filenames, commit messages, PRs and pushes. Preserve unsanitized originals privately.
- Never print credentials or full API exceptions. Keep real keys, connection URIs,
  native recipes, raw captures and account emails out of Git and shared summaries.
  Public client configuration uses a publishable key only. CI must not receive a
  project-wide secret key or admin database URI.
- Preserve original exports, observation timestamps, provenance and conflicts.
  Never relabel a replay/reconstruction as an original or genuine forward capture.
  Missing/stale values must remain unavailable, not silently reused or filled.
- Preserve four frozen V3 models, genuine prediction/outcome ledgers and accepted
  Stage 1–2D evidence. No retraining, forged predictions or production activation.
- Preserve unrelated worktree changes. **The main repository is public and has
  extensive uncommitted/untracked work and older sensitive source references.**
  Never blanket-add, clean, reset or push it. Review a precise publication set.
- Cloud infrastructure deployment, live schedule/collection activation and production
  execution remain gated by explicit authorization and required independent review.
  "Continue" and source-use approval are not a blanket deployment authorization.
- No local Flutter `--release` build. Debug builds are permitted; release APKs use
  the reviewed GitHub workflow. Keep PHP/Dart dividend rules synchronized.
- Proceed autonomously with authorized implementation/testing/documentation. Ask
  only for consequential choices or genuinely missing credentials/permissions.

## Repository and reading order

Workspace supplied by the owner:
`/mnt/shared/Share/studies/FinishedProjects/myInterpreter`

Some sessions resolve the same workspace through
`/home/redachen/studies/FinishedProjects/myInterpreter`. Verify the actual Git root.

Read in this order:

1. `AGENTS.md` and any applicable nested guidance.
2. `docs/APP_FEED_PREVIEW_HANDOFF.md` — newest implementation checkpoint.
3. `docs/PRIVATE_ARCHIVE_GATEWAY_HANDOFF.md` — storage/gateway design and gates.
4. `docs/WEB_MOBILE_AUTOMATION_RESUME_20261028.md` — Auth/key rotation/mobile baseline.
5. `docs/WEB_MOBILE_AUTOMATION_RESUME_20261027.md` and
   `docs/WEB_MOBILE_AUTOMATION_HANDOFF.md` for earlier details when needed.

For model work only when the owner resumes it, start from
`research/prediction_model/docs/REPLACEMENT_HANDOFF.md` and verify its actual evidence.

`docs/MIGRATION_HANDOFF.md` is the historical index. Its older sections contain
superseded defaults, privacy findings, counts and pause notices. Follow the newest
checkpoint; do not treat every old section as the current state.

Project layout: PHP pages at root; shared PHP in `core/`; handlers in `handlers/`;
Flutter in `myinterpreter_app/`; replacement workers in `automation/managed/`;
managed gateway in `automation/archive-gateway/`; SQL in `migrations/supabase/`.

## State: live foundations versus staged work

| Area | Established state | Still missing / limitation |
| --- | --- | --- |
| Supabase application data | Recovered application data and private recovery archives were imported and verified in earlier checkpoints | Locked final Appwrite contents are unknowable; do not claim every final cloud row was recovered |
| Database privacy | Last valid-key verification: all 15 existing application relations reject anonymous access; portfolios are owner-only; internal recovery schemas unexposed | Recheck after any schema/policy changes; a `public` schema name or publishable key does not mean anonymous data access |
| Web/mobile backend code | Local PHP/Flutter code selects Supabase; old network calls fail closed; portfolio trades use an atomic RPC | Complete website/APK production cutover is not established by local code or tests |
| Login/logout/sessions | Real PHP and mobile-SDK integration passed with updated keys, including refresh, restoration, owner isolation and trades; synthetic accounts cleaned; PHP confirmation/reset/callback flows implemented and unit-tested | Email delivery, hosted redirects and the reset form are unverified; Android links implemented October 29 but disabled pending hosted/device acceptance |
| Preserved personal data | Both saved portfolios retained separately, 55 records in private staging | No new-user assignment; original Auth/password export was not verified |
| New quote/book collectors | Generic bounded collectors, private recipes, raw hashes/manifests, completeness and retry checks implemented | New recurring/live collection has not been activated; actual hosted full-batch acceptance still pending |
| Raw-object archive | Gateway, scoped-token client, outbox and SQL009 implemented and tested | Gateway/bucket/SQL009 deployed and verified disabled; scoped caller token, positive hosted acceptance, organization quota and cross-run fallback unresolved |
| App quote/index preview | Exact mapping/candidate builder, SQL010 and PHP/Flutter readers implemented/tested | SQL010 installed disabled, readers not wired into active pages |
| Trusted app publisher | Python publisher, scoped `app_publish_` boundary, canonical candidate/mapping checks, archived-object re-read and per-observation price binding implemented/tested | Publisher deployed/source-verified disabled; caller token and private pin profile unprovisioned; no positive hosted acceptance |
| Owner maintenance writes | SQL011 admin RPCs, PHP admin client, Update/enrichment handlers and the authenticated reviewed-disclosure CLI implemented/tested; operator snapshots carry explicit provenance | SQL011 not installed, admin row not seeded |
| Dividend adapter | Managed calendar collector, verified-byte projection builder and shared payment-period rules implemented/tested; private preparation tool only | SQL013 and projection boundary installed/source-verified disabled; no caller token, seeded pins, schedule or positive hosted acceptance |
| Daily portfolio valuation | Owner-authorized, date-idempotent SQL012 valuation RPC with closing-window price requirements; PHP client and portfolio action implemented/tested | SQL012 not installed; no automatic scheduler; UI action not device-tested |
| Fundamental adapter | Managed three-phase collector, parity-tested derivation and verified projection builder implemented/tested; private preparation tool only | SQL013 and projection boundary installed/source-verified disabled; no caller token, seeded pins, schedule or positive hosted acceptance |
| Projection publication | Scoped `proj_publish_` boundary, SQL013 service RPCs, Python client and loopback integration implemented/tested | Function/SQL013 installed disabled; token and pin row not provisioned; boundary cannot re-derive source values |
| Cross-run outbox recovery | Bounded private bundle pack/unpack with exact hash/length checks implemented/tested | Private artifact destination, quota and retention policy not provisioned; no schedule |
| Deployment package | Independent review closed five findings; owner authorized and Management token supplied for the completed disabled installation | Enablement, source/pin provisioning, SQL011/012, positive hosted acceptance and cutover remain separate gates |
| Managed platform | Separate PRIVATE repository contains reviewed generic package; manual cloud fixture tests passed | No native recipes/credentials uploaded in the latest publications; no schedule activation |
| Prediction system | Separate earlier recovery/replacement work and evidence exist | Deferred; no new model acceptance or readiness is claimed here |

The main site's currently deployed remote files must be inspected separately before
claiming a live website migration. Neither the archive nor preview handoff deployed
the website or built a new release APK.

## What was built most recently

### Raw archive and outbox

`automation/managed/market_frame.py`, `market_collect.py`, `depth_frame.py`,
`depth_collect.py`, `worker.py`, `archive_store.py`, `outbox.py`, `flush_outbox.py`
and `run_collection.py` provide the generic acquisition/archival path.

- Raw bytes/hashes and actual receipt time remain separate from source clock text.
  A naive source clock stays UNKNOWN timezone. No backdated capture time.
- Quote/reference/index/status views are separate. Books and catalog prices cannot
  manufacture missing detailed quotes. COMPLETE does not grant price authority.
- The TypeScript gateway accepts an independent scoped write token, never a CI
  project-wide key. It verifies envelopes/hashes, reserves capacity, performs
  immutable upload and full read-back, then finalizes a unique logical slot.
- SQL009 stores small archive metadata and references private file objects. It is
  a standalone alternative to database-only draft SQL007, not dependent on it.
- Outbox copies are private, bounded and fsynced before upload. Exact receipts
  remove only transmission copies. Failed/partial writes remain for review.
- **An outbox on an ephemeral GitHub runner does not survive runner disposal.**
  A verified private cross-run recovery/fallback remains necessary before schedules.

The gateway exposes neither archive downloads nor a candidate-publishing operation.
It does not read private accounts/portfolios or create predictions.

### Separate application preview

- `automation/managed/app_feed.py`: hash-verifies the original archive bytes and
  recomputes normalization from raw data/private recipe before deriving candidates.
  It preserves exact decimal text, expected universe, missing/conflicting data,
  source timestamps and explicit expiry. All output is SHADOW_ONLY and ineligible
  for prediction/automatic portfolio valuation.
- `tools/prepare_app_feed.py`: local preparation only, private outputs, no remote
  write option. `IsolatedFeedStore` keeps a bounded latest preview per allowlisted
  provider; exact retries work, older and conflicting equal-time updates fail.
- `migrations/supabase/010_shadow_market_feed.sql`: draft service-only publication,
  pinned mapping/recipe/source, verified archive references, exact company checks,
  authenticated sanitized reads, dynamic expiry and evidence availability checks.
- `core/ShadowMarketFeed.php` and
  `myinterpreter_app/lib/shadow_market_feed.dart`: separate preview readers, without
  legacy `pa` document conversion or active page integration. Cached prices expire.

An older recorded archive lacked derived capture/observation IDs. Compatibility
requires an explicit replay-only option and exact agreement of every other field.
Derived IDs are labeled as new; original archives stay byte-identical. Current
acquisitions cannot use this compatibility bridge.

### Trusted application publisher

`automation/app-publisher/` closes the gap the write-only archive token left open:
it accepts only the canonical candidate document, its exact mapping and both
hashes, over a separate `app_publish_` token. It re-reads the exact archived object
by digest from private storage, requires the envelope contract, provider, receipt
time, completeness and frame date to agree, and requires every submitted
observation — through the hash-pinned mapping — to equal the stored frame's
identity, decimal text, receipt time and row index, with no dropped or shared
observations. Only then does it call the service-only publication RPC with the
project key held inside the function. CI never receives that key or the archive
token's authority.

`automation/managed/app_publish.py` builds the candidate with `app_feed.build`
(hash, raw-value and exact-mapping verification) and refuses replays, legacy-ID
derivation, unpinned mapping/recipe and any local isolated or recorded store.
`market_collect.py --publish-profile` publishes immediately after a successful
archive save; `run_collection.py quotes` forwards the option. A caller holding the
archive token could still store a forged archive and publish from it — that remains
the archive trust boundary, and both tokens must stay private and rotatable.

The publisher function, its token and the private publish profile (mapping plus
approved mapping/recipe pins) are **not provisioned or deployed**. SQL010 is still
not installed.

### Administrator maintenance writes

`migrations/supabase/011_admin_market_maintenance.sql` replaces the retired direct
write helpers used by the Update/enrichment paths. Two SECURITY DEFINER RPCs
require both an authenticated JWT and a row in the private `market_admin.admins`
table; the publishable-key client never receives elevated rights. Company updates
accept a fixed field whitelist with type, range, precision and percent-fraction
checks, and never create a company. Operator analysis snapshots are inserted into
`public.data` with `source='OPERATOR_ENTRY'`; recovered rows keep null provenance,
zero or missing prices write nothing, and `latest_prices` is never touched.

`core/SupabaseAdmin.php` is the explicit client; `handlers/storing.php`,
`save_enrichment.php` and `sync_companies.php` now use it. `tools/
apply_reviewed_company.php` signs in with `MI_ADMIN_EMAIL`/`MI_ADMIN_PASSWORD`,
reads with the signed-in token, writes through the owner RPC with a private backup
and read-back verification, and refuses newer stored accounts. SQL011 is not
installed and the administrator row is not seeded.

### Dividend adapter

`automation/managed/dividend_collect.py` archives each configured calendar page
(raw bytes, receipt time, declared charset) and marks the run incomplete when a
required year is missing; an unpublished next-year page (404) is optional.
`dividend_feed.py` derives a `dividend-projection/v1` document from the verified
archive without inventing data: exact amounts/dates, source-only confirmation,
conflicting periods excluded and retained, unmatched issuers retained, duplicate
spellings collapsed to the most complete row, and no fuzzy company matching.
`dividend_calendar.py` holds the payment-period rules shared with PHP and Dart and
is fixture-tested against `tests/fixtures/dividend_periods.json`; it is also
compared with the archival Appwrite parser.

`run_collection.py` now dispatches `dividends`; `--publish-profile` stays limited
to quotes. `tools/prepare_dividend_projection.py` writes only under `private/`.
There is **no publication boundary yet** for `public.dividends`, and no schedule
is enabled.

### Daily portfolio valuation

`migrations/supabase/012_portfolio_valuation.sql` adds
`public.record_daily_valuation()` for the signed-in owner. It computes latent P&L
from that owner's `portefeuille` and `latest_prices`, requires a same-day
closing-window price (local 15:45 or later, weekday), refuses missing/zero/future
prices, bounds positions at 500, writes at most one row per owner/day, and returns
a bounded status. The time-injectable implementation lives in
`portfolio_private.daily_valuation`, which the API role cannot execute and which
lets tests use fixed local times.

`core/SupabaseApp.php` validates the receipt; `portfolio.php` offers an explicit
"record today's valuation" action, so page loads never write. SQL012 is not
installed and no automatic scheduler exists; a scheduled all-user job would need
its own reviewed restricted credential.

**Timezone caveat.** SQL010 and SQL012 evaluate `Africa/Casablanca` with the
database's own tzdata, while the Python workers, PHP and Deno use their own.
These can disagree: the local pg17 image reports UTC+1 for late October 2026 while
Python tzdata 2026.2 reports UTC+0. Before enabling freshness or closing-window
gates on the hosted project, confirm its tzdata; a mismatch shifts every local-time
boundary by an hour. The SQL tests express times as local wall-clock values so
they do not depend on the test host's offset.

### Fundamental adapter

`automation/managed/fundamental_collect.py` fetches one symbol's configured
endpoint set in three phases (identity, company statements keyed by the external
name resolved from the registry response, and symbol-keyed profile endpoints),
archives every raw response, and marks the run incomplete when any endpoint fails.
`fundamental_frame.py` ports the archival enrichment's pure rules: one consistent
fiscal year pins the reported figures, projected profit stays separate
(`fy_est`/`rnpg_est`), share count is current and split-aware, and absent tables
leave fields unknown. The tests compare those rules with the archival module and
it is removed from `sys.modules` afterwards so the retired SDK does not leak.
`fundamental_feed.py` verifies the bundle and emits `fundamental-projection/v1`
for one mapped company; `tools/prepare_fundamental_projection.py` writes it under
`private/` only.

`run_collection.py` dispatches `fundamentals` with a required `--symbol`. There is
**no published schedule** and SQL013 is not installed.

### Projection publication boundary

`migrations/supabase/013_projection_publication.sql` adds a private
`app_projection` control row (provider plus both index pins) and two service-only
RPCs. `publish_dividend_projection` re-applies the payment-period rules, requires
company existence, and upserts rows by company/year/type, updating only changed
rows and never deleting absent ones. `publish_fundamental_projection` requires the
exact field set and applies the retired merge rule: fill missing values, replace
populated ones only for a newer fiscal year, and never overwrite with null. Both
require a STORED archive of the matching kind from the pinned provider.

`automation/projection-publisher/` authenticates a separate `proj_publish_` token,
validates the exact document, re-reads the archived object and its capture hashes,
requires the envelope kind/provider/execution (and symbol for fundamentals), then
calls the RPC with the key held inside the function. `automation/managed/
projection_store.py` and `tools/publish_projection.py` are the client and CLI.
The boundary **cannot re-derive HTML or financial-series values**, so a token
holder could submit contract-valid but substituted values; the index pins, exact
company lookups and review flow bound that risk. Nothing is deployed or scheduled.

### Cross-run outbox recovery and deployment package

`automation/managed/outbox_bundle.py` packs pending outbox copies into one bounded
private bundle (≤ 64 entries, ≤ 64 MiB) and restores them into a fresh 0700 spool,
verifying every filename, declared length and hash and refusing conflicts or
unexpected entries. It never collects, sends or deletes evidence. The private
artifact destination, quota and retention policy are not provisioned.

`docs/DEPLOYMENT_PACKAGE.md` consolidates the SQL order, bucket, three functions,
three distinct tokens, control rows, private artifacts, verification sequence and
disable order for the independent review. It is not a deployment authorization.

### Signup confirmation and password reset

The PHP site now has a complete local flow: signup and recovery send an S256 PKCE
challenge with a `redirect_to` at `auth_callback.php`; the callback accepts either
the PKCE `code` (exchanged with the server-held verifier) or implicit fragment
tokens (validated through `/auth/v1/user` before a session is stored);
`auth_reset.php` sets a new password from the recovery session, enforces 8–128
characters and matching confirmation, then clears the session. Password-reset
requests answer identically whether or not the address exists, and the login modal
can resend a confirmation.

`core/SupabaseApp.php` gained `recover`, `resendConfirmation`, `exchangeCode` and
`updatePassword`; `core/supabase_session.php` holds the PKCE helpers and a
hostname-validated absolute-URL helper. See `docs/AUTH_FLOWS.md` for the Supabase
URL/template settings the owner must confirm. Email delivery, hosted redirects and
the reset form remain unverified. Opt-in Android email-link handling was added
October 29; hosted redirect, SMTP and actual device acceptance remain pending.

## Verified evidence and limits

Latest checkpoint completed **2026-10-28**: preview work by 20:28 UTC, publisher
additions later the same day.

| Check | Verified result |
| --- | --- |
| Original company/format mapping | 81 companies + 81 formats, exact names and expected symbols; separate MASI binding |
| Preserved market response at original cutoff | 66 detailed stock quotes + MASI = 67 reported values; 15 missing stock quotes |
| Same old response at current cutoff | 67 stale captures / 15 missing / **zero current display prices** |
| Preserved depth diagnostic | All 81 raw responses retained and reprocessed into 81 complete book frames; three empty books; 15 unavailable last-trade summaries remain null |
| Local Python workers | **188 tests passed**, including 15 app-feed, 14 publisher, 18 dividend, 24 fundamental, 6 projection-client and 8 outbox-bundle cases |
| Publisher boundary | **15 Deno cases passed**; Python builder accepted through a loopback Deno fixture, altered price rejected |
| Projection boundary | **10 Deno cases passed**; Python projection accepted through a loopback fixture, invalid document rejected |
| Admin maintenance SQL | **10 passed**, isolated local PostgreSQL; PHP admin adapter tests passed |
| Valuation SQL | **7 passed**, isolated local PostgreSQL; no automatic scheduler |
| Projection SQL | **10 passed**, isolated local PostgreSQL |
| SQL010 integration | **13 passed**, isolated local PostgreSQL |
| Existing archive SQL/concurrency | **25 passed** |
| Flutter | October 29 analysis clean; **65 tests passed**, including 23 new mobile email-flow cases |
| PHP preview reader | Syntax and focused checks passed |
| PHP auth flows | PKCE helper, client-shape and page-render checks passed; email delivery unverified |
| Private cloud | **116 worker + 19 gateway passed**; **38 SQL tests skipped there**, already exercised locally |
| Latest private publication | **39 reviewed generic files pushed and all remote hashes verified** |

Private worker commit: `f19dd9f5ebf7578ad5d6652443bccf2f9248ede3`.
Manual verification run: `40762153711`. Repository identity is in the private
metadata file listed below; it is deliberately not copied into this shareable handoff.

The complete application database was not re-audited during these preview tests.
Earlier recovery inventories include original market IDs, index history, dividends,
company mappings, independent historical references, order-book archives and the
private records. Use their documents/manifests and actual hashes before quoting
whole-database counts. See `docs/DATABASE_RESTORE_STATUS.md`,
`docs/ALL_NONPERSONAL_DATA_RESTORE.md`, `docs/DATA_RECONCILIATION.md`,
`docs/HISTORY_DELTA_ARCHIVE.md` and `docs/PERSONAL_DATA_RECOVERY.md` as applicable.

## Private evidence: access locally, never publish wholesale

| Location | Purpose |
| --- | --- |
| `private/app-feed-20261028T194844Z/HANDOFF.md` | Most detailed latest app-feed state, exact files, receipts and remaining work |
| Same directory: `CHECKPOINT.json`, `local-artifact-hashes.json`, `worker-publication-manifest.json`, `worker-publication-receipt.json`, `cloud-verification.json` | Verification and publication receipts |
| Same directory: `company-mapping.private.json`, `index-mapping.private.json`, `recorded-market-original.private.json.gz`, `at-original-cutoff.private.json`, `at-current-cutoff.private.json`, `preview.sqlite` | Native mappings, preserved archive and derived isolated previews |
| `private/archive-gateway-20261028T185149Z/HANDOFF.md` | Gateway/outbox evidence and installation gates |
| Same directory: `market-config.private.json`, `depth-config.private.json` | Latest prepared native profiles, with exact project binding added; not uploaded |
| `private/app-resume-20261028T183324Z/HANDOFF.md` | Actual updated-key mobile check, APK scan, depth replay evidence |
| `private/app-resume-20261027T192358Z/HANDOFF.md` | Updated-key web/privacy checks and original diagnostic receipts |
| `private/app-cutover-20261027/worker-repository.private.json` | Existing private automation repository identity |
| `private/app-cutover-20261027/ACCOUNT_ASSIGNMENT_DEFERRED.private.json` | Both owner-requested email assignments; never copy them into public docs |

Each publication used a separate `worker-release/` clone under its private
checkpoint. Older clones and evidence were preserved. Old fixed-file-list publish
scripts are not current. Do not rerun publishers blindly or copy a private folder
to another repository; it contains sensitive configuration/raw evidence.

The publisher files added after the 20:28 UTC publication
(`automation/app-publisher/`, `automation/managed/app_publish.py`,
`automation/managed/publish_store.py`, their tests and the loopback fixture) are
**not yet in the private repository publication** and were not pushed anywhere.

## Credentials and environment

- `.supabase-migration.env` is ignored and may be a symlink to secure host storage.
  It holds SQL/admin migration credentials. Read in memory; never dump or put values
  in argv/logs. Existing tools enforce a fixed set of keys; don't append unrelated
  deployment variables to that file and break its parser.
- `config/supabase.local.php` and `myinterpreter_app/backend.local.json` are ignored
  public-client configurations. No elevated key belongs there or in an APK.
- The API keys were rotated and verified in earlier checkpoints; client configs
  and the debug APK were refreshed. Do not revert to an older publishable key.
- Current project keys do not provide Supabase Management deployment access.
  A real archive write token has not been generated/provisioned yet.
- Custom SMTP remains **UNKNOWN**; the owner answered "Not sure." Don't repeatedly
  ask the same question without context, disable confirmation, or claim inbox delivery.
- `/tmp` tools/pointers can disappear. Private handoffs retain the useful scripts.
  Local tests used unpacked PostgreSQL 18.6 and Ruff 0.11.13; servers were stopped.
  Snap Flutter/local sockets may require approved execution outside a sandbox.

Earlier debug APK, not rebuilt by the latest preview work:
`myinterpreter_app/build/app/outputs/flutter-apk/app-debug.apk`, 192,654,818 bytes,
SHA-256 `a393474b317f68f48152903618f62761628a94148f18c4e164c39062f09be018`.
Known-secret scan passed for that artifact; it was not a universal secret audit.
Physical-device validation remains pending. Verify the file/hash before reuse.

## Free-tier/storage facts to revalidate before activation

Last read-only measurement: database **332,740,275 bytes**, no Storage buckets or
objects, no new archive schema. These are point-in-time facts, not current quota proof.
Earlier research recorded 500 MB database per project and 1 GB organization Storage.
SQL guards start disabled with upper ceilings of 350 MB database / 750 MB objects;
they are not an allocation or evidence that other projects leave that space available.

The 22.3 MB/month raw-data illustration came from two samples. Latest-row designs
still consume physical PostgreSQL space through metadata, TOAST, MVCC and indexes.
No automatic deletion or guard increase is authorized.

The private Actions planning estimate was 1,882 minutes/month including reserve.
GitHub documentation presents included compute both as Pro credits and legacy
minute allowances; verify actual current account billing/usage. Keep the owner's
**$0 extra-spend cap**. Other private repositories share usage; artifact headroom
has not been verified for outbox fallback. Synthetic CI timing is not a real-source
batch/runtime measurement. No schedules are enabled by these checkpoints.

## Recommended next implementation order

1. Reconstruct current worktree state and verify the latest evidence/receipts before
   relying on it. Preserve all unrelated changes and source-sensitive material.
2. **Review, provision and deploy the trusted managed application publisher.**
   It is implemented in `automation/app-publisher/` and
   `automation/managed/app_publish.py`; the remaining work is independent review,
   a separate `app_publish_` token, the private publish profile and hosted
   acceptance. SQL validation does not itself reparse raw objects, so the Python
   builder must keep doing the exact raw/value normalization.
3. Review, provision and deploy the implemented write boundaries: SQL011 (admin
   maintenance), SQL012 (valuation), SQL013 plus the projection publisher
   (dividend/fundamental projections), with admin/pin rows seeded privately and
   hosted denial checks. Then add the optional all-user valuation scheduler.
   Retain dividend quality exclusions and PHP/Dart financial-rule parity.
4. Resolve the private cross-run artifact destination, retention and actual
   organization storage/Actions budgets; confirm hosted timezone data. Review
   `docs/DEPLOYMENT_PACKAGE.md` and obtain independent approval plus explicit
   scoped deployment authorization and Management/CLI credentials.
5. Under that authorization, install reviewed private bucket/SQL009/SQL010/gateway
   with switches off. Test hosted auth, denial, error shapes, hashes, quota, expiry,
   interruption/retry and real current-session source coverage before a manual trial.
6. Wire a deliberately enabled preview into web/mobile after acceptance. Keep
   recovered history separate; AVAILABLE means a snapshot exists, not that every
   quote is fresh. Use `rowsAt` / `priceAt`; don't bypass expiry or false eligibility.
7. Verify email delivery with an authorized recipient once SMTP is configured;
   check the hosted callback redirect and reset form. The October 29 mobile links
   are implemented but opt-in; complete hosted allowlist and Android device
   acceptance, then the reviewed web/APK cutover.
8. Complete device testing, a reviewed main-project commit/publication set, website/
   APK cutover and only then separately authorized recurring schedules.

Independent review and deployment are not already accepted merely because tests
passed. Keep all new prediction paths SHADOW_ONLY; do not resume prediction work
instead of the app tasks unless the owner changes priorities.

## Deferred owner requests — do not forget or start prematurely

- Preserve **both** original portfolios. They are different users, not competing
  backup versions. Do not merge them or ask which one to keep.
- Both requested emails are recorded privately. Later bind the larger/smaller
  portfolio according to that record, requiring **verified matching email ownership**
  and a newly chosen password. Never link from a typed unverified email or guess
  historical passwords. Do not reset or overwrite existing real users.
- The 55 original private rows include trades, holdings and P&L snapshots. One sale
  remains unresolved for FIFO and some holdings lack saved purchases. Preserve
  snapshots; do not fabricate opening lots, missing transactions or timestamps.
- The owner-only, rarely visited "Société / MAJ" navigation item should be moved/
  de-emphasized using a professional pattern **after current migration work**.
  Retain its authorization rule; don't broaden access during a visual change.

## Useful verification commands

Read files first; rerun checks appropriate to changes. These commands don't deploy:

```
git rev-parse --show-toplevel
git status --short
python3 -m unittest discover -s automation/managed/tests -v
deno test --no-config --no-remote --no-npm automation/archive-gateway/gateway_test.ts
deno test --no-config --no-remote --no-npm automation/app-publisher/publisher_test.ts
deno test --no-config --no-remote --no-npm automation/projection-publisher/publisher_test.ts
python3 tests/integration_app_publisher.py
python3 tests/integration_projection_publisher.py
php tests/supabase_admin_test.php
APP_TEST_DATABASE="host=/tmp/... dbname=... user=..." python3 -m unittest tests.test_admin_market_sql -v
APP_TEST_DATABASE="host=/tmp/... dbname=... user=..." python3 -m unittest tests.test_portfolio_valuation_sql -v
APP_TEST_DATABASE="host=/tmp/... dbname=... user=..." python3 -m unittest tests.test_projection_sql -v
php -l core/ShadowMarketFeed.php
php tests/shadow_market_feed_test.php
```

From `myinterpreter_app/`:

```
dart format lib test
flutter analyze --no-pub
flutter test --no-pub
```

SQL tests require an explicitly configured isolated `/tmp/` Unix-socket database.
They intentionally skip without it. See private `run_shadow_sql.py` /
`run_isolated_sql.py` before reconstructing the temporary test environment. Never
point them at Supabase or weaken their local-host guard. Don't count CI skips as passes.

No background test server or collector was left running at the latest checkpoint.
The original October 28 transfer was documentation-only. The October 29 continuation implemented and tested the opt-in mobile email flow; no deployment was performed.

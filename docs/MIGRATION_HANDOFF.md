# Review issue 1 fixed — mobile reference contract (November 4)

Read docs/MOBILE_REFERENCE_PARITY_20261104.md. Mobile latest_prices ALWAYS uses
read_latest_price_references_v1 now, independent of live-feed feature flags. No
stale original-table retry. Portfolio refreshes on quote expiry/resume and every
15min while foreground to pick up closing batches arriving after quotes expire.
Background cancels timers; request generations guard stale completion scheduling.
116Fluttertests and analyzer PASS; four shared PHP timing scenarios PASS.
Private evidence private/mobile-reference-parity-20261104/. Finalcommit
07a85071cb9a47f5f44a65b3ca667e448bc355eb; cloud41749862195SUCCESS. APK
private/mobile-reference-parity-20261104/apk/app-release/app-release.apk downloaded
55,273,170bytes, SHA2f0bf2f7baa6bb340f5f8174fa6a525ef12cd75de6bb22efd90c50e90e7f6ced.
Older APKs retain the old fallback. Code/test acceptance passed; physical/live
acceptance is NOT complete. Main branch not merged; five selected files verified.
No SQL/production data/financial writers changed. Physical phone installation still
requires the owner's pending approval. Do not claim full migration/live readiness.

Portfolio label cleanup published: Gain / Perte replaces P/MV indicative and summary jargon; Montant investi replaces Val. Achat; Quantité, (par action), Frais de vente estimés, Seuil de rentabilité, Répartition par valeur. Summary uses Valeur actuelle (MAD). Five files PHP+translations exact hosted readback; calculations/sort order unchanged. Receipt private/website-price-check-20261104/website-clear-labels/.

Portfolio display follow-up: published core/holdings_table.php plus en/ar/ary translations. Column now “Valeur actuelle”; holdings with quantity>1 show total followed by per-share price in parentheses, matching purchase formatting. Sorting/date labels unchanged. PHP lint and invented 8-share rendering1776.00(222.00) verified; four hosted files read back exactly. Receipt: private/website-price-check-20261104/website-unit-price/.

# Website price correction — November 4 (read first)

User confirmed portfolio SGTM580 vs actual524. Root cause was stale October21
public.latest_prices plus expiring current-only overlays; enabling night schedules
had NOT refreshed that cache. Corrected and deployed without overwriting originals.

- SQL029_verified_close_display.sql installed; owner-only RLS table
  app_feed.recovered_close_reports preserves the genuine nativeNov3PDF bytes,
  original capture19:23:21.623087UTC and separate freshNov4verification00:26:57UTC.
  Full raw SHA2560b0708cf23baf385fb625aaa96330c96c20550c2dc4b6dbd31ea4391550ecc33.
-75mapped official closes seeded, includingSGTM524. Original latest_prices580
  remains unchanged BY DESIGN. Do not overwrite originals or mistake that raw
  table's old date for the website's current source: the app now uses authenticated
  public.read_latest_price_references_v1() when recurring mode is enabled.
- Read-only RPC unions original dated references, verified recovered report and
  future approved portfolio_private.official_close_batches. It never writes P&L.
  Future official batches therefore become overnight references automatically;
  current live quotes still overlay them during their same-day validity window.
- Only core/SupabaseMarket.php and core/backend.php published, exact hosted bytes
  read back and hosted recurring_feed=true separatelyverified. Permanent private
  rollback/evidence private/website-price-check-20261104/. AnonymousRPCread denied.
- All original public table fingerprints,55original private records and financial
  function bodies/ACLs unchanged. Database335,328,947bytes. No financial writes.
- Independentreview accepted,7SQLtests andPHPadapter tests passed. Synthetic Auth
  identities were used ONLY in isolated tests, never production. Tests required
  private Unixsocket PostgreSQL; stop the temp server after acceptance.
- Scope: fixes portfolio/directory dated price references, not old historical chart
  values or historical ratios. Mobile fallback adapter still needs the equivalent
  latest-reference RPC wiring; latest mobile build currently only overlays live
  quotes over its original reference table. No device install approval received.

# Latest follow-up — November 3 late session

- Mobile portfolio now consumes the authenticated recurring display feed, overlays
  same-day unexpired company quotes, keeps dated references for unmatched holdings,
  rejects conflicting names, suppresses mixed-date totals and expires quotes without
  writing trades/valuations. Pull-to-refresh remains available. Casablanca dates
  use pinned timezone0.11.2, independently of the phone timezone.
- Flutter111 tests passed, analyzer clean; regression includes quote expiry on
  screen, current/reference separation, source-date mismatch and local midnight.
- Six selected files published on fix/mobile-portfolio-quotes-20261103,
  commit0f25ebbdc45afcbbbbc339fde394364ccc152aca. Cloud APK run41742171126.
  Build SUCCESS; APK55,256,786bytes downloaded/hashed, main not merged.
  SHA d22317a3e1990f0d2e4d7445e07366d87699962faa370f8689094501290ca614.
  APK private/complete-automation-20261102/followup-20261103/mobile-portfolio/apk/app-release/app-release.apk.
  One authorized physical Android device connected, current app package not installed.
  User installation/testing approval was requested and remains pending; no app was
  installed/launched, no device identifiers or phone data disclosed.
- Fresh read-only backend check23:51UTC verified55original private records, all six
  backend controls ON, four valid source policies and all five GitHub switches ON.
  Official batches/valuations remain0 (market window has not reopened). DB unchanged
  at334,968,499bytes. Latest cloud runs succeeded; no new live-session proof yet.
- Missing holding investigation:16 matching local files/170 relevant saved records,
  zero ISIN fields and zero records labeled OFFICIAL_CLOSE. Existing historical
  prices do not establish a current verified official close. Keep13/14 coverage
  and skip the incomplete owner until credible authority evidence is available.
- Evidence: private/complete-automation-20261102/followup-20261103/.
  Source identities/credentials remain private; no Appwrite or prediction work.

# ACTIVE override — November 3 recurring and official automation ENABLED

Read [AUTOMATION_STATUS_20261103.md](AUTOMATION_STATUS_20261103.md) first.
It supersedes the older OFF/DRAFT statements below.

- Regular collection AND official-close collection/review are enabled; five flags
  read back true. SQL028 installed, fourth boundary deployed and reviewed, no
  financial records created. First head NULL deliberately means PRICE_UNAVAILABLE.
- Private worker b1ed0f5e32d170af151abb20fcc4295bad563bae, package
  874f195e2ea632d29c3e75548dbb39c5e21e5c252f5e86c62f9dde6a83995516.
  Hosted verification41703417398 and real predecessor/successor checkpoint
  acceptance41704611961 SUCCESS. Genuine fundamental collection41698483129 remains
  the actual source proof; after-hours checkpoint acceptance is not collection.
- Current cron8–18UTC weekdays plus Monday06:05/07:05. Casablanca dispatcher
  quotes15min09–17, depth5min09–17, fundamentals17–19, dividendsMonday07–08,
  official17:35–19. No source/price/valuation success may be fabricated before
  the first eligible live session. Do not force/backdate an outside-window run.
- v4 checkpoint fixes eight-channel v3 restoration. Official receipt compaction
  retains originals, including100session regression. Full managed356, SQL84,
  financialDeno4, existingDeno69, Flutter106 and config7 tests passed.
- Protected environment official-close-review is default-branch-only; financial
  credentials absent from collector repository scope. Parser/identity/source
  configuration hash and reviewed verifier commit are pinned. Future worker
  upgrades require updating the approved server verifier commit after review.
- Actual same-day official report fetched19:23UTC:80securities/77closes. Stored
  privately, zero financial writes; no backdated seed. Source binds78 companies;
  current report covers13/14holdingrows,1/2owners fully. Missing holding legitimately
  blocks the second owner's valuation; no guessed alias or quote substitution.
- New read-only capacity334,968,499bytes; private rawstorage36,831bytes/3objects.
  Prior-snapshot delta516,096bytes includes migration, not certified ingestion.
- Mobile recurring feed branch fix/mobile-recurring-market-20261103,
  commit4d451d2b608f9cacc7076d77ae19ca4212e69219, cloud41704803678SUCCESS.
  APK downloaded54,306,286bytes, SHA0e63fe62950b2b91da8689d939b40a75e027935def186e1a3b9aa66f2284d990.
  Path private/complete-automation-20261102/mobile-recurring/apk/app-release/app-release.apk.
  Device installation/acceptance remains unverified.
- Private evidence: private/complete-automation-20261102/. Activation initially
  expected401 but handler intentionally returns400 for all invalid inputs.
  Activation had committed; fresh READ-ONLY recheck confirmed all ON and unchanged
  data. Do not rerun installers/activation or infer OFF from that retained error.
- Automatic review rejected an initial release pause without restoration; it never
  ran. Corrected release used finally/retry/readback, all regular flags restored.
- Next: genuine next-session collection/official review proof, APK physical checks,
  mobile portfolio-current-quote parity, representative daily capacity measurement.
  Prediction work remains excluded. Preserve dirty root worktree and source privacy.

# ACTIVE continuation override — November 3 automation (read before older OFF notes)

Regular automation IS NOW ACTIVE. Latest implementation/evidence:
`private/complete-automation-20261102/`.

- SQL026/027 installed disabled first, exact three deployed function sources
  verified; then regular policies/credentials activated under explicit owner
  request to complete automation. Three providers cover quotes/depth/fundamentals/
  dividends; source profiles and tokens only in private GitHub secrets/secure host
  vault, not Git. Plan87339fb0c9fab24bd26ee48f7ec1de7ff2b0b44e5cc49f953121fe02316780cc.
- Private worker commit1d9260931b52cd3a204224d54776e5a4325c12d5,
  package5934e5d94587728d67d2eabaf518d5398d26378efa2c64f9d36981d20dbf5535.
  Cloud verification41697684856 succeeded. Bootstrap41698239369 succeeded,
  real hosted fundamental acquisition41698483129 succeeded:20-response pipeline,
  planned1/attempted1/complete1/failed0, exact successor checkpoint restored.
- All three flags APP_DURABLE_COLLECTION_ENABLED,
  APP_CHECKPOINT_HEADROOM_VERIFIED,APP_RECURRING_SCHEDULE_ENABLED true, read back.
  Current cron5minUTC8–17weekday and Monday06:05/07:05, local dispatcher quotes
  every15min09–17, depth5min, fundamentals17–19, dividendsMonday07–08.
  No price/depth live-session collection yet verified; current session was closed.
  New raw fundamental archive is6,263bytes; total archives now3objects.
- Shared artifact inventory295,126,478bytes across15 owned repositories,
  reserve3×65MiB fits included1GB. Current shared compute credit not readable;
  owner-confirmed$0hard-stop budget retained, not changed.
- Website six-file FTPS cutover PUBLISHED with exact readback/private rollback:
  core/current_prices.php,backend.php,ShadowMarketFeed.php,portfolio.php,
  infoAction.php,config/supabase.local.php. Authenticated recurring feed flags true;
  saved-valuation website flagfalse. Current quote overlay uses only same-day,
  unexpired observed quotes; unknown-date refs never promoted to current.
  Mobile has not yet been adapted/rebuilt for recurring RPC; still outstanding.
- All55 original private source records reverified; no existing financial rows,
  frozen models or genuine prediction/outcome ledgers altered by collection.
  Snapshot334,739,123bytes immediately after backend install (before new archive).
- Local recurring SQL78 and managed349 passed; PHP current-price test and all5
  portfolio controller/display tests passed. Independent reviewer reran78SQL+
  13price tests. New code outside published package continues to change.
- A failed installer preflight was ONLY tuple/list JSON normalization, no real
  data differences; fixed and installation succeeded. A schedule-enable receipt
  initially failed Decimal serialization AFTER successful flag write; fresh
  readback confirmed ON and corrected receipt, no repeated activation.

Official-close automation IS STILL OFF. SQL028 and fourth function
`automation/official-close-publisher/` are DRAFT/UNINSTALLED, as is the full
`automation/managed/official_close_collect.py` financial handoff (a disabled early
version is present in worker package; APP_OFFICIAL_CLOSE_COLLECTION_ENABLED is
not provided, so auto dispatcher skips it).

Reviewer found parser-hash-as-proof insecure: archive producer could forge parsed
prices. Current draft now adds HMAC attestation fields to the fourth handler;
this requires completing an INDEPENDENT verifier job/environment with key absent
from collector, fresh TLS download of approved report, independent PDF parse,
exact candidate comparison and HMAC over report/document/identity/parser/policy/
commit/actual-verification-time hashes. No attestation key has been provisioned.
Do not activate official financial writes with a caller-supplied parser hash alone.

SQL028 corrected to preserve master enabled flag and lock owners before control
row, matching authenticated valuation lock order. Existing official SQL test
fixture needs explicit seeded reviewed batch + enabled master now; rerun tests
and independent review after completing HMAC design. Its earlier82 tests passed
BEFORE these new corrections; not final acceptance. Existing global close flag
remains false. Never backdate P&L or bypass17–19Casablanca execution window.

Bootstrap concept for official master flag: owner-maintenance may independently
verify and privately archive one genuine report under a distinct new bounded
manual official-report plan (not old quote trial), register approved seed batch,
then explicitly enable master. This does not save any outside-window valuation.
Future recurring signed batches then update active batch only, never re-enable a
killed master flag. No bootstrap has been performed.

Official report identity investigation: retained company.name OR ext_name exact
normalized match yields78 unique company bindings/74 actual closes against Nov2
report. IAM and MUTANDIS now have direct retained ext_name matches. T2S has no
report match/close; keep that owner's valuation unavailable when coverage fails.
Candidate mapping in official-identity-candidates.private.json, NOT autoapproved.
Current official Python producer draft duplicates delivery logic and needs review/
refactor and tests; use it as staged code, not operational proof.

Keep going on official verification/automation, final scheduled proof, mobile
fresh-reader integration and monitoring. Do not disable regular source controls
merely because older prepare_installation/u.guard expects OFF; regular controls
are intentionally live now. The /tmp isolated PG socket may vanish across turns;
last database recurring_current has78 passing tests, official_automation had82
before financial safety changes. No source identities or credentials in public.


# Latest: slim runner selected, published and cloud-verified

Owner delegated the platform decision. Keep private GitHub Python workers, use
ubuntu-slim for durable collection and verification rather than another platform
migration. Read [RUNNER_DECISION_20261102.md](RUNNER_DECISION_20261102.md).
75-file generic package + manifest published privately; all 76 blobs verified,
ten unselected files preserved. Private commit 1dfc6248a0e9f2e5baf6396e51976e65608555ae.
Cloud run41521436164 SUCCEEDED on ubuntu-slim in73seconds:246Python+66Deno
checks, six-queue checkpoint exact upload/download/restore/cleanup, zero artifacts.
Four local publication-boundary checks pass. Temporary dependency install avoids
system Python changes. No credentials/source profiles/root project pushed.
Collection/checkpoint gates OFF; no schedule, source request, data deletion,
portfolio write or prediction work. This establishes runtime compatibility, not
live collection completeness or recurring admission. Continue those activation
checks and official-close integration; retain measured storage baseline below.

# Latest: runner alternatives and actual storage baseline

Read [RUNNER_AND_STORAGE_ASSESSMENT_20261102.md](RUNNER_AND_STORAGE_ASSESSMENT_20261102.md).
Fresh read-only verified-TLS database measurement: 334,452,403 bytes; 165.55 MB
below advertised quota but only 15.55 MB below installed archive/projection guard.
Private Storage two objects/30,568 bytes. All 1,686 original depth objects hashed
and decoded: 136,562 records, zero invalid, originals untouched. Measured samples
project ~45.15 MB/month quote+depth file storage at original cadence, ~67.72 MB
with a scenario reserve; not measured ongoing production growth. New repeatable
read-only `tools/measure_storage_capacity.py` verified live; baseline saved privately.
Compared Supabase Cron/Edge, cheap private GitHub slim, external HTTP cron,
Cloudflare Workers and Cloud Run against official current limits. Cheapest-change
candidate: benchmark existing Python on ubuntu-slim; integrated candidate:
bounded Supabase collectors. Neither switched/deployed/activated. Shared budget,
real recurring envelopes, metadata/vacuum growth and retention still need acceptance.
No data deleted, raw evidence relocated, schedules enabled or prediction work.

# Latest: desktop email confirmation accepted; temporary accounts removed

Owner confirmed fresh desktop email confirmation works after saving the correct
Site URL and exact website/mobile redirect allowlist. This supersedes the earlier
localhost routing failure. Management Auth-config read remains unavailable; do
not claim mobile-device acceptance from the dashboard screenshot or desktop test.
Latest APK should route app-originated confirmation to its registered deep link;
website-originated signup returns to the website, including on a phone.

At the owner’s explicit request, deleted exactly the two named temporary Auth
accounts after matching their full email identities and checking all four
portfolio tables had zero records for each. Auth API deletions succeeded; fresh
read-only verification confirms both absent, other account identity/password
fingerprint and all portfolio table counts unchanged. Private audit receipts are
under `private/temp-account-cleanup-20261102/`; do not publish account identifiers.
Automatic collection and official-close valuation work below remains unfinished.

# Latest: automation, genuine official report and confirmed Auth redirect failure

Read [AUTOMATION_AND_OFFICIAL_CLOSE_20261102.md](AUTOMATION_AND_OFFICIAL_CLOSE_20261102.md).
One current-session report retrieved with verified TLS: 80 securities, 76 closes,
zero report cross-check discrepancies. New exact-decimal application parser
matches the retained parser 80/80; 341 managed and 3 distribution tests pass.
Nine of 12 held company names have unique report-name candidates; three require
explicit identity bindings. No mappings approved, archive admitted or P&L saved.
Original five-minute depth versus proposed hourly replacement schedule drift
confirmed; new non-activating planner shows original cadence costs $16.284 at
one billed minute per job, $32.568 at two on standard Linux, before other jobs.
Shared remaining allowance/timezone/runtime evidence still needed. Controls OFF.
Owner's real confirmation email still redirects to localhost:3000; fresh Auth
configuration read remains 403. Exact dashboard settings requested; not fixed.
No prediction work or financial writes. Keep working on automatic updates/P&L,
with the Auth dashboard correction pending; no further cosmetic/mobile detours.

# Latest mobile fix — November 2, 2026

Read [MOBILE_REFRESH_20261102.md](MOBILE_REFRESH_20261102.md). Confirmed trades
now refresh retained portfolio/statistics/personal-dividend tabs, once per submission;
uncertain replies do not falsely invalidate and disposed account screens stop
listening. All105Flutter tests pass and analysis is clean. Five screened files
published on fix/mobile-portfolio-refresh-20261102 at482db80c25a7f260301f2735d85873432d25c53d;
its build41512642657 succeeded. Final dividend-tab follow-up is on
fix/mobile-refresh-complete-20261102 at a317845ead3fc5c1a6d24e7b4e1deebbaa158c06,
cloud build41514053430 succeeded. Final installer/verification receipt are under
private/mobile-refresh-complete-20261102/. Physical-device acceptance remains.
Prior email callbacks stay
enabled in this branch; hosted email URL settings remain pending permission.
No actual financial/source writes, schedule activation or prediction work.

# Previous main fix — November 2, 2026

User resumed the main website/mobile/automation work. Read
[PRICE_INPUT_REPAIR_20261102.md](PRICE_INPUT_REPAIR_20261102.md) first.
SQL025 and the existing price publisher now provide company inputs under the
price job's own quote lease/pins, without a separate enrichment-provider lease.
Installed and source-readback verified; no legacy functions/data changed.

Bounded hosted read passed for all 81 mapped companies; zero source pulls,
archives or publications. Exact original provider/control state restored, lease
revoked, temporary secrets removed and endpoint disabled again. Original 55
private records and public table values reverified. All schedules remain off.

327 managed Python,64 isolated SQL and27 price-publisher Deno tests pass;
independent review reran focused SQL/Deno/Python suites. Private worker release
15e41fe9784047a32701124d81a8ce894688d59b passed cloud232Python+66Deno and exact
six-queue artifact roundtrip/cleanup. New backup and partial-install/umask failures
are documented and preserved. Remaining: hosted source/recurring acceptance,
current free-budget verification, official closes and email/device checks.
Email server redirects are still pending Auth-config permission (403), not fixed.
Prediction work remains excluded. Do not reactivate the consumed old quote trial.

# Earlier priority: email redirect fix — November 2, 2026

Read [AUTH_REDIRECT_FIX_20261102.md](AUTH_REDIRECT_FIX_20261102.md) first. User
prioritized verification links before other migration work. Hosted probes confirm
both exact website/mobile redirects fall back to localhost. Auth configuration
GET is 403; owner was asked for read/write access, pending. Server routing remains
unfixed until settings/readback succeed. No need to request source authority again.

Website canonical HTTPS/PKCE fix is deployed, byte-verified and browser-smoked.
New signed APK with secure mobile email callbacks enabled was cloud-built
successfully (run41417855937) and downloaded. 37 mobile,15build-config and
5management-plan tests pass, plus PHP auth suites; independent review closed.
Narrow pinned Auth-config utility is ready; inspect actual templates once access
exists. Default branch untouched; no emails/accounts/financial writes/schedules.

# Previous continuation — November 2, 2026

Read [APP_CONTINUATION_20261102.md](APP_CONTINUATION_20261102.md) first. Owner
maintenance, portfolio sorting, recent sessions and separately annotated purchase
days are live. SQL020–024 are installed; collection and official-close valuation
remain disabled. A signed Supabase APK was built by GitHub Actions and downloaded.
One genuine 214-row history capture was appended with raw-byte/value verification;
no original observations were replaced. Current owner has 16 buys, 3 sells,
10 holdings and 22 snapshots; all 55 original private source records remain intact.

Managed workers now have positive pre-source admission, coordinated dividend
publication, six-queue v2 checkpoints and bounded single-company refresh. All
318 managed local tests pass. Private publication and cloud verification passed:
223 standalone Python, 61 Deno, exact six-queue readback and synthetic artifact
cleanup. Corrected private profiles include the required archive project binding.
Scoped secret-write capability is verified. A new one-company genuine fundamental
acceptance passed: 20 real responses, one byte-verified private archive and one
accepted projection. Local exact-package runner used hosted gateways; this does
not verify source access from GitHub. No existing company/financial values changed;
all 55 originals reverified. Temporary lease/secrets removed and prior disabled
controls restored. Current database: 334,403,251 bytes. Remaining: hosted-runner
and other-kind source acceptance, recurring policy/free-budget gates, official-close
source verification and email/second-owner/phone acceptance. November usage and
Auth-config read-access questions are pending. No prediction work.
Older entries below are historical and do not override this checkpoint.

# Earlier November 1: first genuine owner recovery verified

After the owner reported signing in, a fresh read-only, verified-TLS database
check confirmed the larger approved account exists, has a confirmed email and
has signed in. Its genuine SQL019 claim succeeded: 13 buys, 3 sells, 8 holdings
and 22 P&L snapshots. All 46 private provenance payloads match the original
staging records and the approved recovery-plan pin. Current application counts
match those imported counts. All 55 original source records were reverified.
The second approved account does not yet exist; its nine records remain reserved.
Anonymous application relation privileges remain zero. Database size observed:
334,026,419 bytes. No hosted writes or account impersonation in this check.

Read [WEBSITE_PUBLICATION_20261101.md](WEBSITE_PUBLICATION_20261101.md).
Private aggregate receipt: the publication directory's
`genuine-owner-acceptance.private.json`. First-owner signup/login/recovery is no
longer pending. Reset/logout, second-owner/device acceptance, admin UUID setup,
fresh-price/job activation and official-close valuation work remain outstanding.
SMTP configuration/delivery details have not been separately verified merely
from the confirmed account. Other gates and the exclusion of prediction work
remain unchanged.

# Earlier November 1: website published; genuine owner login pending

Read [WEBSITE_PUBLICATION_20261101.md](WEBSITE_PUBLICATION_20261101.md) first.
The owner explicitly requested publication. The old live website was confirmed
and replaced: 67 runtime files verified, 44 changed, followed by three verified
confirmation-flow updates. Private upstream config was excluded from the upload.
The two exact approved recovery bindings and SQL019 recovery control are now ON,
after original-source/plan verification, with no accounts or financial rows
created by activation. Original 55 records remain private and unchanged.

The new live login/signup renders correctly and anonymous Portfolio redirects
to login. Both API keys are accepted. Confirmation now returns users signed out
with an explicit password-login instruction. The owner must create/confirm their
real account and sign in with their own password to claim the saved portfolio;
zero claims existed at activation verification. Do not fabricate Auth/JWTs or
claim that binding activation itself restored rows to an account. Real email
delivery, redirect allowlists, actual recovery and subsequent admin UUID setup
remain to verify. Private rollback and receipts are in the publication directory.

Direct legacy source requests now have a default-OFF environment gate; session
status stays unavailable without evidence. Preview, valuation, collection and
schedules remain OFF; SQL020/021 remain uninstalled. Official closing prices are
required for future saved daily P&L. No mobile release, root Git push or prediction
work occurred. Older notes that say every control is off or the website is
undeployed no longer describe the website/recovery state.

# Earlier November 1: portfolio displays fixed; official closing prices required

Read [PORTFOLIO_AND_LISTING_JOBS.md](PORTFOLIO_AND_LISTING_JOBS.md) first. The
owner explicitly requires verified official closing prices for saved daily P&L.
Both clients now label recorded-price estimates and suppress incomplete totals.
SQL020 reviewed listing additions and SQL021 official-close-only valuation are
staged/tested, NOT installed. 301 Python, 102 Flutter, 17 PHP price cases, 5 web
controller/template, 9 listing SQL and 25 official-close SQL tests pass; Flutter
analysis is clean. No real official-close source has yet been verified/admitted.
No hosted writes, source requests, client deployment, accounts or emails changed
in this continuation. The previous disabled private worker release remains valid.
Continue application work only; prediction work remains excluded.

# Latest November 1: private cloud worker update and durable retry integration

Read [CLOUD_AUTOMATION_20261101.md](CLOUD_AUTOMATION_20261101.md) first. The private
worker distribution now includes checkpoint restore, failure persistence,
readback and bounded retention; the old non-durable job is disabled. Main worker
tests pass (295); the final synthetic cloud run passed 209 Python and 59 Deno
tests. A synthetic artifact upload/download/four-queue restore and exact deletion
also passed; zero artifacts remain from that run. No collector, schedule,
backend control, account or email was activated. Continue application work only;
prediction work remains excluded. Earlier checkpoint packages stay immutable.

# Latest October 31: approved backend upgrade installed and verified disabled

Read [APP_COMPLETION_20261031.md](APP_COMPLETION_20261031.md) first. SQL017–019
and archive/projection v7 are installed and verified; app publisher stays v8.
All controls remain off, anonymous application access remains blocked, and every
preexisting table hash is unchanged. A fresh verified private backup was saved.
Do not repeat this install or revive the consumed quote trial. Authentication,
exact portfolio claim, company context and durable publication changes passed
local regression suites; real email/device acceptance and cloud job completion
remain. Continue website/mobile/automation only; prediction work is excluded.

The older checkpoints below are historical and do not override this state.

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

# Latest live continuation: disabled fallback upgrade installed

Read [DISPLAY_FALLBACK_INTEGRATION.md](DISPLAY_FALLBACK_INTEGRATION.md) first.
The owner-approved SQL015 + publisher v7 upgrade committed and was verified by
fresh hosted source readback. All nine function files match their pinned packages,
all three endpoints remain disabled, all 15 application-table fingerprints and
archive/candidate/trial records are unchanged, and anonymous application access
remains denied. No source requests or schedules were activated. Do not repeat
this completed permission/install. Continue the original price job’s remaining
row/persistence and enrichment behavior; real account/email/device and screen
cutover checks remain outstanding.

# Latest local continuation: fallback connected through existing feed readers

Read [DISPLAY_FALLBACK_INTEGRATION.md](DISPLAY_FALLBACK_INTEGRATION.md) first.
Opt-in v2 now binds references to archived evidence and carries them through the
existing publisher/RPC to PHP and Flutter readers. Local full-chain checks pass,
as do 209 Python,18 Deno,32 SQL and70 Flutter cases plus clean analysis. Old ratio
calculations match all81 preserved company inputs. A pinned disabled-upgrade
package is prepared; nothing new was deployed or captured. Main screen cutover,
price/ratio persistence, real signup/preview acceptance and recurring jobs remain.

# Earlier owner correction: migrate existing function behavior

Read [FUNCTION_MIGRATION_PARITY.md](FUNCTION_MIGRATION_PARITY.md) first. The owner
wants direct migration/reuse of the old app and functions. The old price fallback
was found and ported locally: the saved capture can display all 81 stocks + MASI,
with 17 clearly labeled instrument references whose trade dates are unknown.
205 managed-worker tests pass; the original quote candidate and hosted services
are unchanged. Existing secondary adapters/router were located locally. Complete
the five original jobs' actual parity before adding broader infrastructure.

# Latest live continuation: genuine archive + shadow publication verified

Read [LIVE_CAPTURE_HANDOFF.md](LIVE_CAPTURE_HANDOFF.md) first. The updated token
worked. One genuine capture was archived/read back exactly and shadow-published:
64 stock quotes + MASI, 17 missing stocks explicitly retained. Final signed-in
preview acceptance stopped because Auth has no current accounts. All controls,
provider, lease and temporary secrets were disabled/revoked/removed; fresh privacy
and original-data checks pass. Do not repeat the consumed trial or reopen its lease.

# Earlier live continuation: trial gate installed, token update pending

Read [TRIAL_ACTIVATION_HANDOFF.md](TRIAL_ACTIVATION_HANDOFF.md) first. The owner
approved the bounded trial; exact SQL014 is installed and original data/functions
verified. Hosted no-op service RPC and anonymous preview denial checks pass.
Storage headroom is supported by owner screenshots. Everything remains disabled;
caller-secret provisioning returned HTTP403 and awaits the requested token scope
update. Do not ask again for trial approval or reinstall SQL014.

# Earlier continuation: bounded manual-trial preparation

Read [MANUAL_TRIAL_HANDOFF.md](MANUAL_TRIAL_HANDOFF.md) first. Local trial gates
and a pinned five-minute quote/MASI proposal are implemented, with 37 new passing
cases, also independently rerun and reviewed. Fresh hosted read-only checks
confirm exact 81-company mappings and the
unchanged private, disabled backend. SQL014/trial activation remain unperformed
and outside the completed disabled-install authorization.

# Latest live checkpoint: disabled backend installation complete

Read [DISABLED_BACKEND_INSTALL_HANDOFF.md](DISABLED_BACKEND_INSTALL_HANDOFF.md)
first. The authorized private bucket, SQL009/010/013 and three functions are
installed; all controls remain off and no data providers/pins were seeded.
Nine hosted source files match the reviewed bundle, three exact disabled
responses passed, and original-data/privacy checks passed. SQL011/012 and all
collection/schedules/cutover remain outside this completed phase. Approximate
app/backend progress: 80% complete / 20% remaining, excluding prediction work.

# Latest checkpoint: independent review fixes closed

Read [DEPLOYMENT_REVIEW_FIXES.md](DEPLOYMENT_REVIEW_FIXES.md) first.
The explicitly authorized reviewer found five real issues; all are fixed and
independently re-reviewed closed. Revision 2 passes 347 test cases plus two
integration checks. No services were deployed or enabled. The proposed first
installation remains narrow and disabled (bucket, SQL009/010/013, three functions),
subject to scoped permission and Management access; SQL011/012 are a later phase.

# Latest October 29 continuation: backend deployment review

Read [DEPLOYMENT_REVIEW_HANDOFF.md](DEPLOYMENT_REVIEW_HANDOFF.md) first.
The private 41-file generic deployment bundle is prepared and hash-verified;
142 test cases passed, including combined SQL009–013 and interruption rollback.
Fresh read-only checks confirm private database access, 332,740,275 database
bytes and 145 matching hosted/local timezone samples. Nothing is installed or
enabled; independent review and the documented deployment/access gates remain.

# October 29 continuation: mobile email authentication

Read [MOBILE_EMAIL_AUTH_HANDOFF.md](MOBILE_EMAIL_AUTH_HANDOFF.md) and
[AI_MIGRATION_HANDOFF.md](AI_MIGRATION_HANDOFF.md) before older checkpoints.
Opt-in Android confirmation/recovery is implemented, with clean analysis and
65 Flutter tests passing. It is still disabled by default; SMTP/device acceptance,
managed deployment and schedules remain pending. Approximate app/backend progress:
75% complete / 25% remaining, excluding prediction work.

**AI transfer handoff — October 28:** Give the next AI [AI_MIGRATION_HANDOFF.md](AI_MIGRATION_HANDOFF.md) and project access. It consolidates current priorities, live versus staged state, test evidence, private-file references, safety constraints, the approximate 25–30% remaining estimate and the next implementation order. This transfer update changed documentation only.

**Latest continuation — October 28, app preview:** Read [APP_FEED_PREVIEW_HANDOFF.md](APP_FEED_PREVIEW_HANDOFF.md) first. Exact mappings and a separate quote/MASI preview are implemented; stale and missing values stay unavailable. New PHP/Flutter readers and draft SQL010 are tested. Private code publication passed; hosted installation and active app cutover remain gated.

**Earlier continuation — October 28, private archive:** Read [PRIVATE_ARCHIVE_GATEWAY_HANDOFF.md](PRIVATE_ARCHIVE_GATEWAY_HANDOFF.md) first. The scoped gateway/outbox passed 101 worker, 19 gateway and 25 local SQL tests; worker/gateway tests also passed privately in GitHub. Code is published privately; no gateway, bucket, SQL or schedules were deployed. Continue app feeds/adapters while respecting the documented installation gates.

**Earlier continuation — October 28:** Read [WEB_MOBILE_AUTOMATION_RESUME_20261028.md](WEB_MOBILE_AUTOMATION_RESUME_20261028.md) first. Updated-key mobile integration and APK scanning passed; all 81 preserved diagnostic books normalize with explicit null last-trade summaries. The reviewed generic workers were published privately and all 82 tests passed locally and on the private cloud runner. Live collection, storage, SMTP and final cutover remain unfinished. Earlier checkpoints below are historical.

**Historical pause — October 27 evening:** Read [WEB_MOBILE_AUTOMATION_RESUME_20261027.md](WEB_MOBILE_AUTOMATION_RESUME_20261027.md) for that checkpoint. Keys were refreshed, privacy and web Auth reverified, the debug APK rebuilt, and market/depth collectors tested against preserved/diagnostic data. The later October 28 continuation above supersedes this pause.

**Paused continuation — 2026-10-27:** Read [WEB_MOBILE_AUTOMATION_HANDOFF.md](WEB_MOBILE_AUTOMATION_HANDOFF.md) first. It records the live privacy change, client fixes, private cloud probes, tests and exact remaining work. Implementation is paused at the owner’s request. Older checkpoints below remain historical.

# Appwrite replacement: resume handoff

Updated 2026-10-25, after restoring both saved portfolios into private staging
and preserving the newly found public backup evidence.
Read this first when resuming migration. It supersedes older export-first and
design-first instructions in historical project documents.

## Latest user priority: restore and reconcile data first

**Latest user clarification (October 25): preserve BOTH original accounts.**
The two groups are distinct users in the same backup, not competing database
versions. The user explicitly deferred assigning each portfolio to its new user.
Do not ask again which portfolio to keep, merge them, select the larger account,
or treat login assignment as a blocker to continued migration work.
Read [PERSONAL_DATA_RECOVERY.md](PERSONAL_DATA_RECOVERY.md).

**Both portfolios are now restored in admin-only staging:** 55 complete original
records (16 buys / 4 sells / 12 holdings / 23 P&L), with original ownership,
permissions, dates and financial values intact. Full import read-back and an
independent read-only verification passed. `anon`, `authenticated` and
`service_role` have no staging access. No Auth account was created/assigned and
no application portfolio table was changed. `tools/restore_saved_portfolios.py`
supports local validation, atomic `--apply`, and read-only `--verify`; logs expose
counts/owner placeholders only. Owner 1's ledger matches all eight holding
quantities; owner 2's two holdings without saved trades are preserved as snapshots.

**Newly found public backups are now archived:** seven public-only extracts,
2,266,152 bytes, including the 23 additional original market records, old quote,
legacy mapping field and historical SQL price variants. All seven were fully
byte-verified in `recovery_archive.files`. Mixed SQL/account tables were not
uploaded by this tool; canonical history/latest quotes/cleanup markers remain
unchanged. Use `tools/archive_earlier_backups.py`; its safe SQL parser executes
no SQL and excludes private literals/sections.

Latest aggregate verification: **16 staging datasets / 110,723 documents**,
including the 55 private records across two original owners; **1,797 archive
files / 33,932,670 original bytes**; database **282,932,915 bytes (~282.9 MB)**.
Fifteen focused Python regressions passed. Login assignment stays deferred;
next priority is verified recent-market catch-up and remaining data/source
reconciliation, then managed jobs/client cutover. No deployment/commit/push ran.

**New discovery after the user recalled earlier database saves:** read
[EARLIER_DATABASE_BACKUPS.md](EARLIER_DATABASE_BACKUPS.md). The September export
was already used, but the root legacy SQL and August rename backup were now
compared directly. The rename snapshot has **23 original market IDs plus one
old quote ID absent from the current recovery**, with a verified MANAGER→MANAGEM
name change. The legacy SQL retains 81 extra `TINCKER_CODE` mapping values and
64 differing prices on known company-days. Public-only evidence is saved under
ignored `backup_live_nonpersonal_20261024/earlier_database_search/`; the October 25
continuation above archived the public extracts in Supabase. Further reconcile
them before adopting canonical changes. Do not
overwrite the audited recovery or restore deliberate `DELETE` cleanup markers.

**Latest continuation:** [DATA_RECONCILIATION.md](DATA_RECONCILIATION.md).
All 56,756 independent daily references are separately queryable and fully
verified; 16,489 inconsistent OHLC ranges are flagged, and 724/725 absent days
have no positive trade-activity evidence. Canonical ticks/ratios stay intact.
Official records filled sector/shareholder details for all five previously
unmatched issuers: coverage is 81 sectors / 80 shareholder disclosures / 74
descriptions. The original financial source still lacks those five issuers.
45 mismatched dividend periods (43 labeled 2027 but dated 2025) are preserved
in the raw DB and withheld from client financial claims; Python collector,
PHP and Dart share nine regression cases. No collector was deployed.
Archive totals are 1,790 files / 31,666,518 bytes; database size is approximately
282.5 MB. All six supplemental tables passed anonymous REST and actual PHP
profile/daily reads passed. All 26 Flutter tests passed with clean analysis.
Next work: verified post-October-21 catch-up, price/OHLC disagreements, replacement
dividend evidence and remaining issuer financial/description gaps. No commit,
push, production switch or deployment was performed in this continuation.

**Latest clarification: EVERY non-personal dataset and field.** Read
[ALL_NONPERSONAL_DATA_RESTORE.md](ALL_NONPERSONAL_DATA_RESTORE.md) first for the
expanded restore, current gaps and completed issuer-alias recovery. The earlier five-table
audit was complete only for that saved public recovery, not the whole requested
scope. New supplemental tables and a protected archive are installed and verified;
all 1,686 order-book objects, full company/market responses, reference/history
evidence and screened diagnostic records are now preserved in Supabase as well.
The expanded destination has 81 profiles; annual charts for 61 companies,
quarterly/interim data for 59/57; two full market snapshots; five source dividend
calendars; sector/issuer references; 81 latest order books and 1,785 protected
archive objects, including preserved source revisions. The archive contains all
136,562 saved order-book records and the 56,756-row independent price file.
LHM's changed issuer-name lookup was reconciled through its verified saved alias.
That earlier checkpoint measured approximately 208.2 MB. Public read-only REST and actual PHP
financial-chart/interim reads passed; archive access remains admin-only.
The five unmatched source symbols, post-snapshot history, dividend-quality
issues and inaccessible current cloud/operational inventory remain explicit gaps.

After mobile integration, the user explicitly prioritized filling the database
with the Appwrite data before continuing automation. Follow
[DATABASE_RESTORE_STATUS.md](DATABASE_RESTORE_STATUS.md) next.

A fresh live read-only comparison verified **all 110,662 public application rows**
against the saved recovery: 81 companies, 81 symbol mappings, 110,067 observations,
350 dividends and 83 last-known quotes. Every original ID and typed value matched;
zero missing/changed/extra rows. All 81 companies have history through October 21
09:29:37 UTC. The original public staging subset still contains 110,668 records
in 12 datasets; four private datasets/55 records were subsequently added.
This proves the saved public restore, not the locked latest cloud database.

Independent archive comparison found 725 evidenced daily company-day gaps and
364 differing overlap prices (55,667 exact matches). Candidate/conflict artifacts
are saved under ignored `backup_live_recovery_20261022/`; no original data was
overwritten and no artificial daily-bar timestamp was inserted. The restored
2027 dividend table also has inherited confirmation flags requiring review.

Next work is data reconciliation/catch-up (including current quotes, fundamentals
and dividend issues), ahead of managed job rollout. Keep the accepted personal
account reset; original private backups and diagnostic logs remain preserved.
`tools/audit_supabase_recovery.py` is the new repeatable check; five audit tests pass.

## Latest implementation checkpoint

Fresh-account private tables and atomic trading are now installed in Supabase.
PHP and Flutter login/signup/confirmation notice/refresh/logout and private
portfolio reads/trades are wired behind explicit `MYINTERPRETER_BACKEND=supabase`
selection. The default and existing production clients remain Appwrite.
Flutter now uses the official SDK, encrypted session storage, paginated public
reads and the atomic trade RPC. Read [SUPABASE_MOBILE.md](SUPABASE_MOBILE.md).
The ignored public-only `myinterpreter_app/backend.local.json` is prepared; use
`flutter run --dart-define-from-file=backend.local.json` from the mobile directory.
No database/secret API credentials are included in that config or app.

Latest verification: all 26 Flutter tests passed; app analysis found no issues;
four public build-config tests and shared-contract generation check passed.
The actual mobile SDK also passed login, owner privacy, 1,501-row pagination,
buy/sell retries, average-cost updates, token refresh, persisted recovery and
logout against Supabase. Its two temporary accounts were deleted; no emails
were sent. A local **debug** Android compilation passed with process-only Java
17 settings after the default Java 25 installation lacked a compiler. The APK
is `myinterpreter_app/build/app/outputs/flutter-apk/app-debug.apk` (166,411,794 bytes).
Every APK entry was scanned: the configured server key, database URI and database
password were absent; the expected public client key was present. No Android
device/emulator was attached, so interaction/keychain checks remain pending.
GitHub Actions can select a backend through public-config generation; repository
settings, commits, pushes and workflow execution have not been performed.

Read [SUPABASE_PRIVATE_PORTFOLIO.md](SUPABASE_PRIVATE_PORTFOLIO.md) for the complete
schema, Auth/session behavior, configuration, tests and remaining limitations.

Completed live tests: two-owner RLS isolation; anonymous and direct mutation
denial; snapshot privacy; partial/full/fractional holding behavior; oversell and
changed-retry rejection; rollback after a partial write; identical retry creates
one trade; real Auth login/refresh; localhost PHP login/CSRF/cookies/trade/logout;
and simultaneous sells cannot oversell. SQL fixtures rolled back, and live Auth
fixtures were deleted without sending emails. Schema repeat application passed.

New files include `003_private_portfolio.sql`, `core/SupabaseApp.php`,
`core/backend.php`, `core/session.php`, `core/supabase_session.php`,
`handlers/supabase_auth.php`, `config/supabase.example.php`, guarded migration and
live-check tools, and Auth/session/SQL tests. New admin UUID, SMTP, actual host
and mobile-device validation, job writes and deployment are still pending. Market data
freshness is unchanged by this step.

The user asked whether a commit/push checkpoint was missed and emphasized
credentials. No commit or push has been made during this rebuild. Local `master`
is 11 commits ahead of its **last recorded** upstream reference (not freshly
fetched); latest local commit is `b5f1507`. The earlier work and current rebuild
also have uncommitted files. Never `git add .`: thousands of unrelated research
artifacts exist. A credential/source-host scan of the 11 outgoing commits'
123 distinct changed objects found no matches to current credentials/private
source hosts or the checked secret patterns. The source candidate scan found
only a fake PostgreSQL test URI, not a real credential. This is a scoped audit,
not proof that every untracked research artifact is safe to publish.

## Current user direction and authorization

- Goal: leave the expiring Appwrite Education plan for managed hosting that
  works while the user's PC is off. Aim for free or inexpensive operation;
  guaranteed $0/month has not been established.
- New Auth logins remain acceptable; old Auth/password export is not required.
  The October 25 clarification supersedes the empty-portfolio reset: preserve
  BOTH saved portfolios separately and assign their new users later. Their 55
  original records are now staged privately; do not discard either owner.
- Preserve existing local backups and public history. Starting fresh does not
  authorize deleting private backups, cloud records, projects or subscriptions.
- **Implementation is authorized.** After the completed feasibility assessment,
  the user explicitly corrected the handoff: "wdym 'dont build yet' the purpose
  IS to build". This supersedes the earlier temporary assessment-only restriction.
- The documentation is a checkpoint before `/compact`, not a new approval gate.
  On resume, continue building the fresh-account Supabase replacement from the
  verified pilot. Do not ask again whether implementation is authorized.
- Start with fresh authentication and owner-isolated private portfolio tables,
  then client integration and cloud automation, using the sequence below. Reuse
  completed recovery/schema work instead of repeating it.
- No support message, subscription change, paid service purchase, permanent user
  account creation, production deployment or Appwrite deletion has been performed.
  Synthetic test accounts were created and deleted during live checks.

## Assessment result

**A working myInterpreter replacement is feasible without further Appwrite
access**, using the existing PHP/Flutter source, retained public history,
direct data sources, new authentication and an empty private portfolio.

This is an engineering assessment, not a claim that every old cloud record can
be reconstructed. Full evidence and source references are in
[APPWRITE_FREE_REBUILD_FEASIBILITY.md](APPWRITE_FREE_REBUILD_FEASIBILITY.md).

Verified read-only during the latest assessment:

- Quote feed: **81/81** saved symbols, all with positive price values; 60 detail
  rows plus the market index. Last-trade dates are not retrieval dates.
- Dividend calendars: **296 rows for 2022–2026**. The 2027 attempt failed
  validation; do not treat it as an empty calendar or overwrite projected data.
- Fundamentals: four samples tested. Three had 17–23 populated computed fields;
  one bank had only 3/23, with missing fiscal year/share count/core financials.
  The current adapter documents missing bank statements and preserves saved
  values instead of overwriting them with nulls.
- Fundamentals registry: **76/81** saved symbols matched. Direct stock fallback
  failed for the other five. A fully automated fresh-universe rebuild is not
  proven. The saved baseline and official issuer reports provide alternatives;
  bank data extraction and reconciliation are still work to do.
- Fresh daily history: three sample symbols worked through **2026-10-23**.
  Two returned 737 rows starting 2023-10-25; a newer listing returned 312 rows
  starting 2025-07-15. Do not infer complete all-symbol coverage from three probes
  or assume that the source retains history indefinitely.
- Order-book source: 81 symbols discovered; one sample returned a summary plus
  five bid and five ask levels. This was not a trading-session or cloud-host test.
- All 1,713 files in the saved live-export bundle still match size/hash checks;
  all eight active function source archives were read successfully.
- Recovery market gzip and independent daily parquet still match their hashes.

Important limits:

- Unsaved historical intraday ticks/full depth cannot be recreated from daily
  price endpoints. Use retained captures and label remaining gaps honestly.
- Today's fundamentals cannot reproduce old point-in-time ratios exactly.
- Corporate-action adjustments, names/aliases, source disagreement, explicit
  unknown values and original timestamps require reconciliation.
- Cloud-region source access, production email, new private-user isolation,
  app integration, unattended scheduling, restore tests and costs remain unproven.

## Work already implemented before the assessment-only instruction

The user had previously authorized destination preparation. These are completed
pilot artifacts, not a deployed replacement:

| Area | Current verified state |
| --- | --- |
| Supabase connection | Database login and TLS passed; publishable and secret keys accepted. Credentials never printed |
| Private recovery staging | `migration_stage.datasets` and `migration_stage.documents`: **110,668 documents in 12 datasets**, fully read back against local sources |
| Public market tables | `public.company` 81; `format` 81; `data` 110,067; `dividends` 350; `latest_prices` 83; **110,662 total rows** |
| Public permissions | SELECT-only grants for `anon`, `authenticated`, `service_role`; RLS on five public tables. Live role probes denied INSERT/UPDATE/DELETE and private staging access |
| Public PHP reader | `core/SupabaseMarket.php`; eight live API/SQL comparisons covering 919 returned rows plus exact counts passed |
| Size | **175,797,939 bytes (175.8 MB)** including private staging, public tables and indexes; below the 350 MB pilot target |
| Repeatability | Both staging and market import repeat runs recognized existing datasets/rows without duplicates. Market repeat run compared every typed value |
| Existing clients/jobs | Production remains Appwrite; PHP/Flutter opt-in and new private tables now exist. Managed jobs still need integration |

Staging includes seven fresh source-response objects that have not been promoted
into application tables. Typed market tables are recovery candidates, not a live
feed or exact current Appwrite snapshot. Their newest recovered quote is October
21; one older series still has a May 25 observation. The assessment's newer live
responses stayed in memory and were not imported or saved.

See [SUPABASE_PUBLIC_PILOT.md](SUPABASE_PUBLIC_PILOT.md) for table/adapter behavior
and [DATA_RECOVERY_STATUS.md](DATA_RECOVERY_STATUS.md) for recovery provenance.

## Artifacts and implementation entry points

All `backup_live_*` directories below are ignored by Git and contain sensitive or
restricted source details. Do not commit, dump or upload them indiscriminately.

| Location | Contents |
| --- | --- |
| `backup_live_20260919/` | Original 11-collection September database backup; 80,555 documents |
| `backup_live_recovery_20261022/baseline/` | Hash/count-verified copy of those 11 collection exports, including private records |
| `backup_live_recovery_20261022/recovered_market.jsonl.gz` | 110,067 original market IDs across 65,659 series-days; 83 names including index/variants; May 29, 2023–October 21, 2026; 842 MASI days |
| `backup_live_recovery_20261022/recovery.sqlite` | Recovery records and source provenance; no inferred deletion reconciliation |
| `backup_live_recovery_20261022/independent_daily_history.parquet` | 56,756 daily rows for 81 symbols; keep separate pending source/corporate-action reconciliation |
| `backup_live_public_20261022/` | Saved public market/calendar responses and one fundamentals sample; raw evidence and manifest |
| `backup_live_20261022_101401/` | Known 1,686 storage files; eight active function sources, function settings/variables and deployment metadata; 1,713 content artifacts total |
| `backup_live_recovery_20261022/supabase_*_report.json` | Local verification, import, public mapping and permission/API reports; aggregate results, not credentials |

The saved company baseline has core BPA/ROE/share-count/equity values for all 81
companies, growth for 80 and dividend-per-share for 59. Do not delete it just
because some current source endpoints also work.

Code prepared so far:

- `migrations/supabase/001_private_staging.sql`
- `migrations/supabase/002_public_market.sql`
- `migrations/supabase/market_contract.json` — explicit public-column allowlist
- `tools/stage_supabase.py`, `tools/verify_supabase_staging.py`
- `tools/migrate_supabase_market.py`
- `core/SupabaseMarket.php` — standalone public reader, not wired into pages
- `tools/check_supabase_connection.py`, `tools/check_supabase_market.py` and `.php`
- `tools/export_appwrite.py`, `tools/recover_appwrite_market.py`,
  `tools/refetch_public_data.py`

Validation previously passed: **15 Python Supabase tests**, PHP reader checks,
PHP lint, Python compilation, live role/API comparisons, full payload comparisons
and idempotent imports. **11 Appwrite exporter tests** passed after prioritizing
accounts and private collections. Documentation-only work does not require
rerunning live imports or all source probes.

## Appwrite blocker: historical context, no longer a fresh-start prerequisite

- Education expiry was inferred around **2026-11-10** from the October 22
  remaining-days screenshot; exact cutoff was not independently confirmed.
- Billing screenshot: Oct 6–Nov 5. A reset around Nov 6 is an inference, not a
  confirmed reset timestamp.
- October 24 retry: database HTTP 402 `limit_databases_reads_exceeded`; users and
  teams HTTP 401 missing `users.read` / `teams.read`; zero pages exported.
- The user tried project Settings via the project menu and supplied a screenshot
  confirming the same quota-lock screen. Console API-key creation is blocked by
  that route too.
- `.appwrite-export-key` was created as an empty ignored file; no suitable key
  was supplied. Existing scoped keys cannot provide a complete database/auth
  export or remove quota restrictions.
- [APPWRITE_EXPORT_ACCESS_REQUEST.md](APPWRITE_EXPORT_ACCESS_REQUEST.md) is an
  unsent draft. Do not ask for old keys/accounts or make support/paid upgrades a
  prerequisite for the fresh-start approach unless the user changes direction.

## Authorized implementation sequence

1. Reuse public data/schema work; select and reconcile source inputs, stale
   labels, corporate actions and fundamentals exceptions. Preserve source history.
2. Fresh Supabase PHP authentication and empty owner-isolated private portfolio
   tables are implemented and tested; configure the new admin identity. Old user-ID mapping and
   password-hash compatibility are no longer required for the accepted reset.
3. Anonymous/user A/user B and transactional trade/holding checks now pass.
   Preserve existing calculation behavior; do not hide unrelated financial-rule
   changes inside the migration.
4. PHP and Flutter opt-in integration is implemented. Continue with market administration and verify the
   actual PHP host, signup/login/logout, persistence and portfolio operations.
   Production email needs a deliberate SMTP setup.
5. Adapt Python jobs/storage for managed execution. Cloud Run + Scheduler + R2
   remains the proposed pilot architecture; no Google/R2 account, billing or
   deployment setup was completed. Verify source access from the selected host,
   job durations, schedules/timezone, retries, overlapping runs, backups and cost.
6. Validate a trading session and backup restoration. Android release builds
   come from GitHub Actions, not a local `--release` build. Review deployment and
   cutover only when the concrete result is ready.

## Security and working-tree rules

- Working directory and actual Git root:
  `/mnt/shared/Share/studies/FinishedProjects/myInterpreter`.
- Many pre-existing tracked modifications and untracked design/research files
  exist. Preserve them. No migration commits/pushes were made. Do not reset the
  worktree or confuse earlier visual work with migration changes.
- `.supabase-migration.env` is configured and Git-ignored. It is now a symlink to
  `/home/redachen/.config/myinterpreter/credentials/supabase-migration.env`, with
  directory/file modes 0700/0600. The shared project filesystem forces 0755 and
  ignores chmod, so do not replace that symlink with an ordinary credential file.
  Contents were verified unchanged during the move. Its field names are
  `SUPABASE_PROJECT_URL`, `SUPABASE_DATABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and
  `SUPABASE_SECRET_KEY`. Read as data; never source it, print values, echo raw
  exception messages, or put credentials into command arguments.
- Other private key/config files include `.appwrite-ops-key`,
  `.appwrite-orderbook-key`, `.env.txt`, `config/secrets.php`,
  `config/sources.php` and function `sources.py`. Keep upstream identities and
  provider endpoints out of tracked documents/commits.
- Automatic approval previously rejected extracting/reusing the stored Appwrite
  CLI cookie for expanded access. Do not retry or bypass that rejection.
- Building the replacement is authorized. The earlier assessment itself used
  retrieval-only probes; no source `main()` functions or writes ran in that phase.
- Read `AGENTS.md`. Keep PHP/Dart dividend rules synchronized. Do not build
  Flutter release locally; use GitHub Actions when a release is authorized.
- Do not send external support/email messages without explicit authorization.
- Do not spawn subagents unless the user or applicable instructions request it.

## Suggested user message after compaction

> Read docs/MIGRATION_HANDOFF.md and docs/APPWRITE_FREE_REBUILD_FEASIBILITY.md.
> Continue building the fresh-account Supabase replacement. Start with
> authentication and private portfolio tables, reusing the verified pilot.
> Do not repeat completed exports, imports or research.

Implementation authorization is already established. Preserve the existing
backups and working-tree changes; paid purchases, destructive retirement and
external messages are not implied by the instruction to build.


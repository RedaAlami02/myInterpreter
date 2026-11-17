> **Current state (2026-11-17):** the Supabase migration is committed and
> merged into `master`; the repository now matches production. Start with
> [docs/CURRENT_STATE_20261117.md](docs/CURRENT_STATE_20261117.md), then
> [docs/OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md) and
> [docs/BUGFIX_LOG_20261117.md](docs/BUGFIX_LOG_20261117.md). The sections below
> record the earlier migration history.

# myInterpreter Project Handoff

## Active migration handoff — 2026-10-25

Latest user clarification: **preserve both original accounts; assign new users
later**. Both portfolios' 55 original records are now in admin-only Supabase
staging and passed full/independent read-back. No owners were merged or assigned
to new logins. See [PERSONAL_DATA_RECOVERY.md](docs/PERSONAL_DATA_RECOVERY.md).
Do not ask again which account to keep. The source-selection default is the
newest verified September backup; older copies remain supporting evidence.

Latest user steering: search earlier database saves. Findings are in
[EARLIER_DATABASE_BACKUPS.md](docs/EARLIER_DATABASE_BACKUPS.md): September export
already used; newly compared legacy SQL and an August rename snapshot reveal
23 additional original market IDs, one old quote and legacy mapping/price
evidence now preserved in seven byte-verified public-only archive extracts.
Canonical market history/latest prices remain unchanged. Further reconciliation
is needed before adopting those records as canonical corrections.

Current totals: 16 staging datasets / 110,723 records (including 55 private),
1,797 protected archive files / 33,932,670 bytes; database approximately 282.9 MB.
Fifteen focused Python tests passed. No deployment, commit or push was performed.

**Compaction/resume entry point:** read
[MIGRATION_HANDOFF.md](docs/MIGRATION_HANDOFF.md) first. It consolidates the latest
user decisions, completed work, artifact locations, checks, remaining gaps and
authorization boundary. The older design history below is not the active task.

Latest clarification: **every non-personal dataset/field**, including MASI and
general company/market information. The expanded restore is implemented and
under final reconciliation; read
[ALL_NONPERSONAL_DATA_RESTORE.md](docs/ALL_NONPERSONAL_DATA_RESTORE.md) first.
Latest continuation: [DATA_RECONCILIATION.md](docs/DATA_RECONCILIATION.md).
56,756 daily references are queryable with quality flags; official issuer
records raise sector/shareholder coverage to 81/80. Client projections quarantine
45 conflicting dividend periods without changing original records. Supabase
measures approximately 282.5 MB; archive totals are 1,790 files. Actual PHP/API
reads and all 26 Flutter tests passed. Next: verified recent market catch-up,
source-price/OHLC disagreements, replacement dividend evidence and remaining
financial/description gaps. No production switch or deployment was performed.

The user's latest priority is **database restoration/reconciliation before
automation**. A fresh SQL read-back matched all 110,662 recovered public rows;
all 81 companies have history. See
[DATABASE_RESTORE_STATUS.md](docs/DATABASE_RESTORE_STATUS.md) for the 725 daily
candidates, 364 source-price differences and inherited dividend/fundamental
issues to address next. Do not restart imports or assume the destination is empty.

Latest checkpoint: PHP and Flutter Supabase Auth/private portfolio integration
is implemented and live-tested. The mobile suite has 26 passing tests and clean
app analysis; two-user live SDK checks passed and temporary accounts were removed.
The Supabase debug APK compiled successfully and contains no configured server
key/database credentials. Real device validation is pending. The migration env
path now links to protected local storage because the shared filesystem ignores chmod.
See [SUPABASE_MOBILE.md](docs/SUPABASE_MOBILE.md). Public-only local debug config
is prepared and ignored by Git. Managed jobs, email, admin support and cutover
remain. No commit, push, release workflow or production deployment has run.

Latest user direction supersedes the export-first blocker below: the user accepts
a **new account and fresh personal information/portfolio**. The feasibility
assessment is complete, and the user explicitly clarified that **the purpose is
to build**. Implementation is authorized; continue from the verified pilot after
compaction without asking for build permission again. Findings are in
[APPWRITE_FREE_REBUILD_FEASIBILITY.md](docs/APPWRITE_FREE_REBUILD_FEASIBILITY.md).
Core app replacement is feasible with retained public history and direct source
feeds; an exact recreation of every cloud record is not established. Fresh
fundamentals have bank/unmatched-symbol gaps, and unsaved historical intraday or
order-book snapshots cannot be regenerated. No personal data was deleted and
no new account, code integration, database import or deployment was performed
for that assessment. Resume implementation with fresh authentication and private
portfolio tables; preserve backups and completed public data work.

The active user request is the managed Appwrite replacement, ahead of the
Education-plan expiry around November 10. The design history below is older
context, not a prerequisite for continuing migration. Current implementation
evidence is in [DATA_RECOVERY_STATUS.md](docs/DATA_RECOVERY_STATUS.md) and
[SUPABASE_PUBLIC_PILOT.md](docs/SUPABASE_PUBLIC_PILOT.md).

Supabase private staging has 110,668 verified documents. Five typed public market
tables now contain 110,662 verified rows; the PHP reader passed eight live REST
comparisons against SQL. Anonymous, authenticated and service roles can read
these public tables but were denied writes and private staging access. Repeating
the market migration matched every row without duplicates. Total measured
database size is approximately 175.8 MB, including private staging and indexes.

Existing production clients and jobs still use Appwrite. Supabase Auth/private
tables and opt-in PHP/Flutter integration are implemented. Authorized next work
is managed automation, admin/email setup and device/host validation. Old user-ID mapping and private-portfolio freshness
are no longer required for the user's accepted personal-data reset. Appwrite
database reads were quota-blocked at the last export attempt; auth export also
lacks sufficient key scopes. Public recovery observations are not an exact
current snapshot, and recovered quotes are stale. Do not deploy or cut over
using them as a live feed.

Superseded export-first direction: the user initially emphasized that the current
database and accounts were essential, before accepting a fresh-account rebuild.
An October 24 retry still returned database 402 and missing users.read/teams.read
401. `.appwrite-export-key` exists as an empty ignored file; the user was asked to
fill it or report API Keys access blocked. The exporter now captures accounts
first and private portfolio collections before public history. The updated
[support request](docs/APPWRITE_EXPORT_ACCESS_REQUEST.md) is prepared but unsent.

Credentials remain in the Git-ignored `.supabase-migration.env` and must not be
printed. Keep upstream source details and private recovery data out of Git.
Preserve unrelated working-tree changes. Do not reuse stored Appwrite CLI
cookies to expand access; automatic approval previously rejected that action.

_Updated: 2026-09-02 · baseline commit: `a323dca584a10dd1ef924b02689beba27df19497` · branch: `master`_

## Current Objective and Active Phase

The evidence-based interface audit and validated screener pilot are complete. After the Company Midday study, the user supplied eight broader financial-dashboard references and requested prototypes before reconsidering the whole project structure. Five review-only directions now compare those references with consistent myInterpreter content. No production restructuring has started; foundation selection is pending. LinkedIn media production remains deferred.

## Project and Personal Context

myInterpreter is a personal tool built to bring together information the author uses for the Bourse de Casablanca. It is not a commercial launch. The verified stack is a plain PHP web client, Flutter Android client, Python Appwrite Cloud Functions, and a shared Appwrite backend. The product covers market history, current prices, company ratios and fundamentals, dividends, holdings, transactions, charts, and operational monitoring.

## Priority Sequence

1. Preserve decisions and evidence in this handoff.
2. Audit the current web and accessible mobile UI.
3. Implement and review one representative screen.
4. Extend the chosen visual language across core screens.
5. Resolve correctness and capture-access blockers separately.
6. Resume LinkedIn production only when the user asks.

## Decisions and Constraints

- Preserve the personal-project story: “Every time I needed something, I added it.”
- Preferred future video hook: “How I turned Casablanca market data into an automated app.”
- Presentation-layer changes are authorized; broad architecture changes and unrelated correctness fixes are not.
- Do not commit, push, deploy, publish, modify production data, weaken access controls, or run a local Flutter release build.
- Never expose credentials, restricted provider identities/endpoints, personal records, or real portfolio data.
- Use a safe demo account or isolated, labeled fixture for portfolio visuals; none is currently established.
- Keep web and Flutter recognizable as one product without forcing identical layouts.
- Codex recommendation, not yet user-approved: use the light Atlas Ledger direction documented in [`design-review/DESIGN_SPEC.md`](design-review/DESIGN_SPEC.md). It most clearly removes the neon/glass dashboard pattern while preserving data density. Night Desk remains the lower-risk dark alternative.

## Known Findings and Uncertainties

Statuses distinguish evidence provenance. The prior review was performed by Codex on 2026-09-02 against the same baseline commit; relevant source was re-read and accessible public screens were visually audited during this task.

- `CORRECTNESS-01` — **VERIFIED IN CURRENT SOURCE:** PHP realized P&L uses FIFO (`statistics.php`); Flutter uses average cost over historical buys (`myinterpreter_app/lib/screens/statistics.dart`). Do not publish either as cross-client-consistent.
- `CORRECTNESS-02` — **VERIFIED IN CURRENT SOURCE:** PHP computes tax as `grandTotal * TAX_RATE` even when total profit is negative. Do not use portfolio-level tax totals publicly.
- `CORRECTNESS-03` — **VERIFIED IN CURRENT SOURCE:** one configured 1% all-in transaction commission represents several costs; TVA is not itemized. Public wording: “Estimated all-in transaction fees.”
- `CORRECTNESS-04` — **VERIFIED IN CURRENT SOURCE:** break-even includes configured fees and capital-gains tax. Public wording: “Estimated break-even after fees and tax.” It is not tax advice or a sell recommendation.
- `CORRECTNESS-05` — **VERIFIED IN CURRENT SOURCE:** the Flutter portfolio retains one dividend row per company, while the dedicated dividend screen processes multiple payments. Do not describe affected portfolio income as complete.
- `CORRECTNESS-06` — **VERIFIED IN CURRENT SOURCE:** admin `Company::test()` still scores some non-positive ratios green, unlike the guarded scraper and screener paths.
- `DATA-01` — **VERIFIED IN CURRENT SOURCE:** automation uses three retries, a broader ticker payload for missing trading activity, and some last-known-price preservation. It does not automatically switch to an independent secondary price source. Safe wording: “validation, retries, and safeguards for missing market activity.”
- `DATA-02` — **REPORTED IN PRIOR REVIEW + PARTIAL CURRENT RUNTIME EVIDENCE:** a read-only Appwrite metadata request returned HTTP 401 on 2026-09-02. The current local public screener successfully read configured collections and displayed 81 companies, but this does not verify total historical records, earliest dates, or live schema. Do not claim “three years” or “5,000+ records.”
- `DATA-03` — **VERIFIED IN CURRENT SOURCE:** schedules are configured in UTC. Convert to Casablanca time only for a stated date because its UTC offset varies.
- `PLATFORM-01` — **VERIFIED IN CURRENT SOURCE:** both clients target the same Appwrite project, but their calculation differences prevent claims of identical behavior or instant synchronization. Safe wording after runtime comparison: “web and mobile use the shared Appwrite backend.”
- `PLATFORM-02` — **VERIFIED IN CURRENT SOURCE:** the Flutter app vendors a patched Appwrite SDK. Use `flutter analyze --no-pub lib test`; unrestricted analysis is dominated by vendored code.
- `TEST-01` — **OBSERVED AT RUNTIME on 2026-09-02:** the generated counter widget test fails because the counter app no longer exists. First-party focused analysis had 34 findings and no analyzer errors.
- `SCHEMA-01` — **VERIFIED IN CURRENT SOURCE:** `appwrite_setup.py` does not recreate the full current schema; `latest_prices`, dividends, errors, projection fields, and newer trade fields are incomplete or separate.
- `DOCS-01` — **VERIFIED IN CURRENT SOURCE:** `ROADMAP.md` and README contain stale claims. Source and observed behavior outrank them.

## Corrected LinkedIn Production Plan

When resumed, build a publication kit centered on a roughly 55–70 second, 1080×1350 product video with the author’s own English narration. The story is: hook → personal need → verified history → automation → safe portfolio tools → market analysis → authentic mobile → personal ending. Actual application footage proves features; narration carries the story; overlays remain short.

Before recording, create a complete feature verification inventory and `FACTS_AND_CLAIMS.md`. Separate `VERIFIED`, `SOURCE ONLY`, `NOT FOUND`, `NOT WORKING`, and `UNSAFE TO SHOW`. Verify counts with authorized, paginated reads or omit them. Use only safe demo portfolio data. Exclude realized P&L, FIFO, affected dividend totals, and tax totals until corrected and tested.

Prepare one 125–150 word recording-ready script, timed visual mapping, and a simple recording guide. Before audio, use `CAPTIONS_DRAFT.srt` and label video exports as previews; reserve `CAPTIONS.srt` and a voiced final for the actual recording. Produce a real-product thumbnail, four to six coherent image alternatives with alt text, one modest 130–190 word post, and optional first-comment links only when verified public.

Keep raw assets separate from reviewed `publish/` exports. Verify media properties, frames, captions, privacy, readable mobile scale, and factual claims. Publishing, deployment, and repository visibility remain the user’s actions.

Source briefs are preserved outside the repository at `/home/redachen/Downloads/myInterpreter_LinkedIn_Codex_Prompt.md` and `/home/redachen/Downloads/myInterpreter_Save_Plan_And_Redesign_Prompt.md`. The corrections in this handoff govern future work where wording conflicts.

## Requested Feature Inventory for Future Media

| Capability | Current evidence | Publication disposition |
| --- | --- | --- |
| MASI movement and market history | Implemented in PHP dashboard; runtime/date span unverified | Verify after redesign |
| Automatic updates | UTC schedules and pipeline verified in source | Source-only until execution evidence exists |
| Cleaning, validation, retries, missing-activity safeguards | Verified in cloud-function source | Eligible with precise wording |
| Holdings, purchase cost, current value | Implemented in web/mobile | Requires safe demo and runtime check |
| Realized/unrealized gains and losses | Implemented but calculations diverge | Unrealized only after verification; realized excluded |
| Transaction history | PHP and Flutter sources located | Safe demo required |
| Transaction costs and tax | Flat commission and configured tax located | Use corrected wording; totals restricted |
| Portfolio, company, and market charts | Multiple web/mobile views located | Choose after visual audit |
| Break-even | Implemented in web/mobile portfolio | Describe as configured estimate after verification |
| Dividends and date types | Dedicated views and helper logic located | Dedicated screen preferred; verify runtime |
| Company color states | Four valuation thresholds located | Explain valuation signals, not overall health |
| Authentic mobile UI | Flutter implementation present | Device/emulator and safe login required |
| Shared web/mobile data | Same Appwrite project verified in configuration | Demonstrate comparable safe data; avoid sync guarantee |

## Design Plan and Acceptance Criteria

The audit is in [`design-review/DESIGN_AUDIT.md`](design-review/DESIGN_AUDIT.md). The public screener replaced the preferred portfolio pilot because it safely exposes real numerical content, filters, sorting, states, and responsive pressure without private records. Atlas Ledger and Night Desk were rendered with the same content/viewport; Codex recommended Atlas and implemented it as a scoped, reversible pilot. The decision and rules are in [`design-review/DESIGN_SPEC.md`](design-review/DESIGN_SPEC.md).

The pilot improves reading order, metric grouping, typography, numeric alignment, terminology, sorting semantics, touch controls, and narrow-screen behavior while preserving routes, DOM hooks, filters, calculations, and row data. Desktop/mobile before-and-after captures, behavior checks, exact public-data attribute comparison, PHP lint, and remaining limitations are recorded in [`design-review/VALIDATION.md`](design-review/VALIDATION.md). Acceptance is met for the pilot; rollout acceptance remains pending user direction and per-screen validation. Visual polish does not change or conceal known calculation defects.

## Backlog

| ID | Status | Evidence/location | Next action | Dependencies |
| --- | --- | --- | --- | --- |
| DESIGN-01 | Complete | [`design-review/DESIGN_AUDIT.md`](design-review/DESIGN_AUDIT.md), safe before screenshots | Use findings to prioritize rollout | None |
| DESIGN-02 | Awaiting user review | [`design-review/DESIGN_SPEC.md`](design-review/DESIGN_SPEC.md), Atlas and Night previews | Confirm Atlas or request Night Desk | Human visual preference |
| DESIGN-03 | Pilot complete; rollout pending | `screener.php`, `assets/css/screener-pilot.css`, `core/sidebar.php` | Extend confirmed direction to company detail, dividends, then safe portfolio | DESIGN-02 |
| CORRECTNESS-01 | Deferred | PHP FIFO vs Flutter average-cost logic | Reconcile and test in separate scope | User authorization |
| CORRECTNESS-02 | Deferred | Negative PHP portfolio tax | Correct with regression tests | User authorization |
| CORRECTNESS-03 | Deferred | Flutter portfolio dividend selection | Sum legitimate multiple payments | User authorization |
| CORRECTNESS-04 | Deferred | Admin ratio scoring | Apply non-positive guards consistently | User authorization |
| ACCESS-01 | Blocked | Appwrite metadata returned 401 on 2026-09-02 | Recheck only after credential/scope change | Authorized backend access |
| ACCESS-02 | Blocked for capture | No safe portfolio demo identified | User identifies demo account or authorizes isolated fixture | Human input |
| ACCESS-03 | Blocked for visual review | `adb devices -l` returned no connected devices on 2026-09-02 | Connect an authorized debug device/emulator when Flutter work resumes | Local device |
| TEST-01 | Existing failure | `myinterpreter_app/test/widget_test.dart` | Replace with meaningful tests in separate scope | Correctness/test scope |
| MEDIA-01 | Deferred | `linkedin-launch/` absent at baseline | Resume only on explicit user request | Stable redesign, safe access |
| MEDIA-02 | Deferred | Voice not recorded | Prepare one final script before requesting recording | Verified shots/claims |

## Current Work State

- Initial Git state: branch `master`, commit `a323dca584a10dd1ef924b02689beba27df19497`, untracked user-created `AGENTS.md` only.
- Created this handoff, `design-review/DESIGN_AUDIT.md`, `DESIGN_SPEC.md`, `VALIDATION.md`, two prototype pages, and safe before/after screenshots.
- Added the reference-driven `design-review/prototypes/company-midday.html` prototype, its scoped CSS, desktop/mobile renders, and `design-review/COMPANY_MIDDAY_DIRECTION.md`. It is not wired into production.
- Added the interactive five-direction dashboard comparison, ten desktop/mobile renders, and `design-review/DASHBOARD_DIRECTIONS.md`. The current recommendation is Research Desk as the structural foundation, Market Grid for dense tables, and Ember Noir only as an optional dark theme.
- Verified `origin/master` remotely at untouched baseline `a323dca584a10dd1ef924b02689beba27df19497`. A verified local Git bundle and a separate pre-restructure archive of current uncommitted design work are stored under ignored `safety-snapshots/2026-09-02-pre-restructure/`.
- Presentation changes: `screener.php`, new scoped `assets/css/screener-pilot.css`, and concise shared navigation labels in `core/sidebar.php`. No business logic, calculations, data, deployment, or Flutter source changed.
- Validation passed for PHP syntax, diff whitespace, browser rendering, filter/sort/navigation behavior, keyboard sorting, data-hook preservation, and 390 px overflow. Details and observed values are in the validation file.
- Temporary local PHP/browser/ADB processes are stopped before handoff. No task-started service should need cleanup on resume.
- `linkedin-launch/` remains absent and media work was not started. `design-review/` was absent at baseline and is now the design evidence directory.

## Human Input Needed

Review the concrete screener result and choose one visual branch: continue the implemented light **Atlas Ledger** direction, or switch the pilot to the restrained dark **Night Desk** direction. Before protected portfolio capture or Flutter visual validation, the user must also identify a clean demo account/authorize an isolated fixture and make an authenticated debug device or emulator available; these are later dependencies, not blockers for the current visual choice.

## Resume Instructions

Do not repeat the repository analysis, audit, prototype work, or screener pilot. First read the three `design-review/` documents and obtain the user's Atlas-versus-Night decision. If Atlas is confirmed, consolidate the scoped rules carefully into shared presentation primitives while migrating **company detail first**, then dividends; re-render each route before proceeding. If Night Desk is chosen, restyle the existing screener pilot to that direction and validate it before any rollout. Keep the protected portfolio and Flutter rollout source-only until safe access/device requirements are met. Do not begin LinkedIn production unless the user explicitly resumes it.
# 2026-10-24 implementation checkpoint

Fresh Supabase private tables and atomic trades are installed. PHP Auth and
portfolio integration are implemented behind an explicit backend selector and
passed live login/refresh, private-access, retry and concurrent-sell checks.
Continue from [docs/MIGRATION_HANDOFF.md](docs/MIGRATION_HANDOFF.md) and
[docs/SUPABASE_PRIVATE_PORTFOLIO.md](docs/SUPABASE_PRIVATE_PORTFOLIO.md).
Mobile-device validation, managed jobs, production email and cutover remain. Credentials/backups
remain excluded. No rebuild commit/push has been made; local `master` has 11
earlier commits ahead of the last recorded upstream reference.


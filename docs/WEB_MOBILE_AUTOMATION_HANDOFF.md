# Paused handoff — web, mobile and managed workers — 2026-10-27

The owner explicitly paused implementation. **Do not resume automatically.**
Resume the website/phone/Supabase and private automation work before prediction
work. Read this file first, then the ignored private handoff at
`private/app-cutover-20261027/HANDOFF.md`. The latter contains evidence paths and
private repository pointers; personal email mappings are in a separate ignored
record and must never enter public documentation or Git.

## What changed and what is actually live

| Area | Completed | Deployment state / remaining work |
| --- | --- | --- |
| Database privacy | Anonymous/PUBLIC reads revoked from all 15 application tables; no anonymous writes/RPCs; owner RLS preserved | **Applied to live Supabase**, independently rechecked over REST |
| Web authentication | Supabase-only default; old login/cookie/network branches removed; signed-in JWT required for market queries; login/refresh/logout/CSRF/trade retry/isolation tested live | Local implementation; no website deployment this continuation |
| Mobile authentication | Supabase default; Appwrite SDK dependency and active adapters removed; shared query helper; session integration retained | Debug APK built; actual SDK integration passed; no device test or release deployment |
| Financial calculations | Shared PHP/Dart FIFO avoids future/reused purchases; ambiguous/incomplete sales excluded; tax estimate cannot become a negative refund; fractional quantities retained | Nine shared fixture cases pass in both clients; original stored financial rows unchanged |
| Dashboard integrity | Removed stock-price-average fallback masquerading as MASI | Missing MASI stays unavailable; preserved index data unchanged |
| Managed hosting | Separate **private** repository contains only reviewed generic worker code; standard Linux eligibility test passed with the existing $0 cap | Manual workflows only; no recurring schedules or collection activation |
| Provider access | Local request and actual private GitHub cloud HTTP probe succeeded | Reachability only; completeness, normalization and app updates remain unverified |
| Private acquisition | Provider-configured worker, immutable gzip evidence, retry/readiness/idempotency checks, isolated SQLite backend and restricted PostgreSQL interface prepared | SQL007 tested locally only; **not installed live**, collector role/credential not provisioned |
| Account recovery | Both requested email-to-portfolio mappings recorded privately | Owner explicitly deferred implementation; no accounts linked/created for the real users |
| Signup email | Auth email enabled, signup enabled, email confirmation required, anonymous sign-in disabled | Custom SMTP and real inbox delivery **unknown/unverified**; owner answered “Not sure” |

## Live database privacy: confirmed evidence

`migrations/supabase/008_authenticated_market_access.sql` was applied with
`tools/private_database_access.py --apply`, after an isolated PostgreSQL test.
All 15 application-table row counts matched before and after. This changed
permissions and policy roles, not financial/market row values.

Fresh `tools/verify_database_privacy.py` checks passed:

- All 15 application REST tables reject the publishable key without a user session.
- No application/recovery relation grants anonymous reads.
- All four portfolio owner policies and RLS remain enabled.
- No public Storage buckets; anonymous Storage/Realtime row visibility is zero.
- Internal managed Realtime/extension schemas are not exposed through PostgREST.

Supabase-managed internal schemas retain their platform defaults. An internal
Realtime subscription table does not use RLS, but it is not an exposed REST
schema and contained no anonymously visible rows during verification. Do not
mistake a catalog table-level privilege count for actual application exposure,
and do not casually alter managed service internals.

The schema name `public` and public project URL/publishable key do not mean that
anonymous users can read the tables. Signed-in users can read market data; each
portfolio remains restricted to its own authenticated owner. Auth signup/login
endpoints remain available.

Fresh-install/repeat-import SQL002/004/005 and the market import privilege checks
were also tightened to authenticated-only market reads, preventing a normal
repeat import from reopening anonymous access. Market/supplemental verification
tools were adapted to the changed access contract; an authenticated user token
is needed for REST/PHP parity checks and is passed only in memory/private pipes.

## Client implementation details

- `core/backend.php` accepts/defaults only Supabase and reads the ignored public
  runtime config, never the migration admin/database credentials.
- `core/Appwrite.php` retains compatibility helper names for existing pages, but
  the retired transport permanently refuses requests. Reads delegate to Supabase;
  old direct document writes fail closed. Authentication and portfolio actions
  now use Supabase sessions and the atomic `record_trade` RPC.
- Old web login and portfolio mutation branches were removed. Existing company
  enrichment/admin writers that relied on direct document writes still need an
  authorized Supabase replacement; they are **not** fully migrated yet.
- `core/SupabaseMarket.php` now sends the user JWT alongside the publishable key.
- Flutter uses `lib/query.dart`; the Appwrite dependency was removed from
  `pubspec.yaml` and lock/plugin state refreshed. Legacy adapter sources are kept
  privately, not loaded by the active app. The old vendor tree is archival only.
- `core/portfolio_math.php` and `lib/portfolio_math.dart` share nine fixtures.
  Actual saved-record checks verified all 55 original rows and found one sale
  whose FIFO result is unresolved. Do not invent ordering or opening purchases.
  Historical holdings/cost/P&L snapshots remain separate and unchanged.
- Public-only config writers and deployment filtering prevent shipping obsolete
  credentials, private backups or SQL. Explicit uploads obey the same runtime
  allowlist. Required new runtime helpers/contracts are included even while
  untracked. These changes are tested, **not a completed production deployment**.
- The APK workflow now builds against Supabase, but the main worktree has not
  been committed/pushed. Never build Flutter `--release` locally.

## Tests and artifacts

- Flutter analysis: clean; default Flutter suite: **35 passing tests** (26 existing
  plus nine FIFO cases). This suite ran before the later live-test expectation
  update; no runtime Dart changes followed it.
- Actual mobile SDK integration: **passed after privacy change**, including
  anonymous denial, authenticated market pagination, login/refresh/restoration,
  fractional trades, retry behavior, owner isolation and logout. Temporary users
  were deleted and no signup email was sent.
- PHP live integration: passed login/refresh/logout, CSRF/cookie behavior,
  authenticated market reads, exactly-once trade retry, cross-owner isolation and
  concurrent oversell rejection. Temporary users deleted; no real-user changes.
- PHP market/Auth/session adapters and nine shared FIFO cases passed.
- Python config/deployment checks: four Flutter-config, three web-config,
  three deploy, five market-migration cases passed.
- Managed worker: **21 local unit tests pass**. Seven isolated PostgreSQL archive
  tests and one privacy-migration regression passed; all local SQL fixtures and
  role changes rolled back.
- Debug APK: `myinterpreter_app/build/app/outputs/flutter-apk/app-debug.apk`,
  **192,654,817 bytes**, SHA-256
  `2bf67538a8175d3a751f707533816ca2d01d2927ea667de000f9c81ce8a967a0`.
  Known secret/database-password literals were absent from decompressed entries.
  No device validation or release build/deployment was performed.

## Private automation and free allowance

The supplied billing screenshots show Pro with 3,000 included private Actions
minutes/month. The $1.27 gross usage was fully offset by included usage; no
payment was shown. Keep the existing $0 extra-spend budget. Billing APIs lack
Plan-read permission, so **exact remaining monthly minutes are unknown**.

Proposed recurring timeout plan, before other private repositories and overhead:

| Proposed job | Maximum monthly planning minutes |
| --- | ---: |
| Combined 15-minute quotes and hourly depth, 32 weekday runs × 23 days × 2 min | 1,472 |
| Daily valuation/maintenance, 23 × 4 min | 92 |
| Daily fundamentals batch, 23 × 6 min | 138 |
| Weekly dividends, up to 5 × 6 min | 30 |
| Scheduled plan | **1,732** |
| Manual testing reserve | **150** |
| Total plan | **1,882** |
| Pro headroom before other private usage/overhead | **1,118** |

This is a timeout planning calculation, not measured production runtime or a
billing guarantee. There were eight existing owned private repositories before
the new worker repository, all sharing the same allowance. Current manual
collection workflow has a six-minute cap and remains gated off; it is not the
proposed final recurring two-minute combined job. No artifacts/caches were added.
GitHub schedules are best-effort, not a real-time guarantee.

Actual cloud tests:

1. Secret-free one-minute standard Ubuntu eligibility job succeeded; recorded
   job duration two seconds. The red $0 budget banner did not block that run.
2. First source probe failed. The same urllib implementation also failed locally
   with HTTP403, while the existing collector's Requests client worked.
3. Reused Requests with pinned dependencies; local and cloud retests succeeded.
   Cloud response was 50,292 bytes with valid JSON, at
   `2026-10-27T16:17:03.689505+00:00`. This was a **reachability probe**; raw cloud
   response was not archived, no database access occurred, and no completeness
   or current-price certification was claimed.

All source endpoints/native recipes stay in ignored local config or encrypted
CI secrets, never in Git. GitHub currently has only the read-only source-probe
recipe; no Supabase admin/database/collector credential was uploaded. The main
public repository and unrelated worktree were not pushed.

## Exact remaining work, in order

1. Resume from the private evidence handoff. Check worktree/remote state first;
   preserve all unrelated WIP. Latest local worker hardening/tests are ahead of
   the published private package and need review before synchronization.
2. Finish provider recipe normalization and semantic checks. Local bulk response
   had 66 detailed stock rows, one index row, one status row and 81 ticker rows.
   Some source times are timezone-free and ticker rows have no individual time.
   Do not infer timezones, fabricate session dates, or label all 81 as fresh.
   Native request/field bindings must stay private.
3. Finish reusable fundamentals/dividend/order-book adapters, market-status
   evidence and batch manifests. Current worker is a raw evidence foundation,
   not a complete substitute for every old function or an active app data feed.
4. Implement the separate app current-price/history projections, ratio/dividend
   validation and bounded write interface. Never overwrite original recovered
   observations or quietly substitute prices. Restore admin enrichment writes
   through an authorized Supabase API rather than enabling old write helpers.
5. Implement daily valuation with owner privacy, actual closing-window freshness,
   stale/ambiguous-data skips and owner/day idempotency; workers must not receive
   broad personal-table or Auth access. Maintenance may not delete original
   recovery evidence, models or genuine ledgers.
6. Review/install SQL007 only after live read-only contents/ownership/capacity
   checks, then provision a dedicated narrow collector login. It is NOLOGIN in
   the draft and currently not installed live. Use project-bound verified TLS;
   never upload the admin database URI or Supabase secret key to Actions.
7. Measure storage growth and cloud runtimes. Last read-only database size was
   332,723,891 bytes. Draft archive guard is 350,000,000 bytes; this cannot support
   indefinite raw capture growth. Design a private archive/export/retention path
   before activating continuous depth collection. Do not silently delete data.
8. Verify SMTP settings and actual confirmation delivery. Owner is unsure;
   management access/SMTP credentials are not available in the current config.
   Keep confirmation enabled. Supabase built-in SMTP is restricted to team
   addresses and low limits; configure a suitable sender before claiming public
   signup works. Add/test password recovery and callback/deep-link behavior.
9. Recheck web/mobile end to end and prepare an explicitly reviewed deploy set.
   Do not publish the main worktree wholesale: it contains unrelated WIP and
   older unsanitized source evidence. Do not trigger release builds accidentally.
10. Finalize private schedule YAML and runtime/usage monitoring; activate only
    after source/capacity/permission/runtime checks and necessary authorization.
    No prediction/model schedule is part of this work.
11. **Deferred by owner:** implement both saved-portfolio email mappings from the
    ignored record. Users choose new passwords; require verified matching email
    ownership, never merely typed email or old guessed credentials. Do not start
    this task ahead of the current migration work.
12. **After current work is complete:** research professional navigation patterns
    and de-emphasize/move the rarely used owner-only Société/MAJ link. Preserve
    owner-only authorization. It has not been redesigned this continuation.

## Sources for service constraints

- [GitHub included usage](https://docs.github.com/en/billing/reference/product-usage-included)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [Supabase custom-role connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase SMTP requirements](https://supabase.com/docs/guides/auth/auth-smtp)

Original recovery data, genuine predictions/outcomes, frozen models and accepted
prediction-stage evidence were not modified in this continuation. Prediction
work remains deferred; its independent handoff is under the research directory.

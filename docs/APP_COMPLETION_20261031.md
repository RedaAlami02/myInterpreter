# Website, phone and automation checkpoint — October 31

Scope: finish the application migration and original jobs. Prediction-model work
is excluded. Upstream identities and credentials remain private.

## Verified hosted state

The owner approved the disabled SQL017–019 upgrade and two existing function
updates. It completed successfully; do not rerun the installer.

- SQL017 subject-specific archive completion, SQL018 minimal company context and
  SQL019 confirmed-email portfolio recovery are installed.
- Archive gateway v7, projection publisher v7; application publisher stays v8.
- All three endpoints return their exact disabled responses. Collection,
  enrichment context, application-row publication and recovery remain off.
- Every preexisting table fingerprint is unchanged. Existing functions and ACLs
  are unchanged except the reviewed archive-finalization guard.
- Anonymous exposed application relations: **0**. Auth accounts: **0**.
- Database at acceptance: **333,788,851 bytes**.
  After disabled binding registration: **333,838,003 bytes**. Fresh read-only
  verification confirms every other table hash and every function/ACL unchanged;
  private recovery tables are inaccessible to all application roles.
- Fresh private custom-format backup: **55,521,707 bytes**, SHA-256
  `bbb67253d2bd6b6dd97e1de6f2255097802dd747dead6933d67d3254b6bedffd`.
  Its table of contents and every archive stream were decoded successfully.
  An actual restoration drill was not performed. Auth, Storage objects, roles
  and platform configuration are outside this backup.
- Zero source requests, account creation, financial imports, secret changes or
  schedule activation during this upgrade.

Private evidence:
`private/app-completion-20261030/install-20261031T082658Z-f0562efc/`.
Earlier failed pre-commit attempts remain preserved. The final installer uses
verified TLS with the official database root certificate.

## Implemented and locally verified

- Website confirmation/recovery callbacks use one-use PKCE intents bound to
  email, flow and time. Password recovery has its own bounded session; ordinary
  login does not authorize reset. Redirect parameters match the Auth protocol.
- Both application clients call the zero-argument recovery RPC before private
  portfolio access. First recovery requires a confirmed email and signed
  password-authentication evidence. Original financial rows and timestamps are
  copied exactly with private provenance; occupied destinations fail closed.
- Both saved owners have 55 preserved original records in private staging.
  Both approved email bindings were registered disabled and verified through a
  fresh connection. Their identities and exact source pins stay private. No real
  account has yet claimed either portfolio; staging, bindings and claims are
  distinct states. Registration changed no Auth account or financial row.
- Fresh company context carries original dates separately from availability
  timestamps. Quotes/full display rows retain exact retry inputs and durable
  acceptance receipts. Enrichment uses the existing calculation/collector rules.
- Typed bounded bundles transport archive, quote, receipt and enrichment queues
  locally. The new runner checkpoint includes all four queues, an explicit empty
  state and a pinned completion manifest. Restore validates every channel before
  touching a fresh target. Nine additional tests include the real publication
  receipt/completion path; hosted checkpoint orchestration remains unfinished.
  Read [RUNNER_CHECKPOINTS.md](RUNNER_CHECKPOINTS.md) before wiring cloud state.
- Website deployment now includes the callback and reset pages even while they
  are untracked. Owner-only maintenance navigation is last, after dividends.

Completed verification: 278 managed Python, 34 deployment-tooling, 59 Deno,
82 Flutter, 58 isolated context SQL and 12 isolated recovery SQL cases passed.
Flutter analysis is clean. Focused PHP authentication/adapter/claim checks passed.
An additional three website publication-boundary tests and PHP lint passed after
the deployment manifest/navigation adjustment. Website deployment dry-run only.
These results are local tests, not live email, device or source acceptance.

Review package v3 manifest SHA-256:
`d07435edd36dbb1ef540685cf0e962e7607a74ddf503663f512edfd2ce9522fb`.
Installed nine-file delta manifest SHA-256:
`68cf86e3cc1a5f9cb83c9e956a6c72709ae8b69099636e851d14ced1918c8ccb`.
Preserve both immutable packages and earlier accepted evidence.

## Remaining acceptance and implementation

1. Both private owner bindings are registered disabled with all four dataset pins.
   Do not register the older preparation artifact lacking those pins or enable
   real recovery before the account/email acceptance gate is met. Registration
   receipt: `private/app-completion-20261030/portfolio-bindings-registered/`.
   Fresh safety proof: `private/app-completion-20261030/post-bindings-verification.json`.
2. Verify custom SMTP and redirect allowlists, real confirmation/reset/logout,
   then real phone/device behavior. Management Auth configuration returns 403;
   the owner has a pending SMTP-settings question. No fabricated acceptance.
3. Finish bounded cross-run queue persistence and update the private worker
   distribution. Current cloud workers predate these changes. A runner-local
   spool alone cannot survive disposal; local ZIP transport is not automation.
4. Complete new-listing persistence/profile updates, hosted dividend/fundamental
   acceptance, daily P&L integration and operational retention. SQL012 remains
   staged, not installed. Shadow prices must not silently become valuation inputs.
5. Review the website upload before cutover; no website upload, root Git push,
   APK release or recurring execution occurred in this checkpoint.

The former depth function ran every five minutes. The current opt-in managed
window allows hourly depth only; this is a known cadence difference, not parity.
The older 1,882-minute budget estimate assumed reduced depth cadence. Original
separate quote/depth jobs can consume almost the full included monthly compute
allowance before other jobs and shared account usage. Measure actual runtimes
and confirm remaining compute/artifact capacity before enabling recurrence.

Do not reconnect to the retired backend, repeat the consumed live quote trial,
enable controls/schedules, or call this production ready. Source-use authority
is already supplied; source identities remain private. Preserve unrelated dirty
worktree changes and all original recovery/model/ledger evidence.

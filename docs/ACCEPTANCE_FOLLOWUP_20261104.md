# Acceptance follow-up — November 4, 2026, evening

This supersedes earlier unresolved storage and first-tick-only notes. It does not
claim complete website/phone acceptance or a successful full market session.

## Deployed fixes and evidence

Worker release `73bf768e4a4da13b186dc30c1f649ac450348e13` includes the reviewed
collector repairs plus operational monitoring. Exact remote file readback passed.
The protected official-review commit pin matches this release. Collection and
review gates were restored and verified after each publication. No root worktree
commit or wholesale website upload was performed; unrelated work remains local.

- Preserved depth batches showed exactly 80-second runtimes and deadline errors,
  leaving instruments unattempted. The bounded sequential budget is now 120 seconds,
  with explicit attempted/failed/unattempted and stop-reason summaries. The outer
  combined collector bound is 300 seconds. The expected universe and completeness
  rules remain unchanged. Live improvement requires the next eligible session.
- Quote evidence contained 67 of 81 expected instruments, with no parser issues.
  Fourteen quotes were absent from the response. Display publication remains
  explicitly partial; missing quotes are not fabricated or made eligible.
- Official capture IDs used a concatenation hash incompatible with the archive
  gateway's canonical array hash. New captures now follow the gateway contract.
  An invalid old candidate is preserved byte-for-byte in quarantine; it is never
  rewritten into apparently valid historical evidence. Fresh acquisition and
  independent review are still required.
- The official archive outbox now lives inside the durable checkpoint. Safe
  collector failure codes are emitted instead of swallowing every exception.
- GitHub dispatch accepts both documented successful HTTP responses, 200 and 204.
  Previously a successful review dispatch could be reported as failed.
- The prior official-review pin still pointed to the original worker commit after
  schedule-only commits advanced the branch. Those intervening changes were
  verified, and the publisher was redeployed with the final exact reviewed pin.
  Future worker releases must update this pin after review, even for workflow-only
  changes; do not remove the commit verification.
- Timer deduplication now compares five-minute slots with an additional one-minute
  cooldown. Comparing exactly five elapsed minutes with GitHub's delayed creation
  timestamp had suppressed the next valid cron tick. Advisory locking, active-run
  checks, the daily cap and outside-session gates remain enforced.

The independent timer had made 21 HTTP attempts during the afternoon; repeated
cron executions and runner starts were observed. Later collection failures are
separate from trigger reliability. The corrected cadence needs a new genuine
session; GitHub's native schedule remains replaced, not repaired.

## Storage cleanup completed

The owner explicitly approved removing exactly 110,668 non-personal migration
staging rows. Before production cleanup:

1. The complete private backup was hash-verified.
2. All 110,723 documents and 16 metadata records were restored successfully into
   an isolated, network-disabled PostgreSQL container using the staging schema.
3. The atomic cleanup was rehearsed and retained all 55 personal records exactly.
4. Live backup contents and dataset metadata matched under locks. Dependency
   review found only the saved-portfolio claim function, with no dependent views,
   inbound foreign keys or user triggers.

The production transaction retained table identity, RLS, privileges, all 55
personal records, all 16 dataset metadata records and the claim function unchanged.
Application tables were not modified. Physical database usage fell from
336,090,803 to 221,796,019 bytes. A later monitoring reading was 221,853,363 bytes,
leaving 128,146,637 bytes below the verified live 350,000,000-byte guard.

The removed staging content remains in the owner-only backup, not online staging.
Original dataset row counts describe the preserved import; full-staging verification
or re-import tools must account for this intentional archival cleanup. The backup
and exact cleanup/restore receipts live under
`~/.local/share/myinterpreter/acceptance-20261104/`. The PostgreSQL rehearsal was
removed after verification. No guard was increased.

## Monitoring

The owner selected GitHub Actions failure-email notifications. A screenshot
confirms receipt of a collector-failure email. The separate health workflow checks
storage headroom, quote/depth freshness and completeness, official-close batches,
valuation receipt existence for holdings, and the most recent collection result.
It runs at 12:07 and 20:07 Casablanca time on weekdays through the independent
private timer. No user identities, source identities or prices enter its snapshots.

Manual acceptance run `41918849715` reached the final release and correctly failed
with `OFFICIAL_CLOSE_UNVERIFIED` and `COLLECTION_RUN_FAILED`; storage passed.
HTTP dispatch returned 202 without timeout. Receipt of this new health email and
its first automatic cron tick remain unconfirmed. The screenshot of the older
collector notification does not establish either of those facts.

This is not an independent external uptime monitor: an outage of the same database,
GitHub service or dispatch credential can prevent notifications. Token renewal is
required. Holiday/closed-session ambiguity is reported as unverified rather than
inventing an official batch. Existence of receipts alone does not prove every
portfolio is eligible or completely valued.

## Website, authentication and mobile

- Fresh FTPS readback matched all 24 selected website files to local bytes; all ten
  earlier fix receipts still match. No website runtime code changed in this pass.
- Six deployed Edge Functions matched local source exactly. Five relevant SQL
  function definitions were hashed into the private release record.
- Public browser checks at 390 and 1366 pixels passed for the six selected paths
  with no horizontal overflow or visible PHP errors. Protected portfolio/reset
  pages redirected to login. These redirects are not signed-in page acceptance.
- Unauthenticated trade and admin submissions redirected to login. The storing
  helper is a function library, not a trade endpoint; an empty 200 from that file
  is not evidence of an accepted write.
- The owner-supplied test address had no existing account. A real website signup
  created an unconfirmed account and recorded confirmation dispatch time. The
  expected notice appeared; no admin confirmation bypass was used. Actual inbox
  delivery, emailed PKCE completion and password reset are still pending.
- The Gmail connector was installed but unusable because its tool requested a
  connection identifier it did not supply. No inbox read or direct Gmail send
  occurred. The owner is checking the relevant emails manually.
- Signed-in buy/sell/refresh and live admin-edit acceptance remain pending.
- Compatible-phone testing was explicitly deferred. The existing parity APK hash
  is verified as `2f0bf2f7baa6bb340f5f8174fa6a525ef12cd75de6bb22efd90c50e90e7f6ced`,
  from build `41749862195`, commit `07a85071cb9a47f5f44a65b3ca667e448bc355eb`.
  No mobile files changed and no new APK build was needed. Installed version,
  device deep links, offline behavior and cross-device parity are unverified.

## Validation and release record

370 local worker tests; 15 timer Deno tests; four health-dispatch Deno tests;
23 PHP suites with one legacy live-backend suite explicitly skipped; six portfolio
display tests; five distribution checks; five deployment-tool tests passed.
Hosted synthetic verification `41917607814` passed for the collector-fix commit.
Final monitoring-release hosted verification is tracked separately.

The deployment CLI now handles `--help` safely, rejects unknown flags before loading
credentials, and makes `--dry-run` independent of credentials/network access. This
fix is local tooling only and was not uploaded to the web host.

The combined private record `release-record.json` binds deployed website hashes,
worker commit, Edge source hashes, SQL definition hashes and the candidate APK.
It explicitly sets combined release acceptance and installed-APK verification false.

Next acceptance requires a genuine new session, successful independent official
review and eligible valuations, the two real email flows, a compatible phone, and
signed-in website/admin checks. Do not simulate production timestamps or fabricate
prices to mark these items complete.

## Later signed-in acceptance and final hosted verification

Hosted verification `41919374765` passed on final release
`73bf768e4a4da13b186dc30c1f649ac450348e13`.

The test account became confirmed at 21:48 UTC. The agent did not force-confirm
it; the completion path is not established. Normal password login subsequently
passed. Live website checks on this initially empty account verified:

- Buy two units at 100; replaying the same request created only one trade.
- Sell one unit at 110; the remaining position was one unit with cost 100.
- Overselling and zero-quantity submissions were rejected without additional rows.
- Invalid CSRF returned 403; the non-admin account received 403 on the admin page.
- Displayed FIFO gross profit was 10.00 and net 6.90 under the configured 10% tax
  and 1% buy/sell fee assumptions. This verifies arithmetic, not statutory tax rates.
- The prior-day reference price was dated and explicitly described as non-live.
  Unverified official-close valuation remained unavailable; no valuation was written.
- Portfolio, Transactions and P&L tabs had no page overflow at 320, 390 and 1366px.

All five exact test trade/holding/idempotency records were backed up privately and
removed transactionally. The account was verified empty again; other accounts were
untouched. Successful admin editing still requires an authorized admin session.

A real password-reset request was then submitted through the website. The owner
provided an image of the resulting Supabase reset email, establishing reset-email
inbox delivery. The reset link was not consumed by the agent and no password was
changed. Completion in the originating browser remains pending. The helper
`tools/save_acceptance_link.py` accepts a recovery link via hidden terminal input
and saves it owner-only; it never sends a request or prints the link.

The new health-workflow email has not been confirmed delivered. The older
collector-failure email is confirmed by the owner's earlier image. Auth-log and
GitHub primary-email API access were denied, so sender-side email delivery cannot
be inferred from those APIs. An approval-review usage-limit failure temporarily
blocked the final read-only hosted check; a later approved retry succeeded.

## Password reset completed through the real emailed link

The owner saved the received reset link privately. The original isolated browser
consumed it and reached `auth_reset.php` through the emailed PKCE callback. The
form accepted a newly generated password and returned to login with the explicit
reset-success marker. The old password was rejected with the login error notice;
the new password signed in successfully. A normal signed-in session could not
open the password-reset form without a recovery intent. The test session was
logged out afterward.

The current test password is retained only in the owner-only acceptance credential
file. The consumed email link and redundant temporary password file were removed.
The private combined release record now marks password-reset completion verified.
Signup email-confirmation completion remains a separate, partially observed flow;
this reset test does not retroactively establish how signup was confirmed.

## Compatible device connected — November 9

A Samsung SM-A325F running Android API33 was connected. Its older installed APK
was updated in place, retaining application data. The installed APK SHA256 now
matches the recorded parity release exactly. The existing authenticated session
was preserved. Portfolio navigation loaded without an observed load error, the
custom callback resolved to the app, and background/resume was exercised. Recent
app-process logs showed no fatal exception, Flutter unhandled exception or
RenderFlex overflow. These checks do not establish full device acceptance.

Switching the existing signed-in session to the empty acceptance account was
presented to the owner because restoring their original session requires their
login. Login/trade-refresh/offline/expired-session and actual callback completion
remain pending. Detailed device evidence is kept in the owner-only private vault.

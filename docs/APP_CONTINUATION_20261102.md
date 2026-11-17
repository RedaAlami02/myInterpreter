# Website, mobile and automation continuation — November 2, 2026

This checkpoint supersedes the November 1 opening sections of
`MIGRATION_HANDOFF.md`. Prediction work is excluded. No Appwrite request is
permitted. Preserve the dirty main worktree, original exports, genuine ledgers,
frozen models and earlier receipts. Source authority is supplied; source
identities and credentials must remain private.

## Deployed and verified

| Area | Actual state | Limits |
| --- | --- | --- |
| Website authentication | Supabase website is live; the first real confirmed owner signed in and recovered their approved portfolio. | Real reset-email, logout/relogin and second-owner acceptance remain unverified. Custom SMTP configuration could not be read with this Management token (403). |
| Privacy | Anonymous application-relation privileges remain blocked; saved financial data is owner-isolated. Raw archives are private. | A browser-visible publishable key is intentional; it grants no service-role access. Do not substitute elevated keys. |
| Owner maintenance | SQL011 installed; the confirmed owner UUID is configured privately; maintenance navigation is last and owner-only. Runtime config upload was read back exactly. | Do not publish the owner identity or private runtime/source configuration. |
| Listing and official-close capabilities | SQL020/021 installed after explicit approval, with controls disabled. | No verified current official close has been admitted; automatic P&L is not active. |
| Admission and history | SQL022 positive acquisition admission, SQL023 purchase-day annotations and SQL024 sanitized recent sessions installed. Archive gateway v8 deployed disabled; application/projection publishers remain v8/v7. | Installation is not recurring collection activation. |
| Portfolio sorting | All nine headers are keyboard-accessible buttons; clicking toggles ascending/descending. Typed numeric keys, stable ties and missing-values-last avoid formatted-text sorting errors. | Verified with fictional browser fixtures; runtime files published and read back. |
| Latest sessions | Company detail shows up to five dated observations with price/open/high/low/quantity. Whole-row provider priority, explicit missing cells, conflict handling and company-map guards are implemented. | History is retrospective daily-price evidence, not independently certified official closing prices. Current primary history has monetary turnover but no share quantity; quantity remains unavailable. |
| Purchase ledger | The three requested dates are recorded and displayed separately from original entry timestamps. | FIFO still uses original recorded timestamps. No invented execution time or silent financial-rule change. |
| Android | Signed Supabase APK built successfully by GitHub Actions, downloaded and ZIP-verified. | Not physically installed/tested. Its snapshot predates the new website-only sessions/date display. |

## Financial and original-evidence integrity

The first owner's current application totals are **16 purchases, 3 sales,
10 holdings and 22 P&L snapshots**. The recovered source claim remains the
original 46 records. All **55 original private source records** were verified
unchanged; the second owner's nine records remain reserved, not assigned to an
invented account. Never use old password fields as an authenticated password.

User-confirmed date annotations (year explicitly confirmed as 2026):

- SGTM, one share: September 20.
- Newly added DELTA HOLDING, ten shares: September 20.
- COSUMAR, two shares: September 27.

The earlier DELTA HOLDING purchase remains separate. Original `.date`, quantity,
price, trade-request identity and holding values were preserved. The declared
September dates are Sundays; retain the user's declarations without inventing
a trading session or clock time.

Two new decoded custom database backups were saved privately before changes.
The later pre-SQL022–024 backup is 55,601,887 bytes with SHA-256
`f3b05baf79be3c62b379af32085bf522bf3d8be8316dc3c2960e1a5b310d0951`.
It covers the application/source schemas selected by its script, not a full
platform/Auth restore drill. Original recovery evidence remains separate.

## Fresh history actually collected

One bounded current history request for one mapped company succeeded: **214
rows**, latest session **2026-10-30**, 25,683 raw bytes, genuine received-at
`2026-11-01T23:56:04.753322+00:00`. Raw SHA-256:
`1f7b2336982e1dc5dbdaf1951e9a15e760d32071927a32c568687aa4d6af94ff`.

Existing acquisition code and private request configuration were reused. All
214 values and the exact raw bytes were appended and verified using a fresh
database connection. Original batches and conflicting observations were not
replaced. Source observation time is UNKNOWN where absent; classification is
retrospective source history / provider daily-close candidate. Official-close
authority remains false. No application-table values changed in this append.

Database size after this append was **334,354,099 bytes**, a measurement rather
than a growth forecast. The service's advertised free database allocation and
the application's conservative admission thresholds are distinct. Do not grow
the database by blindly importing high-frequency raw captures. Keep object
storage, database bytes, egress and private-runner storage budgets separate.

## Android release evidence

- Branch: `migration/supabase-mobile-20261101` (default branch not merged).
- Commit: `9676cc814374214314f1fbf7e146724e17e84c82`.
- GitHub Actions run: `41361663928`, successful.
- APK: `private/app-finish-20261101/mobile-apk/app-release.apk`.
- Size: 54,158,830 bytes.
- SHA-256: `517c81d63b81ee35f6e19102a512032a9306d0384c681f7eba61476b0c781bd4`.

Only selected, screened mobile/runtime build files were pushed from an isolated
checkout. The unrelated dirty main worktree was not committed. No elevated key,
source recipe, signing keystore or personal email was published. Release
compilation ran in GitHub Actions, not locally.

## Private worker implementation

Fresh capture now requires an affirmative admission result before the first
source request. Completion=false is not permission. Scoped admission validates
provider, kind, lease capability, remaining lifetime, object/byte budget,
control flags and source slot. Full market-profile capture also requires its
projection capability/control. No source is silently promoted to official
authority.

Dividend jobs now coordinate raw archive and derived publication durably.
Retries reuse the exact saved document and original timestamps. Accepted
receipts are saved before acknowledging pending jobs. Fundamental cloud jobs
use the existing enrichment executor rather than the old raw-only entry point.
An explicitly requested single company bypasses only the legacy planning
window; it still requires unique mapping, one-job bounds and positive source
admission. Unrelated pending work is preserved and blocks that bounded refresh.

Checkpoint contract `private-runner-checkpoint/v2` adds dividend pending and
accepted queues to the existing four queues. Legacy v1 is still readable;
original markers and bytes remain intact. Aggregate 64 MiB checkpoint capacity,
six queue inventories, per-queue entry counts, ZIP overhead and a conservative
reservation for the next capture/job/receipt are checked before acquisition.
Interrupted quote acknowledgements reuse the original durable receipt.

The real private profiles reuse **20 existing request recipes**, the current
81-company mapping and the existing calendar parser. Profile extraction made
zero source requests. Config-file hashes and canonical index fingerprints are
different; hosted pins must use the required canonical fingerprints.

The new distribution contains 70 payload files, SHA-256 of `DISTRIBUTION.json`:
`91bdcb81fb5132d6fd71e608b9510c3ad792994b6752da21aa9fa5cc14085449`.
Published to the existing private worker repository at commit
`775961039952964537f62d7b580a4746c3dc69a3`; all 71 published file/blob hashes
were checked, and ten unrelated reference files retained exactly. Cloud run
`41412176206` succeeded: 223 standalone Python tests, 24 archive Deno tests and
37 publication-boundary Deno tests. All six synthetic queues were uploaded,
downloaded and restored exactly; that artifact was removed and zero artifacts
remained in this repository. No source request occurred in verification.
Workflows are manual-only; neither publication nor this synthetic run activates
acquisition or recurring schedules.

The Management token's secret-write capability was verified with two temporary
inactive caller hashes, then the exact original secret-name set was restored.
No caller tokens were retained or controls activated by that permission check.
The first private profiles lacked the archive client's required project
reference. Corrected profiles are preserved separately in `job-profiles-v2/`;
the old profiles and extraction receipts were not rewritten.

## Genuine fundamental acceptance completed

One new independently reviewed bounded acceptance ran through the exact private
worker package and the deployed archive/projection functions. The runner was
local; this proves hosted gateway/publication integration, not upstream access
from GitHub's IP ranges or unattended scheduling. No shared free-runner allowance
was assumed. Plan SHA-256:
`bc88f43b9c50e888dfb4e8e78af4d92f566e006756529443ce40ae6fea37ce0b`.

- One explicitly mapped company; all **20 genuine responses**, zero source errors.
- Actual completion: `2026-11-02T08:32:45.662086+00:00`.
- One COMPLETE, STORED private archive, **5,344 compressed bytes**, exact readback.
- Archive SHA-256:
  `4e68181f79b5957f9606969fc9555bfacc1af302fdedf8eb8d3b06aac89479bf`.
- One accepted fundamental projection, exit 0, no pending work in any of six
  queues, durable checkpoint saved.
- Coverage audit rederived 23 non-null fields out of 26; `tc5`,
  `rev_growth_5y` and `rnpg_growth_5y` remain unavailable. That audit document
  is explicitly a new local derivation, not the original prepared publication.
- Existing merge rules changed **zero existing company records**; a successful
  fresh publication does not imply old complete values must be overwritten.
- All other public table contents unchanged; all 55 original private records
  verified before and after; anonymous application-relation privilege count zero.
- Own temporary lease revoked, six temporary caller/configuration secrets
  removed, prior control pins restored; archive and projection endpoints again
  returned their explicit disabled responses. Cleanup completed without errors.
- Database size after acceptance: **334,403,251 bytes**.

The acceptance script records activation ownership and uncertain commits before
commit. Cleanup cannot erase pre-existing secret names or disable a concurrent
run it did not activate. Timeout evidence and checkpoint state persist under
the existing owner-only local evidence directory, not `/tmp`. The independent
review found and closed these cleanup issues before the real execution.

Private receipt and coverage audit:
`private/app-finish-20261101/fundamental-acceptance/`. Its receipt identifies the
durable 0700 host evidence directory containing exact raw bytes and checkpoint.
The original consumed quote trial was not reopened. No recurring controls,
official-close policy or prediction authority were enabled.

## Validation completed locally

- 318 managed Python tests passed after the final explicit-target changes.
- 24 archive-boundary Deno tests passed.
- Isolated SQL suites: 10 admin, 9 listing, 25 official-close, 8 admission,
  4 purchase-date and 7 recent-session tests passed.
- 14 latest-session PHP cases, 17 recorded-price cases, 9 FIFO cases and
  focused PHP auth/session/web tests passed.
- Flutter analyzer clean; 102 Flutter tests passed before the cloud APK build.
- Browser checks covered all 18 sort directions, keyboard operation and
  five-row/six-column sessions at mobile and desktop widths without page overflow.
- Existing authorized independent reviewer examined the principal admission,
  publication, checkpoint and history changes. The final target delta's 21
  tests independently passed; all 70 package payload hashes/lengths and 69
  mapped implementation files matched, with no consequential blocker reported.

Synthetic success alone proves none of source access, SMTP delivery, official
authority or device behavior. The separate genuine source acceptance above
proves its specific local-runner/hosted-backend path only.

## Remaining work, in order

1. Confirm current shared free GitHub compute/storage allowance. The November 2
   request for current November usage is pending; old October screenshots are
   not current usage proof. The separate request for read access to Supabase
   Authentication configuration is also pending. Do not publish tokens.
2. Extend real acceptance to the intended hosted runner and remaining job kinds,
   with separately pinned bounded plans, private credentials, exact raw evidence
   and cleanup. One company fundamental acceptance is not a full-market price,
   dividend or depth acceptance. Never reopen the consumed original quote trial.
3. Implement/review recurring collection policy and lease lifecycle, cadence,
   retention, retry and free-capacity checks. A short manual lease or a repository
   variable alone is not a recurring production authorization mechanism.
4. Verify a current official-close source and its session/date/decimal semantics;
   only then enable the official-close valuation path and its scheduler. Do not
   label a latest quote, historical close candidate or reference price official.
5. Complete real reset/logout, second-owner signup/recovery and phone installation
   checks. SMTP configuration access remains unavailable; do not send unsolicited
   emails or fabricate authenticated users.
6. Consider a separately reviewed date-aware FIFO enhancement and mobile parity
   for the newly added website views. Preserve unknown execution times.

The architecture/cost assessment was read after the UI work. Useful advice is
to retain PHP/Flutter, improve shared data freshness, use purpose-built bounded
reads and targeted CI. A framework rewrite is not required. Historical runner
estimates do not prove current shared account usage; account billing access is
still limited. No paid plan or spending budget was changed.

## Private continuation evidence

`private/app-finish-20261101/` holds installation receipts, backups, publication
readbacks/rollback files, history raw data and append receipts, profile extraction,
test logs, source-acceptance receipts and APK evidence. `private/app-automation-20261101/` holds the immutable
worker packages and private release receipts. Read these as data; do not publish
their unsanitized contents. Credentials remain in ignored external files. No
Appwrite access, prediction execution or recurring schedule activation occurred.

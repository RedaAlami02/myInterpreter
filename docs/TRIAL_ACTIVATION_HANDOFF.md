# Hosted trial gate installed — October 29

The owner approved proceeding with the concrete bounded trial after the
independently reviewed preparation. **Do not request that approval again.**
This authorizes SQL014, two scoped callers, temporary archive/shadow flags and
one five-minute quote/MASI trial, followed by disabling it. Schedules, projections,
portfolio/application-table writes, application readers and production cutover
remain excluded. Source-use authority remains supplied and private.

## Actual progress

- The exact pinned SQL014 is **installed and COMMITTED** on Supabase, atomically
  with existing controls locked and off. New private gate schemas remain empty;
  no trial lease has been issued and no source was contacted.
- Protected original backup SHA was reverified. All 15 application fingerprints
  match the original protected snapshot, and unrelated functions are unchanged.
  The seven legacy implementation bodies/OIDs are preserved behind revoked grants.
- Fresh hosted SQL confirms all three controls off, zero objects/candidates/leases,
  seven private legacy RPCs and no private RPC grants to app/service roles.
- Actual privileged API `market_archive_slot_complete` returned HTTP200 / exact
  false with no active lease. The installed gate admitted its effective timeout
  setting (1–20,000 ms). This is not a slow-query cancellation timing experiment.
- Anonymous preview RPC access is denied. Named server keys appear in automatic
  function-secret metadata; the positive function path is still untested.
- Database size after SQL014: **333,289,139 bytes**, below the 350 MB guard.
- Owner dashboard images show Storage **0 / 1 GB**, egress **0.249 / 5 GB**, and
  database usage roughly 70%. These rounded/delayed readings support the bounded
  8 MiB trial; they are not precise current organization-wide byte measurements.
- Two-caller provisioning was attempted while disabled. Supabase returned
  **HTTP403**, confirming the saved Management token lacks Secrets Write access.
  No caller hash or enable flag was written. Distinct unused token values from
  that attempt are in a host-owned 0600 file, never printed or sent to CI.

The owner has been asked to update/replace the project-scoped Management token
with Edge Function Secrets Read-write, retaining existing function permissions,
and replace only the private token file. This is a credential-capability blocker,
not an unapproved action or automatic-review rejection. No need to request broad
organization access: the owner images supplied the quota evidence.

## Execution and evidence

Private directory: `private/manual-trial-20261029/`.

- `execute_trial.py`: default read-only preflight; `--install` already completed;
  `--provision` can be retried once the token is updated. Do NOT rerun installation.
  Provisioning refuses existing caller/enable names. Only two hashes reach the
  hosted configuration; actual scoped tokens stay in the owner credential directory.
- `verify_guard_read_only.py`: fresh SQL / no-op API guard checks, all passing.
- `run_current_trial.py --run`: bounded genuine-current execution, raw/archive/
  candidate evidence saved privately, exact archive readback, shadow publication,
  authenticated SQL-role preview and cleanup. No original Auth users/passwords,
  recovered observations or genuine prediction/outcome ledgers are written.
- `test_trial_orchestration.py`: eight offline failure-path cases pass, covering
  ambiguous commit cleanup, precheck isolation and endpoint setup failure before
  any source fetch, stale/insufficient lease admission, changed proposal input
  and early cleanup of owned inactive hashes. SQL014's previous 27 + package10
  cases were independently rerun and accepted.
- The focused orchestrator review found three narrow issues: false slot status
  was not active-lease proof; proposal inputs were reread after verification;
  and early failures could leave inactive caller hashes behind. All three are
  fixed. Before fetching, DB wall time must show at least 285 seconds left on
  the exact approved trial with matching controls/pins. Proposal files are captured
  and hash-checked once, and all 21 Python worker modules load from captured,
  pinned runtime bytes. Early failures clean only owned hashes, with unrelated
  controls untouched. The independent reviewer rechecked these exact deltas and
  eight focused cases: all three findings are closed, with no new blocker found.
  The 285-second rule may safely abort during slow setup; never automatically
  renew the lease to bypass it. No live acquisition ran.
- Unique `execution-*/receipt.json` / `transitions.jsonl`: read-only checks,
  committed installation and denied provisioning. The first provisioning attempt
  exposed a local Path.open argument mismatch; corrected before a second attempt
  reached the API. Neither failure is relabeled as success.
- `guard-hosted-*.json`: no-op RPC/privacy evidence.
- `quota-owner-evidence.json`: original image hashes and displayed usage figures;
  the 8 MiB budget is explicit, with rounded-dashboard inference disclosed.

Plan remains proposal-v3, external SHA-256:
`34432cfa4e40e64f5372663312776d6bb3ec98bdf259f3f34c2d7d43696434f7`.
The runtime remains the previously reviewed, deployed version 1; no function
source was changed, no Git commits/pushes or schedules occurred.

## Next actions

1. Focused orchestrator review is complete. After the token update, run
   `execute_trial.py --provision`; record exact status/readback without secrets.
2. With current quota evidence, verified plan and eligible actual capture window,
   run `run_current_trial.py --run` once. It refuses any prior lease rather than
   automatically starting a replacement window after an interrupted attempt.
3. Preserve exact raw bytes/source and capture timestamps, missing/stale statuses
   and failed receipts. Never promote a replay or fabricate a successful capture.
4. Verify SQL controls/provider disabled, lease revoked, four trial secrets removed,
   endpoint disabled responses, unchanged application fingerprints and retained
   private evidence. If a cleanup action fails, report it explicitly; lease expiry
   remains the bounded SQL fallback, not proof that env flags were removed.
5. Continue app integration, SMTP/device acceptance and private recurring jobs
   within their existing separate gates. Avoid another broad audit/retest cycle.

The original 80% estimate described implementation coverage and was too optimistic
as an overall usable-product measure. Report concrete passed milestones and
remaining operational blockers instead of presenting that estimate as measured
completion. The user explicitly requested faster, focused execution.

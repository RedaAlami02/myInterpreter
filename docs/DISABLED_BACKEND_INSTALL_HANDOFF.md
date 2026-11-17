# Disabled backend installation — October 29

**Newer local continuation:** [MANUAL_TRIAL_HANDOFF.md](MANUAL_TRIAL_HANDOFF.md)
records bounded manual-trial gates, tests and the private proposal. The hosted
state below remains unchanged; no new controls, secrets or schedules were enabled.

**The approved first installation is complete on Supabase.** The private archive
bucket, SQL009/010/013 and the three functions are installed. Every enable switch
is off/absent; no collection or schedules run. The owner authorized this narrow
scope by continuing after its concrete proposal and supplied the scoped Management
token privately. Do not request that installation permission again.

Approximate website/mobile/backend progress is **80% complete / 20% remaining**,
excluding prediction work. This is an engineering estimate, not a data-recovery
percentage or a production-readiness claim.

## Live state now verified

| Component | Verified state |
| --- | --- |
| Private archive bucket | Private, 8,388,608-byte object limit, zero objects after probe cleanup |
| SQL009 archive | Installed; control disabled; providers, objects and slots empty |
| SQL010 shadow feed | Installed; control disabled; latest candidates empty; pins unseeded |
| Revised SQL013 projections | Installed; control disabled; acceptance heads empty; pins unseeded |
| Archive function | Deployed version 1; returns exact HTTP503 ARCHIVE_DISABLED |
| App publisher function | Deployed version 1; returns exact HTTP503 PUBLISHER_DISABLED |
| Projection publisher function | Deployed version 1; returns exact HTTP503 PUBLISHER_DISABLED |
| Deployed source | All **nine runtime files byte-identical** to the independently reviewed revision-2 bundle |
| Enable variables / scoped caller tokens | All three enable-variable names absent; no new function secrets or tokens provisioned |
| SQL011/SQL012 | Deliberately absent; owner maintenance/valuation remain a later phase |
| Native profiles, provider/pin/admin rows | Not uploaded or seeded |
| Website/APK, accounts, schedules, prediction execution | Unchanged by this installation |

Platform metadata labels deployed functions ACTIVE because their endpoints exist.
Their application handlers explicitly reject calls in disabled mode. No live
market acquisition or publication trial has been performed.

## Preservation, backup and privacy

Before any hosted mutation, a consistent read-only application/recovery snapshot
was exported. `pg_dump` used that snapshot and read-only connection options; its
password stayed in child environment memory and out of command arguments/log output.

- Protected backup: **55,405,184 bytes**, directory 0700 and archive 0600 outside
  the shared workspace. Exact location and SHA-256 are in the private receipts.
- Backup schemas: public application data, private portfolio implementation,
  migration staging and both recovery/history archives (five schemas).
- SHA-256 was checked twice, the TOC was readable, and every compressed data block
  decoded successfully to `/dev/null`. **No restoration drill was performed.**
- Auth, Storage, database roles and platform configuration are outside that backup;
  this is not a complete project-recovery backup. Original Auth users were not changed.
- All **15 existing application table fingerprints**, original public function
  definitions and grants match the pre-install snapshot, including a fresh
  post-install read-only comparison.
- Fresh valid-key API checks deny anonymous access to all 15 application relations.
  Portfolio ownership policies/RLS remain intact; no public bucket or anonymously
  visible managed rows were found.

Bucket visibility was tested with one unique synthetic object, explicitly unrelated
to market data. Service readback matched its exact bytes; anonymous private/public
HTTP reads returned no object body, and the authenticated SQL role could not see
its catalog row. The probe was deleted and service/catalog cleanup verified.
A real signed-in user's Storage HTTP request was **not** tested; that remains a
later acceptance check. No temporary user or signup/reset email was created.

Final measured database size: **333,182,643 bytes**. Headroom before the existing
350 MB safety guard is **16,817,357 bytes**. Private object storage remains empty.
The installation did not raise guards, change billing or establish organization-wide
quota/Actions/artifact headroom. All **145 sampled hosted/local timezone
calculations still agree**.

## Review, transactions and hosted checks

The unchanged deployed runtime comes from the reviewed 41-file revision-2 bundle:

`76425b6d9752926a913cff39c4065905782d0de6a35c3f662699f9eb1bfb4330`

Previous-checkpoint tests remain **347 passing cases plus two integration checks**;
the runtime files did not change and those suites were not needlessly rerun here.
The new orchestration scripts were syntax-checked, independently reviewed and
exercised by the actual installation/hosted verification described here. The
reviewer also checked receipt transitions and all nine source hashes against the
pinned files. That last review was local evidence review, not independent live access.

The selected migration bytes were captured immediately after pin verification and
executed from memory in one transaction. Unique run directories, fsynced transition
journals and atomic receipts preserve every attempt. Commit status was recorded
UNKNOWN before commit and COMMITTED only after acknowledgement. Disabled controls,
empty tables, original data/functions and capacity were checked before commit.
No existing function was overwritten.

An initial hosted source-readback assumption was wrong: the default download is
ESZIP2.3, not ZIP. Verification stopped after the first function, leaving it disabled.
The official CLI uses `Accept: multipart/form-data` and prefers the
`deno2_entrypoint_path` metadata field. The verifier was corrected to follow that
protocol, compare the original file bytes and reject extra/ambiguous sources.
It then verified the first existing version without reposting it, and created only
the two missing functions. Both the initial failure and successful reconciliation
are preserved. No failed verification was relabeled as success.

Protocol references: [Supabase Management API](https://supabase.com/docs/reference/api/introduction),
[function deployment](https://supabase.com/docs/reference/api/v1-deploy-a-function),
and the [official CLI download implementation](https://github.com/supabase/cli/blob/develop/apps/cli/src/shared/functions/download.ts).

## Private evidence and credentials

Private checkpoint: `private/disabled-install-20261029/`.

- `run-20261029T101116Z-9996661b/receipt.json` and `transitions.jsonl`: backup,
  private bucket and committed disabled SQL installation.
- `functions-20261029T101630Z-3b62d4f9/`: first source-format failure, preserved.
- `functions-20261029T102439Z-1f6affec/`: final three-function source/disabled checks.
- `final-preservation-verification.json`, `privacy-final.private.json`,
  `readiness-final.private.json`, `backup-stream-verification.json`: final evidence.
- `bucket-probe-*.json`: exact present-object visibility and cleanup checks.
- `CHECKPOINT.json`, `HANDOFF.md`: consolidated final state and continuation steps.

Credentials and native source identities were not committed or published. The
Management token remains in the owner-only host credential file, with only
project-scoped Edge Functions read/write and Edge Function Secrets read requested.
It was not sent to CI or the function endpoints. Runtime checks used a separate
publishable-key-only HTTP client. Existing project credentials remain in their
original secure configuration; do not put them in shared docs or command arguments.

## Exact remaining work

1. Prepare the controlled hosted acceptance package. Source-use authority is
   already supplied, but enabling controls, provisioning caller token hashes and
   seeding private pins are **outside the completed disabled-only authorization**.
   A concrete manual-trial scope and necessary secret-write permission come next.
2. Complete organization Storage/Actions/artifact headroom and durable cross-run
   outbox provisioning before recurring jobs. Update/review the private worker
   publication: the newest local adapters/fixes are not all in the older private
   GitHub release. No main/public repository blanket push.
3. Verify actual hosted archive reserve/upload/readback, retries, quotas, expiry,
   interruptions, current-session coverage and timing. Positive privileged
   function paths and automatic named-server-key availability remain untested.
4. Deliberately integrate the accepted shadow quote preview into web/mobile.
   Preview data does not update legacy latest_prices, become an official close,
   or grant portfolio/model eligibility. Automatic valuation needs its own
   reviewed current-price path/contract.
5. Handle SQL011/012 as a separately authorized owner-maintenance phase. SQL012
   has no global off switch. Apply only the missing scripts; never rerun the
   full five-script batch over the installed subset.
6. Finish SMTP delivery, hosted auth redirects and Android device acceptance,
   then reviewed website/APK cutover. Mobile email links remain opt-in; no new
   APK was built and no real inbox delivery is claimed.
7. Keep both original portfolio assignments deferred until verified matching
   email ownership/new passwords are available. Preserve the later owner-only
   navigation request. Prediction work, frozen models and genuine ledgers remain
   outside this app-first continuation.

The full readiness tool still reports STAGED_SERVICES_NOT_FULLY_INSTALLED because
market_admin and the three SQL011/012 RPCs are intentionally absent. This is an
expected full-project readiness result, not a failed first-phase installation.
No production-readiness or schedule-activation approval is claimed.

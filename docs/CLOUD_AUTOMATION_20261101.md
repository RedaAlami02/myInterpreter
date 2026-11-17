# Application automation — November 1

**November 2 continuation:** read
[APP_CONTINUATION_20261102.md](APP_CONTINUATION_20261102.md) for current state.
The private worker release now uses six-queue checkpoint v2, positive admission,
coordinated dividend publication and bounded company refresh. Cloud verification
passed 223 Python and 61 Deno tests plus exact six-queue artifact readback/removal.
One separate genuine fundamental test used a local exact-package runner and
hosted gateways: 20 real responses, one stored archive, one accepted projection,
successful cleanup. It does not prove GitHub source access or recurring operation.
All recurring controls remain off; the four-queue/295-test descriptions below
are historical evidence, not the current implementation inventory.

Continue website, phone and original job migration; prediction work is excluded.
This checkpoint supersedes the cloud-transport pending state in the October 31
handoff. It does not change the installed Supabase state or activate collection.

## Completed implementation

- `cloud_collect.py` wires the existing collectors to the actual four retry
  queues. Quote runs carry full publication inputs and optional enrichment;
  dividend and fundamental requests keep their separate recipes. Configuration
  files live outside the checkpoint tree and are removed after execution.
- `collect-durable.yml` restores the exact preceding admitted run's checkpoint,
  runs the collector with a bounded timeout, and checkpoints even after collector
  failure. An initial empty state requires explicit bootstrap. Missing, expired
  or corrupt expected state stops execution; interrupted runs without a complete
  checkpoint block the chain. There is no silent older-state fallback.
  Guard-skipped jobs do not break the chain.
- A newly uploaded checkpoint is downloaded and verified before any superseded
  operational checkpoint is removed. Newest and preceding checkpoints remain.
  Production names and synthetic acceptance names have distinct namespaces.
- Checkpoints are at most 64 MiB; the workflow reserves up to 195 MiB including
  artifact overhead and an in-flight copy. This is an application budget, not a
  verification of the account's shared free allowance. Shared headroom must be
  checked before setting the separate activation flag.
- All workflows remain manual-only and use commit-pinned actions. The original
  non-durable collection entry is unconditionally disabled. New collection needs
  both `APP_DURABLE_COLLECTION_ENABLED` and `APP_CHECKPOINT_HEADROOM_VERIFIED`,
  in addition to the independently controlled disabled backend/source gates.
- Only metadata/retention steps receive an explicit GitHub token. Neither
  synthetic verification nor its artifact test receives collection credentials.

The existing private worker repository was updated with the generic code. Its
private visibility and remote Git blob identities were checked. Ten existing
reference/SQL files were preserved byte-for-byte; no SQL was applied. No main
repository push, website upload, account/email operation, secret upload, source
request or live schedule/collector dispatch occurred.

## Verification

| Check | Result |
| --- | --- |
| Main managed Python suite | 295 passed |
| Distribution boundary tests | 3 passed |
| Standalone synthetic worker suites, final cloud run | 209 passed |
| Function boundaries, final cloud run | 59 Deno tests passed |
| New synthetic artifact test | 2 local tests passed; hosted upload/download/four-queue restore/exact deletion passed |
| Independent review | Cloud lifecycle, distribution and synthetic cleanup reviewed; findings fixed |

Two issues caught during integration were fixed: a shared secret file was created
twice under exclusive creation, and a job-level skip could be mistaken for an
admitted predecessor. Full regression also caught and fixed a CLI umask leak
between in-process tests. Failed logs/packages remain private rather than being
presented as successful acceptance.

Final distribution contains 68 payload files. Manifest SHA-256:
`0888ab6406baef5f43e0121e1e0cf8cff32cdf82630a66ddf7dd5521b28c1a22`.
Private receipts, cloud logs, exact commit IDs, original packages and separate
release checkouts: `private/app-automation-20261101/`.

Final cloud run **41329652845** completed successfully in **17 seconds** of job
elapsed time. Its tiny synthetic checkpoint was uploaded, downloaded, checked
byte-for-byte across all four channels and removed. The exact run's artifact
listing confirms **zero remaining artifacts**. Evidence:
`private/app-automation-20261101/cloud-acceptance-receipt.json` and the private
cloud log. This measured synthetic test runtime does not estimate source-job
runtime or establish the account's remaining monthly allowance.

## Limits and next work

The synthetic test proves transport of invented bytes, not provider access,
production checkpoint-chain operation or source authority. Source-use authority
is already supplied; a new live trial/schedule still needs its own activation
scope. Never repeat the consumed earlier trial.

Abrupt runner loss before upload can still lose unacknowledged runner-local
copies. Artifact expiration is finite (90 days requested for operational state);
missing state causes an explicit stop. Never bootstrap over lost expected state.
Storage restrictions, shared quota or retention settings can reject uploads and
must be resolved without deleting original historical evidence. A cancelled run
can intentionally require operator reconciliation even if an older copy exists.

Still remaining: fresh shared compute/storage budget acceptance, scoped live
collection/source admission, new-listing persistence/profile updates, remaining
dividend/fundamental hosted acceptance, daily P&L/source integration and operational
retention outside retry checkpoints. Original five-minute depth cadence is still
different from the current managed hourly window; do not claim exact parity.

SMTP/redirect allowlist, real signup/reset/logout and actual phone acceptance
remain separate. Both saved email bindings remain disabled under the last
October 31 hosted verification. Website/auth/navigation changes remain local.
No production readiness claim is made.

# Decision: reuse private Python collectors on the slim runner

Owner delegated the platform decision. Select private GitHub `ubuntu-slim` for
the current Python collectors, retaining Supabase as the private application
backend and object archive. Do not create another hosting account or port the
collectors to a new runtime merely to reduce scheduled-job costs.

## Implementation

- Durable collection and synthetic-verification workflows now select
  `ubuntu-slim`; existing default-off gates, private/default-branch restrictions,
  timeouts, concurrency and durable checkpoint handling remain intact.
- Dependencies are installed into a temporary runner directory with explicit
  `PYTHONPATH`, avoiding mutation of system Python on the minimal runner.
- Package validation permits only the two documented GitHub Linux runner labels;
  schedules and unpinned actions remain rejected. Four package-boundary tests
  passed, including rejection of a self-hosted replacement.
- The exact generic 75-file package plus manifest was published to the existing
  private worker repository, preserving ten unselected files byte-for-byte.
  All 76 published blobs were read back and verified. Main project Git state,
  credentials and source configurations were not pushed.
- Private commit `1dfc6248a0e9f2e5baf6396e51976e65608555ae`, package manifest
  SHA-256 `a1073434fcf1f04ffa0065ec4e234017261e080ed9bfe709786fe6b90ce89be1`.
- Synthetic cloud acceptance run: `41521436164`; result recorded below once
  completed. No collection/source credentials are supplied to this workflow.

## Cost and storage decisions

Published slim rate is $0.002 per billed minute, versus $0.006 for standard
Linux. At two billed minutes for 2,714 separate original-cadence November jobs,
the scenario is $10.856 rather than $32.568, before other shared usage/retries.
This is not a measured collector bill; a slower CPU and setup overhead may
change duration. Do not treat the account's full included credit as unspent.

Preserve the existing latest-row SQL publication pattern. Keep high-frequency
raw captures in private file storage, retain their hashes/source timestamps and
avoid duplicating every intraday price into SQL. Do not delete originals or
move recovered historical tables without verified durable backups and a specific
reviewed migration. Use the recorded capacity baseline and repeat the read-only
measurement after representative enabled collection.

No automatic retention or archive deletion is authorized by this cost decision.
The 350 MB archive/projection guard remains unchanged; its 15.55 MB headroom
requires monitoring. See `RUNNER_AND_STORAGE_ASSESSMENT_20261102.md` for measured
samples and explicitly qualified growth scenarios.

## Activation remains separate from runner verification

A successful synthetic run establishes runtime/dependency/checkpoint compatibility,
not live source access, complete price coverage, source authority admission,
recurring leases, official-close availability or account-wide remaining budget.
Those checks still govern collection and saved P&L. No schedules or financial
writes were enabled by this publication. Prediction-model work remains excluded.

## Hosted acceptance completed

Run `41521436164` succeeded on the actual `ubuntu-slim` runner. Job started
20:41:04 UTC and finished 20:42:17 UTC: **73 seconds**, two billed minutes,
nominal $0.004 from included credit at the published rate. This is the full
synthetic verification job, not a live collection runtime benchmark.

- 246 standalone Python tests passed.
- 24 archive gateway and 42 publication tests passed (66 Deno total).
- All six synthetic queues restored with exact checkpoint bytes.
- Upload, exact-artifact download, restore and cleanup steps succeeded.
- Fresh API read confirms **zero remaining artifacts** for this run.

The remote durable workflow now selects the verified slim runtime. Its source,
checkpoint headroom and collection enablement gates remain unset/off. No live
collection was attempted and no production schedule was activated. Full private
logs and publication/blob-verification receipts are under
`private/slim-runner-20261102/`.

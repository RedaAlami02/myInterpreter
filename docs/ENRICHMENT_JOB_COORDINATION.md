# Company enrichment coordination — October 30

The existing enrichment calculations and original capped job selection now have
an opt-in executor: `automation/managed/enrichment_jobs.py`. This is a **local,
tested implementation**, not an enabled hosted job. No source requests, hosted
changes, schedule activation, real accounts/emails, release builds or pushes were
performed in this continuation.

## What changed

The previous fundamental collector used a provider/kind/hour completion key.
Completing one company could incorrectly skip a different company in that hour.
New `private-acquisition/v3` archives add the exact `symbol:<symbol>` subject.
SQL017 keeps subject metadata and per-company/per-trial completion separately;
existing v2 archives, slots and original timestamps remain intact. A new trial
cannot adopt an old digest or be blocked by an old trial's subject completion.
Legacy finalization refuses scoped reservations. Its original wrapper body is
hash-pinned before the additive restriction; its OID and grants are preserved.

The fundamental CLI defaults to scoped collection. Explicit `--legacy-unscoped`
retains old v2 behavior. Unsupported legacy database storage fails before a
scoped source request. The archive gateway's additional
`APP_ARCHIVE_SUBJECT_ENABLED` switch defaults off. The projection boundary checks
the exact v3 fundamental symbol/subject while retaining legacy verification.
SQL017 and these function changes **have not been deployed**.

The executor reuses `price_jobs.enrichment_jobs()`, `fundamental_collect`,
`fundamental_feed`, the archive client, projection client and private `Outbox`.
The original separate initial/refresh limits and first-quarter-hour rule remain.
Execution is bounded to one through five attempted jobs per invocation; complete
plans, skipped work, failures and deferred counts are reported separately.

Raw archive bytes and the prepared projection document are saved together before
publication. Restart retries use the same archive, document and actual original
preparation timestamp. Changed identity indexes and altered derived fields are
rejected. Incomplete attempts are archived without merging company fields.
Preparation failures retain raw evidence for review. No exception detail, company
identity, endpoint, recipe or response body is printed by the executor.

The job wrapper has an explicit 24 MiB entry bound and 64 MiB spool allowance.
Ordinary archive/outbox/gateway limits remain 8 MiB. Capture is refused if there
is insufficient worst-case job-spool capacity. Archive and job spools must be
separate, non-nested private directories. `--isolated-store` uses SQLite archive
and projection output, without constructing the remote publisher. The library
also rejects a remote `ProjectionPublisher` paired with SQLite.

## Admission and current limits

A false completion response is **not** permission to collect. Each fresh scoped
request needs a separate positive admission response. It checks the enabled
archive/provider/private bucket, current lease/kind, remaining object/byte budget,
database and Storage guards, and more than 300 seconds remaining. Enrichment also
requires projection capability and matching enabled provider control. Completion
and final commit still enforce their own current lease and privacy checks.

This is advisory preflight, not a reservation or replacement for the approved
exact-trial orchestrator. Competing workers can consume capacity afterward; a
lease can expire/revoke during acquisition. Commit rejection preserves queued
evidence rather than retimestamping it. The preflight does not prove the caller's
recipes equal an externally approved plan or pin an exact subject allowlist.

Existing manual leases still cap **total** bytes at 8 MiB. Admission conservatively
requires the full 8 MiB for each new capture; after the first stored object it
will refuse another fresh capture in that same trial. A default five-minute
lease cannot pass the remaining-time check. Multi-company execution is verified
in isolated storage, not a claim of multi-company hosted acceptance. No lease
limits were widened, no new trial was issued, and the consumed earlier trial must
not be revived. Recurring execution needs its own reviewed production gate.

Crash guarantees start after durable queue storage. Process death while fetching
or before that write can require another request; exactly-once source collection
is not claimed. Retries cannot adopt old-trial evidence without explicit recovery.
Do not use the raw-archive `flush_outbox.py` on this job spool. Existing v1 outbox
bundle transport is limited to 8 MiB entries and is **not** sufficient for these
larger publication jobs; private cross-run carriage remains to be implemented.

## Inputs and a future manual invocation

Private source configuration and the existing private fundamental index are
required. The company context is owner-prepared JSON with contract
`private-enrichment-context/v1`, actual `observed_at`, and a `companies` map using
the existing application fields. The CLI refuses future or more-than-one-day-old
contexts. Automated fresh context retrieval is not implemented. Keep all these
files under ignored private storage, not in a workflow definition.

```sh
python3 automation/managed/enrichment_jobs.py \
  --config private/jobs/source-config.json \
  --index private/jobs/company-index.json \
  --context private/jobs/company-context.json \
  --spool private/jobs/pending-publications \
  --max-jobs 1
```

This command is documentation, **not** a command run during this continuation.
Remote mode needs the existing scoped archive/projection environment tokens and
a separately approved active window. No project/admin key is supplied to workers.
Local-output mode adds `--isolated-store /tmp/enrichment-preview.sqlite`; it still
uses the explicitly configured source fetcher, so it is not an offline-fixture
mode. Unit tests inject synthetic source responses and make no external requests.

## Verification and handoff

The managed suite, gateway/projection/app-publisher suites, staged SQL tests and
bundle/tooling tests pass; exact final totals and file hashes are recorded in
ignored `private/enrichment-jobs-20261030/CHECKPOINT.json`. SQL runs use fresh
synthetic databases through a `/tmp/` Unix socket. The SQL suite includes all 42
previous display/trial cases plus subject isolation, cross-trial same-hour
completion, immutable retry, role boundaries, rejected adoption, revoked trials,
incomplete captures and admission capacity checks. No hosted acceptance is implied.

Independent local review found and closed cross-trial completion, isolated remote
publication, missing positive admission and oversized wrapper issues. Review did
not independently rerun the full SQL suite. Historical frontend acceptance is
unchanged and was not repeated for this backend-only delta.

Review-bundle contract v2 includes the new executor, previously omitted price
modules and SQL014–017. Historical v1 bundle verification remains supported;
old packages are not rewritten. The new bundle is review-only and contains no
recipes, credentials, raw data or schedules.

Remaining work, in order:

1. Review/pin the exact new disabled backend package and prepare bounded hosted
   fundamental acceptance without reusing the consumed quote trial.
2. Add fresh private company-context retrieval and durable private cross-run job
   carriage, then invoke this executor from approved price-job orchestration;
   verify runtime and free private-runner allowance.
3. Connect new-listing proposals to reviewed identity persistence/profile updates.
   Proposals already exist, but this executor dispatches only mapped companies.
4. Complete remaining original-job coordination, real signup/SMTP and hosted/
   device preview acceptance before frontend cutover and recurring schedules.
5. Return to prediction production gates after the website/phone migration work.

Last hosted checkpoint remains SQL016, archive/projection functions v6 and app
publisher v8, all disabled. No current hosted state was re-read in this offline
continuation. Source-use authority remains supplied; source identities stay private.

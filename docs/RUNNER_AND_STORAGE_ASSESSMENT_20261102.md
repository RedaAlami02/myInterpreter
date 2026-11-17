# Managed script runners and measured storage capacity

Measured November 2, 2026. Read-only database inspection; no activation,
publication, data deletion, history relocation or prediction work.

## Decision

Private managed scripts need not use standard GitHub runners. First benchmark
`ubuntu-slim` with the existing Python collectors: this preserves the current
implementation and offers a lower published rate. Keep Supabase Cron + Edge
Functions as the integrated alternative for short network-bound collectors.
Do not port everything or choose a new platform based only on invocation counts.

| Option | Confirmed capability / allowance | Fit and remaining check |
| --- | --- | --- |
| GitHub `ubuntu-slim` | Private repositories supported, one core/5 GB, 15-minute maximum; $0.002/billed minute | Lowest adaptation for existing Python. At 2 billed minutes for all 2,714 original-cadence November jobs, $10.856 vs $32.568 on standard Linux. Runtime, installed tools, artifact lifecycle, source access and shared remaining credit still need acceptance; not switched or activated. |
| Supabase Cron + Edge Functions | SQL/HTTP scheduling; 500,000 free function invocations; 150-second wall time and 2-second CPU/request | Existing account and private backend. 2,714 once-per-job calls use 0.543% of invocation allowance, before gateways/retries. Current collector Python is not a drop-in Deno module; split/adapt bounded collectors and measure CPU/wall time. `pg_cron` available but not installed on this project. |
| cron-job.org + authenticated hosted endpoint | Free HTTP scheduling as often as every minute; 30-second request timeout and 64 KB response cap | Scheduler only: does not host/run Python. Can trigger an existing authenticated function. Backend CPU, storage, durable completion and invocation limits still apply. No secrets in URL query strings. |
| Cloudflare Workers Cron | 100,000 free requests/day, five Cron Triggers/account, 10 ms CPU/invocation on Free | Useful lightweight dispatcher. Not a verified direct host for these Python collectors or PDF tooling; network wait is excluded from CPU, but parsing/signing/compression still counts. |
| Google Cloud Run service + Scheduler | Request-billed services: 180,000 vCPU-seconds, 360,000 GiB-seconds, 2 million requests monthly free-tier baseline; three Scheduler jobs free | Good Python/container compatibility. Billing-enabled account required; region, registry/build, startup and network costs also matter. No guaranteed hard $0 cap established. No account credentials or deployment verified. |

At 2,714 calls of 30 seconds on a one-vCPU request-billed Cloud Run service,
nominal runtime is 81,420 vCPU-seconds before startup, retries and other usage.
That is an illustrative fit, not a measured bill or permission to deploy.
One scheduling dispatcher can select due jobs, but must not turn into an
unauthenticated arbitrary URL/script executor.

Sources, checked November 2:
[GitHub runner capabilities](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[GitHub rates](https://docs.github.com/en/billing/reference/actions-runner-pricing),
[Supabase Cron](https://supabase.com/docs/guides/cron),
[Supabase pricing](https://supabase.com/pricing),
[Edge limits](https://supabase.com/docs/guides/functions/limits),
[HTTP scheduler limits](https://cron-job.org/en/faq/),
[Workers limits](https://developers.cloudflare.com/workers/platform/limits/),
[Cloud Run pricing](https://cloud.google.com/run/pricing),
[Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing),
[Cloud Run billing setup](https://docs.cloud.google.com/run/docs/setup).

## Actual database measurement

Verified-TLS repeatable-read READ ONLY transaction, no account/row contents
printed. Current database: **334,452,403 bytes (334.45 MB decimal)**.

- Advertised 500 MB database headroom: **165.55 MB**.
- Installed archive/projection 350 MB safety-guard headroom: **15.55 MB**.
  Other writers may have separate controls; this is not Supabase's quota.
- Current private file storage: **30,568 bytes**, two archived objects.
  This is this project's metadata total, not fresh proof of organization-wide
  usage; another project's consumption must still be included.

| Existing relation | Rows | Physical size including indexes/TOAST |
| --- | ---: | ---: |
| migration-stage documents | 110,723 | 114.38 MB |
| daily-price reference | 56,756 | 73.92 MB |
| original market observations | 110,067 | 49.86 MB |
| versioned historical observations | 58,121 | 47.55 MB |
| preserved recovery files | 1,797 | 30.71 MB |

These are distinct retained representations/evidence; space overlap alone is
not authorization to delete any of them. No recovered original was removed.
Table/index allocation includes page slack and bloat; tiny tables' allocated
bytes divided by two rows do not represent marginal per-row growth.

## Measured samples and forward scenarios

Eight-hour weekday schedule, November's 21 weekdays, 81-company scenario:

| Data / policy | Measurement basis | Estimated added storage/month |
| --- | --- | ---: |
| Quote raw archives, every 15 minutes | One genuine current-format compressed batch, 25,224 bytes × 672 | 16.95 MB in file storage |
| Depth raw archives, every five minutes | All 1,686 preserved original gzip JSONL objects, 23,580,325 bytes total; 13,985.96 mean bytes × 2,016 | 28.20 MB in file storage, historical-format proxy |
| Combined quotes + depth | Above two samples, no other jobs | **45.15 MB** |
| Combined plus 50% scenario reserve | Allowance for variability/envelopes; not a statistical confidence interval | **67.72 MB** |
| Append all 81 prices each 15 minutes into SQL | 54,432 rows × existing large market table's 453.04 physical bytes/row | **24.66 MB SQL**, proxy only |
| Append one 81-company daily history row/session | 1,701 rows × existing versioned history's 818.06 physical bytes/row | **1.39 MB SQL**, proxy only |

The 1,686 original objects were SHA-256 inventoried and gzip-decoded read-only:
**136,562 records**, zero invalid objects, capture range September 22 08:04:51
through October 22 10:06:18 UTC. They were already gzip compressed; recompression
does not reduce size. Originals were not modified. The new depth worker's
raw-response-plus-normalization envelope has not been measured as a genuine
recurring complete batch; its size may differ materially. Quote sample size is
one, so these estimates are not a proven future rate.

Current publication keeps latest application/shadow rows; it does NOT imply
inserting 54,432 new `public.data` rows/month. Append-every-intraday-price is a
comparison showing why SQL should not become the raw archive. At that proxy
rate, the current 350 MB guard would be exhausted in under one month even
before other growth. Do not silently change source/history retention semantics.

At 67.72 MB/month, quotes+depth alone reach the installed 750 MB file-storage
guard after approximately **11 months**, assuming no other data/growth and
unchanged capture sizes. Official reports, fundamentals, dividends, incomplete
attempts, retry records, lease/run metadata, P&L provenance and other projects
reduce that runway. Keeping every capture forever cannot fit a fixed free quota.
No precise SQL exhaustion date is defensible for the bounded-latest design until
representative collection plus vacuum/index/receipt growth is observed.

## Concrete storage approach

Keep Auth, portfolio/trades, current application views and queryable daily data
in private Supabase tables. Keep high-frequency raw evidence as private objects,
with catalog hashes/source timestamps retained. Agree on a hot retention period
and verify an independent durable archive before removing any remote copy.
Never erase the only original evidence to meet quota. No automatic retention or
archive relocation was enabled here.

Private object storage such as R2 offers a larger candidate archive:
[10 GB-month Standard storage, 1M Class A and 10M Class B monthly operations
included](https://developers.cloudflare.com/r2/pricing/). This is object storage,
not a SQL database or Python host. Billing/account controls and integration are
not verified, and exceeding free allowances can incur charges. Any future
buckets must remain private; financial provider identities must stay private.

## Repeatable monitoring

`tools/measure_storage_capacity.py` now captures database/table/index allocation,
private archive totals and project Storage metadata using a read-only transaction
and verified TLS. Output is a new, non-overwriting local JSON snapshot. Optional
`--previous` reports the observed byte delta/time without calling it a certified
collection rate. No continuous monitoring schedule was installed.

Actual command shape (use the existing private CA path, keep output ignored):

```sh
python3 tools/measure_storage_capacity.py --ca /path/to/database-root.crt \
  --output private/capacity-YYYYMMDD/snapshot.private.json \
  --previous private/capacity-20261102/repeatable-baseline.private.json
```

Initial utility execution succeeded against the real database and matched the
independent detailed measurement: 334,452,403 bytes. Python compilation passed.
Private evidence is under `private/capacity-20261102/`, including actual table
counts/sizes, object hashes, measured sample sizes and calculated scenarios.

Collect representative snapshots after one day and a week of enabled collection,
with ingestion counts, before extrapolating steady-state growth. Schedules are
currently disabled, so no genuine ongoing ingestion rate exists to measure yet.

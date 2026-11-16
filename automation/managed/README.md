# Private managed acquisition

November 2: new cloud price jobs read company inputs through their own publisher
and scoped quote lease; a separate enrichment provider is no longer required.
SQL025 and the endpoint were installed disabled and a bounded 81-company read
passed with exact cleanup. Private cloud verification passed 232 Python and
66 Deno tests plus six-queue transport. Read
[`PRICE_INPUT_REPAIR_20261102.md`](../../docs/PRICE_INPUT_REPAIR_20261102.md).
This is not fresh-price or recurring-production acceptance; schedules remain off.
Older four-queue/version/deployment descriptions below are historical.

November 1: the generic workers are updated in the existing private repository.
The new manual-only durable workflow and synthetic hosted artifact roundtrip are
implemented; cloud acceptance passed 209 Python and 59 Deno tests plus exact
four-queue transport/cleanup. Live collection and schedules remain off. Read
[`CLOUD_AUTOMATION_20261101.md`](../../docs/CLOUD_AUTOMATION_20261101.md) before
older implementation/deployment notes below.

Current application migration state is recorded in
[`docs/APP_COMPLETION_20261031.md`](../../docs/APP_COMPLETION_20261031.md).
The backend archive/feed/projection services through SQL019 are installed and
verified **disabled**. Older deployment-state statements below are historical
implementation notes, not the current hosted state. Current prices remain
shadow-only; production collection and schedules are off.

Quote retry now retains exact prepared documents and inputs before archive
acknowledgment, retries before `ALREADY_COMPLETE`, and durably saves acceptance
receipts before removing pending work. Optional enrichment invokes the existing
rules after verified publication. See
[`RUNNER_CHECKPOINTS.md`](../../docs/RUNNER_CHECKPOINTS.md) for the new local
four-queue checkpoint tool and its exact producer layout. Local tests and ZIP
transport do not constitute hosted cross-run persistence or schedule activation.

This package has no retired backend dependency and contains no provider identity,
endpoint, personal record or production credential. Native request recipes and
field bindings are supplied in an encrypted Actions secret. The source namespace
must be an opaque `feed_` identifier, not a provider name.

`probe.yml` is a manual, one-minute standard Ubuntu runner eligibility test. It
uses no secrets, external actions, caches or uploaded artifacts. `collect.yml` is
manual-only and additionally disabled unless `APP_COLLECTION_ENABLED=true`.
`source-probe.yml` is a separate manual read-only HTTP check, capped at two minutes; it logs only status, bytes and a checksum and never imports data. There are no enabled schedules. Leave the account's $0 additional-spend cap in
place. A successful probe proves runner eligibility at that moment, not remaining
monthly minutes or source access.

The collection workflow dispatches `quotes` to `market_collect.py`, `depth` to
`depth_collect.py`, `dividends` to `dividend_collect.py` and `fundamentals` to
`fundamental_collect.py`, through `run_collection.py`. Each job selects its own
encrypted configuration; none can fall back to the legacy parser or another job's
recipe. Fundamentals additionally require an explicit `--symbol`. The dividend and
fundamental configurations and the narrow archive-gateway credential still need
private provisioning. Publishing this package does not configure secrets or
activate collection. The older `worker.py` CLI remains a reference implementation.
`verify.yml` is a separate manual three-minute regression run using synthetic
fixtures only. It receives no collection or database credentials, contacts no
market source, and uploads no artifacts. It does not activate collection.

The owner's Pro plan includes 3,000 private minutes/month, shared by all private
repositories. Proposed recurring job timeout allowances are 1,472 quote/depth,
92 valuation, 138 fundamentals and 30 dividends: 1,732/month; plus 150 manual
minutes = 1,882, leaving 1,118 before other private usage and runner overhead.
These are planning allowances, not measured runtimes or billing guarantees.
Private usage elsewhere must be monitored. Standard runners only; no paid larger
runners or artifact uploads. See [included usage](https://docs.github.com/en/billing/reference/product-usage-included).

Planned quote cadence is 15 minutes, with hourly depth, weekday local hours 09–17.
Fundamentals would run daily in a bounded batch and dividends weekly. This does
not preserve every former function cadence. GitHub schedules are best-effort;
late jobs must not invent missing capture timestamps. Scheduling remains gated
on budget, source-access and storage checks, and actual cloud timings.

## Evidence boundary

`worker.py` performs bounded HTTPS requests with no redirects, preserves exact raw
bytes and SHA-256 checksums in a compressed immutable envelope, and stores source
event time separately from actual HTTP receipt time. Recipe configuration must
provide source session dates and the complete quote universe. An index is required.
Missing data, identity conflicts, stale/future events and malformed responses
produce INCOMPLETE evidence. Unknown source event times remain explicitly unknown.
No historical observation is relabeled as a current quote or official close.

The manual cloud collection template now uses `APP_ARCHIVE_GATEWAY_URL` and
`APP_ARCHIVE_WRITE_TOKEN`, bound to `archive_project_reference` in the private
recipe. It supplies no database URI or elevated API key. `archive_store.py` uses
the staged write-only gateway: raw gzip files go to private object storage,
with small metadata receipts in PostgreSQL. The gateway/SQL009 are not deployed.

The older, explicitly configured PostgreSQL backend requires an `app_collector` credential with
verified TLS. SQL007 provides only two functions in a non-exposed private schema;
this role cannot read raw tables, portfolios or Auth. It starts NOLOGIN and must
be provisioned separately after review. The archive stops before its 350 MB guard
instead of deleting evidence. It does not create app quotes, P&L or predictions.
Application projection, validated dividend/fundamental updates, daily valuation,
retention/archive export and production schedules are not implemented here yet.
Do not describe raw acquisition as a fully migrated application data feed.

Before a remote write, `outbox.py` fsyncs a private bounded transmission copy.
An exact STORED receipt removes only that copy; failures retain it. Normal
collection flushes pending copies before fetching again. `flush_outbox.py`
inspects pending bytes by default; `--send` retries those exact bytes without
collecting or changing timestamps. Partial filesystem writes require review.
Runner-local copies do not survive ephemeral-runner disposal.

`outbox_bundle.py` carries pending copies across runs: `pack` writes one bounded
private bundle (≤ 64 entries, ≤ 64 MiB) and `unpack` restores it into a fresh 0700
spool with exact filename/hash/length checks, refusing conflicts and never
overwriting different bytes. Persist the bundle only in the private repository
with short retention and delete it after acknowledgement. Artifact quota and a
private cross-run destination still need verification before schedules; none is
enabled.

GitHub's included-usage reference now expresses Pro compute as an $18 allowance;
its Actions billing page also lists the legacy 3,000-minute allowance. Keep the
earlier 1,882-minute estimate as a plan, and verify the actual account's current
usage/allowance before activation. Artifact capacity is shared with other account
usage and is not assumed available for a fallback archive.

## Local verification

```
python3 -m unittest discover -s tests -v
python3 run_collection.py quotes --config /private/path/market.json --isolated-store /tmp/isolated.sqlite
python3 run_collection.py depth --config /private/path/depth.json --isolated-store /tmp/isolated.sqlite
python3 run_collection.py dividends --config /private/path/calendar.json --isolated-store /tmp/isolated.sqlite
python3 run_collection.py fundamentals --symbol AAA --config /private/path/fundamentals.json --isolated-store /tmp/isolated.sqlite
python3 ../tools/prepare_dividend_projection.py --config /private/path/calendar.json \
  --archive /private/path/calendar.json.gz --sha256 <digest> \
  --index /private/path/dividend-index.json --output /private/path/projection.json
python3 ../tools/prepare_fundamental_projection.py --config /private/path/fundamentals.json \
  --archive /private/path/bundle.json.gz --sha256 <digest> \
  --index /private/path/fundamental-index.json --output /private/path/projection.json
python3 ../tools/publish_projection.py --document /private/path/projection.json
python3 outbox_bundle.py pack --spool /tmp/private-market-outbox-<ref> --output /private/path/outbox.zip
```

Both normal collectors enforce their market windows. The market CLI also supports
`--recorded-response` and `--recorded-receipt` for a hash-checked historical replay,
but only with `--isolated-store`; it cannot initialize PostgreSQL in replay mode.
Use `market_collect.py` directly for those replay-specific options.

The v2 normalization recipes retain source clock text, actual HTTP receipt times,
raw hashes and explicit completeness. Naive source clocks retain UNKNOWN timezone.
A configured optional last-trade summary may use `blank_is_null: true`; this
retains a genuinely absent last-trade price as null, never zero or a substituted
order price. Nonblank malformed numbers remain errors. Book completeness does
not imply complete stock quote coverage or permission to value a portfolio.
Failed book normalization retains its raw digest and receipt in the draft v2
manifest as well as the full raw capture. Original earlier manifests are retained
unchanged; reprocessing must produce separate, explicitly labeled replay evidence.

`COMPLETE` means acquisition coverage under the chosen recipe, not price authority.
All v2 results remain UNPROMOTED and prediction-ineligible; complete book data
cannot manufacture a missing last trade, close or detailed stock quote.

## Separate application preview

`app_feed.py` verifies the original gzip archive hash and rechecks its normalized
values against the raw body/private recipe before deriving a shadow candidate.
Explicit exact company mappings are required; no fuzzy matching. Missing/conflicting
quotes remain unavailable, with conflicts retained. Source-clock timezone stays
UNKNOWN. Same-date receipt alone does not establish an exact source event time.
An expired capture never yields a current display price.

The optional legacy-ID bridge is limited to explicit recorded replays whose only
missing fields are derived capture/observation IDs. It cannot repair or hide a
price/time/coverage mismatch or admit an old-format current acquisition. Original
archives remain unchanged; candidate metadata declares that IDs were newly derived.

SQL010 stores a bounded latest shadow candidate per pinned provider, referencing
the verified SQL009 archive. Only a trusted service publisher may write. It is not
called by the worker's write-token gateway. Its authenticated read RPC exposes
only sanitized preview rows and rechecks staleness and archived evidence. It starts
disabled and never writes recovered `data`, `latest_prices`, models or portfolios.
It is not installed/deployed. PHP/mobile readers remain separate from legacy data
contracts and are not activated in this package.

### Publishing the preview

`app_publish.py` is the trusted publisher for the managed job. It takes only the
archive the job just created, requires `CURRENT_ACQUISITION` with original
normalizer identities, and refuses replays, the legacy ID bridge, and any mapping
or recipe that does not match the approved pins in the private publish profile. It
builds the candidate with `app_feed.build` (hash, raw-value and exact-mapping
verification) and submits it through the separate `app_publish_` token to
`automation/app-publisher/`, which re-reads the archived object and binds every
submitted price to the stored frame before the service-only RPC.

`market_collect.py --publish-profile` publishes immediately after a successful
archive save in the same run; `run_collection.py quotes` forwards it. Publication
is refused with any local isolated or recorded store. `APP_PUBLISHER_URL` and
`APP_PUBLISHER_TOKEN` are required; the profile is an encrypted secret. The
publisher function and SQL010 are not deployed, so this path is implemented and
tested but not active.

A publish that fails after the archive was stored leaves valid evidence but no
feed update. The next capture supersedes it; a retry of that same archive is only
possible while it is still within the publication freshness window, and the
`ALREADY_COMPLETE` collection path does not republish. Use `app_publish.py
--config --profile --archive --sha256` for an explicit operator retry from
retained bytes; it never invents a newer receipt time.

Both candidate persistence and display are SHADOW_ONLY. Automatic app projections,
fundamental/dividend jobs and valuation require their remaining implementation,
reviews and activation. Do not give CI a privileged key to bypass that boundary.

## Dividends

`dividend_collect.py` fetches the configured calendar pages, archives each raw page
with its receipt time and declared charset, and states whether every required year
was obtained. A next-year page that is not published yet (404) is optional and does
not make the run incomplete; a required page that fails does. Nothing is derived at
collection time.

`dividend_feed.py` turns those verified bytes into a `dividend-projection/v1`
document without inventing anything: exact amounts and ISO dates are preserved,
only a source ex-date marks a payment confirmed, conflicting payment periods are
excluded and retained for review, unmatched issuers are retained, and duplicate
spellings collapse to the most complete row. Company resolution needs a private
index (`private-dividend-index/v1`); there is no fuzzy matching.

`dividend_calendar.py` carries the payment-period rules shared with
`core/dividends.php` and `myinterpreter_app/lib/dividends.dart`; the three are
tested against `tests/fixtures/dividend_periods.json`. The managed parser is also
compared with the archival Appwrite parser on the same pages.

`tools/prepare_dividend_projection.py` writes the projection under the ignored
`private/` directory only, with no remote-write option. Publishing dividend rows to
`public.dividends` still needs a separate reviewed service boundary; `run_collection`
has no dividend publish step.

## Fundamentals

`fundamental_collect.py` fetches the configured endpoint set for one symbol in
three phases: identity (symbol-keyed), company statements (keyed by the external
name resolved from the registry response) and symbol-keyed profile endpoints. It
archives every raw response with its receipt time and marks the run incomplete if
any configured endpoint fails; an unresolved company identity fails the run.

`fundamental_frame.py` derives the reported figures from those payloads. It selects
one fiscal year where the core statements agree, keeps projected profit strictly
separate (`fy_est`/`rnpg_est`), uses the current share count (split-aware), derives
per-share earnings from profit and shares, and leaves every field unknown rather
than borrowing a different year. The archival enrichment's rules are compared in
the tests; both implementations must keep agreeing.

`fundamental_feed.py` verifies the archived bundle and emits a
`fundamental-projection/v1` document for one mapped company, with the exact field
set the `company` table uses. `tools/prepare_fundamental_projection.py` writes it
under `private/` only. Writing these fields to `company` still needs a reviewed
service boundary; the admin-update RPC is for the owner, not for automated
projections.

### Publishing projections

`tools/publish_projection.py` sends one prepared document through the separate
`proj_publish_` token to `automation/projection-publisher/`, which re-reads the
archived evidence, rechecks the document contract and calls a service-only RPC.
SQL013 upserts dividends by company/year/type and merges fundamentals under the
fill-null / newer-fiscal-year rule. The function and SQL013 are installed with
all controls disabled; no recurring publication is active. Temporary trial
credentials were removed afterward. The boundary does not re-derive source values, so the
prepared projection must be reviewed before publication.

### Original price-job parity

`price_refresh.build()` derives full stock/index application rows and enrichment
choices from the exact verified archive. It reuses the original financial rules
in `fundamental_frame.py` and capped dispatch decisions in `price_jobs.py`.
`tools/prepare_app_feed.py --include-price-refresh` exposes the local derivation;
optional `--application-bindings` reads native field paths from private JSON.
Explicit `calculation_rules: legacy_getprice/v1` selects the old collector's
derived reference/change rules. The default does not assume them for a provider.

This is shadow output, with separate provenance. It cannot write application
tables, update valuation prices, fetch new data or enable schedules. See
`docs/PRICE_REFRESH_PARITY.md` for actual parity evidence and unfinished wiring.

The existing publisher now supports explicit opt-in full-row publication with
`--companies` and `--application-bindings`; the private publish profile pins
`application_fields_sha256`. Both exact quote/application hashes are verified in
the combined receipt. SQL016 and the publisher extension are installed disabled.
Full display rows use private `app_feed.application_latest` and authenticated v3
preview; original market and valuation tables remain unchanged. See
`docs/APPLICATION_PRICE_PUBLICATION.md` for limits, evidence and remaining work.

Never put actual recipes, database/admin keys, response bodies or exception details
in workflow logs or this repository. No raw observations or genuine prediction
ledgers are written during unit tests.

### Company enrichment dispatch

`enrichment_jobs.py` connects the existing capped rotation to scoped v3 collection,
archive storage and projection publication, retaining exact pending bytes and
prepared documents for retries. `--isolated-store` keeps outputs in SQLite.
SQL017 and gateway support are staged, with an additional default-off switch;
hosted collection/scheduling is not active. This uses a separate bounded job
spool, not the raw-archive flusher or its v1 transport bundle. Read
`docs/ENRICHMENT_JOB_COORDINATION.md` for admission, current manual-lease limits,
private inputs, tested behavior and unfinished production wiring.

### Exchange reconciliation

`exchange_reconciliation.py` is a pure reconciliation module for Bourse de
Casablanca instrument snapshots. It triangulates current shares, classifies
pre-split annual rows, quarantines unexplained differences and proposes company
fields. `tools/capture_exchange_pages.py` performs the portable cloud capture,
including automatic AIA TLS-chain completion; `tools/reconcile_exchange.py`
writes the report; `tools/apply_reconciliation_cloud.py` calls the audited
service-role RPC. The scheduled workflow is
`.github/workflows/exchange-reconciliation.yml`. Tests:
`tests/test_exchange_reconciliation.py` and `tests/test_exchange_capture.py`.
See `docs/EXCHANGE_RECONCILIATION_20261116.md`.

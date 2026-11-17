# Incremental private source history

`tools/history_delta.py` adds the separately versioned
`private-source-history-delta-v2` archive contract. The original v1 SQL/schema,
source observations and readers remain unchanged. No new grants or deployed
services are required: the append uses the existing private archive tables.

## Two distinct layers

Each v2 version preserves its **complete raw capture set**, including exact
response/request/receipt bytes, hashes and actual capture times. Every source
observation ID and ordinal can be reconstructed from those bytes with the
unchanged v1 identity rule. Duplicate occurrences, conflicting prices and all
native fields survive. Original observation/publication times remain UNKNOWN.

The `observations` rows for a v2 batch are explicitly a **sparse economic-value
projection**, rather than all source observations. The planner compares whole
native-row payloads within a provider namespace and symbol, preserving occurrence
multiplicity. A volume, OHLC or other native-field revision is a new payload even
when its close is unchanged. Symbol/date alone is never a deduplication identity.
Numeric JSON formatting equivalents compare consistently; exact source bytes
and source identities remain preserved independently.

An unchanged economic value in a new raw capture is not inserted into SQL again.
It still exists as a source observation in the complete captured version, with
its own raw hash/ordinal identity. A source's rolling-window expiry never deletes
older parent observations or evidence. Captures without new economic payloads
are retained in local acquisition evidence without a duplicate SQL batch.

## Reading and verification

Consumers must pin an archive batch explicitly. `load_archive()` verifies its
manifest identity, complete raw capture membership and every materialized value,
then reconstructs a full v1-shaped source bundle. V2 parent metadata/version
bindings must exist and match. Appends verify the full parent source and typed
contents both before and after the write. Direct reads verify the selected
version and immediate parent metadata; they do not claim a recursive audit of
every ancestor or distributed anti-rollback guarantees.

Do not count sparse SQL rows as complete source coverage, union batches into
prices without source reconciliation, or silently select an observation by date.
The old direct v1 historical reader rejects a v2 batch. `load_archive()` is the
explicit v1/v2 reader. The sanitized preview exporter now supports
`--archive-id SQL_BATCH_ID --verify-remote`; it compares that reconstructed remote
version with the pinned local full bundle before exporting. Its public content
version identifies the full source bundle; the SQL wrapper batch has a separate
ID recorded in private receipts. Neither is a provider trust or authority grant.

## Import safety

The default `prepare` command is local-only. `verify` uses TLS READ ONLY.
Explicit `apply` validates the plan against its complete parent/source bundles,
locks the archive, and appends one transaction. All values, raw bytes, parent
contents, public-table content fingerprints, privileges and database size are
checked before commit. A matching retry verifies rather than overwriting.
Partial, conflicting, corrupted or missing evidence fails without auto-repair.
Logical rollback does not promise immediate physical disk reclamation.

```bash
python3 tools/history_delta.py prepare \
  --parent PRIVATE_PARENT_FULL_BUNDLE \
  --current PRIVATE_NEW_FULL_BUNDLE \
  --delta NEW_DELTA_FILE --receipt NEW_PLAN_RECEIPT

# For a later v2 parent, also pin its SQL wrapper using --parent-archive-id.
python3 tools/history_delta.py verify \
  --parent PRIVATE_PARENT_FULL_BUNDLE \
  --delta VERIFIED_DELTA_FILE --receipt NEW_READONLY_RECEIPT

# Explicit authorized append, only after local tests and read-only reconciliation.
python3 tools/history_delta.py apply \
  --parent PRIVATE_PARENT_FULL_BUNDLE \
  --delta VERIFIED_DELTA_FILE --receipt NEW_APPEND_RECEIPT
```

All bundles, bindings and credentials stay private. Outputs refuse to overwrite
prior receipts. RLS and private-schema grants are unchanged; no public role gains
access. This is data persistence, not production predictor activation.

## Verified October27 continuation

The actual new source capture contains **57,831 observations**, all 81 stocks and
MASI through October26. Comparing it with the preserved v1 parent found **82 new
instrument/date values**, **57,749 unchanged economic occurrences**, no revisions
to overlapping keys and **76 occurrences absent from the new rolling window**.
All older parent data remains intact. The new raw version still retains all
35 duplicate instrument/date keys, including four conflicting-close keys.

The complete local database trial and live Supabase append each grew by
**1,097,728 bytes**, compared with roughly 48.5 MB for another full normalized
copy. The connected database measured 332,674,739 bytes at commit; later read-only
verification measured 332,723,891 bytes. No existing public-table or parent content
changed. Fresh TLS READ ONLY verification checked all 82 new materialized values,
82 raw captures, all 57,831 reconstructed source observations and the original
57,825-row parent. The new sanitized preview also passed remote verification.

**55 scoped tests passed:** nine delta unit tests, 15 local PostgreSQL integration
tests, 12 v1 integrity regressions and 19 preview regressions. Coverage includes
interruption, rollback, retry, capacity, raw corruption, missing parents, sparse
versus full contract separation, occurrence multiplicity, non-price revisions,
and mismatched preview exports. Full-size tests used a disposable Unix-only
database; actual remote checks required TLS. Numerical pipeline/model hashes
remain unchanged; earlier scientific tests are not relabeled as a new run.

Separately, all four frozen models produced 67 retrospective SHADOW_ONLY rows
for October26, captured/executed October27. Exact restart output equality passed.
This is not a genuine or backdated forward prediction. Today's October27 rows
were absent at capture, so no current-session inference was attempted.

Raw captures still consume space. This saves repeated normalized copies but
does not establish perpetual free retention: durable external raw archiving,
measured growth and retention remain necessary before production. The internal
350 MB guard is not a statement of service quota. No cloud schedule, deployment,
production execution, source publication or account ownership change occurred.

Private receipts: `private/prediction-replacement/continuation-20261027/`.
Independent technical acceptance and separate activation authorization remain
required. Owner source-use permission is already supplied; names stay private.

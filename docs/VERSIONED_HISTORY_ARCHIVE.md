# Private versioned historical archive

Subsequent incremental batches use the separately versioned
[sparse delta contract](HISTORY_DELTA_ARCHIVE.md). The original v1 batch and its
full-row semantics below remain unchanged.

The recovered daily history is now stored additively in Supabase under
`market_history_v1`. It does not replace original market observations or change
the application, portfolio, authentication or genuine prediction tables.

The initial verified batch contains **57,825 source rows and 82 raw captures**,
covering 81 securities and MASI, with economic dates 2023-10-27–2026-10-23.
These are newly retrieved historical source versions, not newly recovered
original observation timestamps. All original observation times remain UNKNOWN.
Actual HTTP completion times are stored separately from economic dates.

## Storage and integrity

- `batches`: immutable manifest and hashes of the source projection, index,
  bindings, observations, raw captures and SQL contract.
- `captures`: exact response, request and receipt bytes in lossless gzip form,
  original hashes and actual completion time. Private configuration identities
  in this evidence are not exposed to applications.
- `observations`: source ordinal and identity, economic date, exact normalized
  close string, original source row and retained quality warnings.

The economic date is deliberately not unique: all **35 duplicate economic keys**,
including **four conflicting closes**, survive. The 16,716 inconsistent source
OHLC rows and 4,152 missing-volume placeholders are retained. No data was repaired
or silently selected. IDs identify source namespace, symbol, response hash and
source ordinal; batch identities pin the complete import version. A consumer
combining batches must reconcile shared source IDs explicitly, never deduplicate
by symbol/date or count every capture as a new economic observation.

RLS is enabled with no policies; public, anonymous, authenticated and service
roles have no archive access. SQL-owner access is used only by the explicit
backend/research tools. There is no new public endpoint or application grant.

## Commands and reader

`tools/import_versioned_history.py` supports `prepare`, `verify` and `apply`.
Prepare is local-only. Verify uses a project-bound TLS READ ONLY transaction.
Apply requires explicit invocation and appends in one transaction, checking
raw/typed readback, privileges, existing public-table content fingerprints and
database size before commit. It uses no overwrite, update or conflict-discard
path. A matching retry reads and verifies the existing batch. Partial or changed
remote contents cause failure rather than automatic repair. Logical rollback
does not promise immediate release of physical disk space from failed inserts.

Native parser bindings, input paths, immutable bundle and receipts belong in the
ignored private migration folder. Never publish bindings, endpoints, raw source
identifiers or credentials. Receipts refuse to overwrite prior results.

`tools/read_versioned_history.py:historical_closes` requires an explicit batch,
namespace, economic date and instrument universe. It returns retrospective close
candidates only. Missing instruments, duplicate observations or wrong namespaces
block selection; there is no preceding-day fallback. A successful historical
read is not evidence of live acquisition, source attestation or production
eligibility. Application integration is a separate, reviewed change.

## Verified evidence and capacity

The current private receipts are in
`private/prediction-replacement/supabase-next-step-20261026/`.
All 110,723 existing staging payloads in 16 datasets were compared before import.
All 57,825 new rows and 82 raw captures were checked both within the committing
transaction and through a fresh read-only connection afterward. October 21–23
each returned 82 exact stock/MASI closes; October 26 returned all 82 missing,
without fallback. Existing public-table fingerprints remained unchanged.

Thirty tests passed: 12 local integrity tests, 10 disposable PostgreSQL integration
tests and eight existing staging/verifier regressions. They cover interruption,
rollback, retries, permissions, capacity, conflicts and provenance. Frozen model,
genuine ledger and accepted Stage source pins remain unchanged. The earlier
prediction regression release was not rerun or relabeled as a new full-suite run.

Measured database growth was about 48.5 MB. The connected database is about
331.6 MB; all three cluster databases, including templates, total about 346.9 MB.
Against a conservative decimal 500 MB budget this leaves about 153.1 MB. The
provider's billing dashboard was not inspected; its reporting can differ or lag.
The importer's 350 MB guard is an internal target, not the service's plan limit.

Supabase publishes a 500 MB free database allowance per project, and database
size includes indexes. [Billing](https://supabase.com/docs/guides/platform/billing-on-supabase),
[database-size measurement](https://supabase.com/docs/guides/platform/database-size).
Daily incremental prices and a small portfolio database are plausible within
this budget; their long-term growth has not yet been measured. Repeating a full
48.5 MB normalized history import daily would exhaust it after roughly three
more copies. Frequent raw/depth captures need a measured retention policy and
separate compressed archival storage. No old evidence has been deleted, moved
out of the database, or made dependent on a new storage service.

Source-use authorization is owner-confirmed. Independent technical acceptance,
current closing-session evidence and explicit activation remain required. No
schedule, deployment, production forecast, source-identity publication or public
push was performed.

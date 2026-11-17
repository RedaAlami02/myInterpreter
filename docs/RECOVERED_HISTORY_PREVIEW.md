# Recovered daily history preview

Newer source versions can use the sparse archive described in
[HISTORY_DELTA_ARCHIVE.md](HISTORY_DELTA_ARCHIVE.md). Export them with the explicit
`--archive-id SQL_BATCH_ID --verify-remote` binding; the original v1 export path
remains supported. The October27 continuation includes history through October26.

The PHP application now has an opt-in daily history view at `history-preview.php`
and a read-only JSON endpoint at `handlers/recovered_history.php`. They use a
sanitized, pinned export of the separately versioned history archive. Neither
route loads account configuration, SQL credentials or an upstream transport.
The main quote feed, portfolio valuations and prediction execution are unchanged.
This is a local review surface; it is not deployed or production-approved.

The initial export covers **81 stocks and MASI /57,825 observations**, through
2026-10-23. Actual capture dates are shown separately. Original observation
times remain UNKNOWN. The page says “Not live” and “Last recorded close”, rather
than presenting a recovered historical value as today's quote.

## Data behavior

- All close strings remain exact. Numeric conversion is limited to chart drawing.
- All 35 duplicate instrument/date keys and four conflicting-close instrument/date keys survive as
  separate candidates. Such dates have no selected plot value and split the line.
- Original source OHLC inconsistencies remain as warnings, with affected recent
  records labeled “Daily range needs review”. They are not silently corrected.
- An empty range remains empty. No last-known price is inserted into a missing
  current session. Economic calendar dates are not invented or certified.
- The endpoint requires an explicit symbol for date filters and accepts only
  `symbol`, `from`, `through`. Unknown instruments and invalid ranges return 400;
  non-GET methods return 405. Disabled or invalid configuration returns 503.
- Responses include generic history metadata and source-record hashes only.
  Raw envelopes, native bindings, provider identities, file paths and credentials
  are excluded. The original archive remains private with unchanged grants.

`daily-close-preview-v1` is a presentation contract. It does not grant source
authority, certify a live closing session or permit production model execution.

## Generate and review locally

Use a new output directory and receipt. The optional remote check below verifies
every archived value/raw byte through a TLS READ ONLY connection before exporting.

```bash
python3 tools/export_history_preview.py \
  --bundle PRIVATE_VERIFIED_BUNDLE \
  --bundle-sha256 VERIFIED_BUNDLE_HASH \
  --output NEW_EXPORT_DIRECTORY \
  --receipt NEW_RECEIPT \
  --verify-remote

python3 tools/serve_history_preview.py \
  --directory NEW_EXPORT_DIRECTORY \
  --manifest-sha256 VERIFIED_MANIFEST_HASH
```

The foreground preview listens on `127.0.0.1:8943`; stop it with Ctrl+C. Its
router serves only the preview, history endpoint and stylesheet, returning404
for every other project path. The launcher passes only ordinary locale/runtime
settings and the pinned sanitized export to PHP. Backend credentials are not
inherited. It installs no service or schedule and deploys nothing.

Direct application hosting requires both `MYINTERPRETER_HISTORY_PREVIEW_DIR`
and `MYINTERPRETER_HISTORY_PREVIEW_SHA256`; without them the feature is disabled.
The immutable manifest pins every series file. Paths escaping the export
directory, altered content and unexpected private fields are rejected. Future
hosting must place private source evidence outside any served tree. Do not
publish a research directory or grant the web process access to raw credentials.

## Verification and remaining integration

Evidence, screenshots, manifest pin and local launch command are under
`private/prediction-replacement/history-preview-20261026/`.
The full export was checked against Supabase read-only, and the PHP reader
compared every point for all 82 instruments with the pinned export. Browser checks
covered desktop/mobile layout, chart gaps, empty current-day range, local-only
resources, API statuses and blocked private paths. **19 preview tests passed**. Unit/regression tests are
`tests/test_history_preview.py`; PHP syntax and Python format/lint/compilation
were checked. No new numerical pipeline regression release is claimed.

The preview is deliberately separate from the existing main pages and Flutter
screens. A reviewed application cutover, mobile consumer, incremental future
persistence, current closing-session evidence and independent technical acceptance
remain necessary. No public API configuration, remote grant, deployment, schedule
or production activation was changed. Owner source-use authorization remains
supplied; source identities stay private.

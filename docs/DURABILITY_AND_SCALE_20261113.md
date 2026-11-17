# Durability and scale improvements — November 13

## Deployed behavior

- Website serves explicitly dated recorded prices when recent quote/application fields expire or become unavailable. Current quote expiry and ratio validation remain in force. Recorded references do not become trade execution prices or saved valuation authority.
- Mobile implements the same dated fallback with local search, one bounded reference request per fallback state and lazy list rendering. Refresh can return to recent quotes. No per-keystroke network queries or periodic polling added. Response reads are bounded at 500; this covers the present universe, not an assertion of unlimited pagination capacity.
- Website publication changed only core/market_preview_panel.php and new core/recorded_market_panel.php. Private backups and exact remote-byte readback verified. Signed-in browser confirmed 83 recorded-reference cards and absence of the old unavailable-screen message after quote expiry.
- Full screener RPC now works in a genuinely read-only transaction. Feed readers and nested reference helper validate existing evidence/policy directly rather than acquiring writer locks and renewing writer leases. Disabled-policy and unauthenticated reads rejected in rollback tests. Writer admission and evidence limits remain separate.
- Verified reference heads are incrementally maintained by source-report insertion triggers, with source foreign keys and private/RLS-protected storage. Reads consider company heads and legacy references, rather than re-expanding the lifetime of JSON reports. Old reports cannot replace newer heads. Existing reports and financial valuations remain intact. Source deletion invalidates dependent heads through cascading foreign keys.
- Authenticated, uncached publisher preflight returns its trusted worker commit. Official reviewer checks it before independent report fetch/signing and gives OFFICIAL_REVIEW_DEPLOYMENT_MISMATCH for drift. This detects drift early; deployments still must update the trust pin atomically. It does not automatically approve arbitrary new commits.

## Verification and versions

- All 121 Flutter tests passed; analyzer clean.
- PHP fast suite: all applicable suites passed, including dated fallback rendering and unsafe/future record rejection; legacy live-backend suite skipped.
- Twenty official-close tests and five publisher tests passed, including authenticated read-only deployment preflight and rejection of forged financial authority.
- Live authenticated publisher preflight matched backend commit fa684bc448601338a027d316262d75944ae2593e.
- Reference migration matched all 83 existing output records exactly. One measured database read changed from 134.59 ms to 54.00 ms including client overhead; this is a single check, not a load benchmark or p95 claim.
- Mobile commit a83d869c54ad6f4f2249e26c56e159cd5a5a69ce, isolated branch fix/mobile-dated-market-fallback-20261113, successful GitHub APK build 43513008762.
- APK: private/durable-fallback-20261113/apk/app-release/app-release.apk, 55,305,938 bytes, SHA256 34a343de12ea2cf02709d14f347dc89c8b3af28749756a3209d8430b39858c8e. New APK not installed or tested on physical phone during this turn.
- Root worktree was not committed or published wholesale. Other model changes preserved.

## Remaining operations and limits

- Missing upstream quotes remain explicitly missing; fallback availability does not establish complete fresh quote coverage.
- November 10–11 historical reports are retained but historical batch/valuation ingestion remains outstanding.
- Today's late official-close review succeeded, but eligible valuation recording returned OUTSIDE_WINDOW in dry-run tests. No timestamps were falsified; explicit late/backfill valuation handling remains to be designed and validated.
- Checkpoint artifacts still depend on GitHub availability. This change does not implement an alternative durable state store or prove sustained high-concurrency load capacity.
- Application datasets remain company-count bounded for current reads, but report/archive retention and hosting capacity still require monitoring as history grows.

# Migration review follow-up — 2026-11-04

This note records a local review, not a production acceptance certificate.

- Mobile now calls read_latest_price_references_v1 and has adapter regression
  coverage. Concurrent mobile work was left untouched; device/deployment parity
  was not verified here.
- Read-only web /auth/v1/user validation now has a 3-second connection and
  5-second total timeout. Writes retain their original limits; no authentication
  cache or revocation delay was introduced. Temporary failures already produce 503.
- measure_storage_capacity.py now reports guard headroom and exits 2 at warning
  or blocked capacity. Defaults are the previously documented 350 MB guard and
  a 20 MB warning margin, not a claim about the currently installed guard.
  The live read-only measurement failed in this review environment. No current
  storage size or ingestion rate was established; no data was deleted.
- release_inventory.py hashes an explicit newline-separated file selection into
  a new immutable-by-convention inventory. Keep outputs private until reviewed.
  It does not establish deployed identity. For each release, retain the inventory,
  SQL installation receipts, worker commit, mobile build, non-secret flag readback,
  and hosted file readback together. Do not sweep the dirty worktree into a release.

## Outstanding production acceptance

Use one genuine eligible market session, without forcing/backdating collection:

1. Record scheduler run identity, collection time, source observation time and
   admitted batch identity; job success alone is insufficient.
2. Verify authenticated website and mobile show the admitted prices and dates.
   Verify quote expiry falls back to the same dated close on both clients.
3. Verify the official-close batch and each owner's daily valuation separately.
   Missing coverage must remain an explicit skip, never a guessed price.
4. Capture capacity before and after a representative day using --previous;
   migration/maintenance growth must not be described as ingestion rate.
5. Configure operational notification for failed collection, missing expected
   batches and capacity tool exit 2 in the active private worker workflow.
   That workflow was not changed or deployed by this review.

These checks remain open until genuine hosted evidence exists. Historical bundle
manifests should remain unchanged; they are evidence for their original releases.

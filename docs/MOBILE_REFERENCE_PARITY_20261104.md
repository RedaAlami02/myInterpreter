# Review issue 1: web/mobile price-reference parity

Implemented. Mobile `latest_prices` reads now use the same authenticated,
read-only `read_latest_price_references_v1` RPC as the deployed website. No mobile
live-display flag can select the old table as the reference source. Existing
filters, selected columns, stable ordering and pagination remain intact. Errors
propagate; no retry against the original table is allowed.

The portfolio refreshes at live-quote expiry, on foreground resume, and on a
15-minute foreground refresh interval. This picks up a closing batch
published after the last quote expired. Background timers are cancelled. Request
generations prevent an older response from replacing the latest refresh timer.
All operations reuse existing reads; trade/P&L writers are unchanged.

Acceptance:

- Shared fixture `tests/fixtures/portfolio/reference_price_parity.json` checks after
  market close, exact quote expiry, next morning and a fresh next-session quote.
- `php tests/reference_price_parity_test.php`: all four web scenarios pass.
- Flutter backend tests exercise authenticated GET routing, response projection,
  filters, ordering, 500-row pagination, no-session rejection and RPC failure with
  no old-table fallback. Both live-feed flag states use the same reference RPC.
- Widget test verifies quote expiry, a subsequently published closing reference
  while the screen remains open, and another reference fetch on next-morning resume.
- Full Flutter suite:116 passed. Analyzer: no issues.

The fixture quote is invented and never enters live storage or a genuine ledger.
These checks establish code behavior, not a successful live market session or
physical-phone acceptance. The release remains on an isolated branch; main and
production records are untouched. Install the final parity APK for this behavior;
older APKs still contain the original fallback path.

Private release/build receipts: `private/mobile-reference-parity-20261104/`.

Final release commit: `07a85071cb9a47f5f44a65b3ca667e448bc355eb` on
`fix/mobile-price-reference-parity-20261104`. Cloud APK run: `41749862195`.

Parity means the same reference contract at a given read time. A foreground
mobile screen polls every15minutes (or earlier at quote expiry); refreshing or
resuming triggers another read. Clients at different refresh times may therefore
briefly show different dated snapshots. This is not a claim of simultaneous live
prices or complete market coverage.

Final cloud build41749862195 succeeded. APK downloaded55,273,170bytes, SHA256
`2f0bf2f7baa6bb340f5f8174fa6a525ef12cd75de6bb22efd90c50e90e7f6ced`.
Artifact: `private/mobile-reference-parity-20261104/apk/app-release/app-release.apk`.
Physical installation and genuine live-session acceptance remain unverified.

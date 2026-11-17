# Price fallback integration — October 29

The old price fallback now travels through the **existing** collector/publisher,
feed RPC and PHP/Flutter feed readers in isolated tests. No additional market
tables or public endpoints were introduced. The owner-approved disabled backend
upgrade is now installed: SQL015 and publisher version 7. Source collection,
schedules and app-screen cutover remain off; no APK was built.

## Implemented

- The default v1 quote candidate is unchanged. A private publish profile may
  explicitly opt into `display_fallbacks: true`, producing a v2 candidate.
- v2 keeps the normal quote absent for an omitted stock and attaches its original
  instrument-reference price separately. Trade date/time remain unknown. Conflicts
  are explicit and cannot be hidden by a saved-price fallback.
- The publisher verifies the reference against the exact archived instrument
  identity, value, capture time, raw-row position and full positive-observation set.
  Altered values, missing available references and masked conflicts are rejected.
- Installed SQL015 upgrades only the existing private publish/read implementations.
  It checks their exact prior source hashes before patching. All v1 validation
  and retry rules remain; new helper functions are private. No tables or public
  RPCs are added. Existing trial gates and reference expiry still apply.
- PHP `ShadowMarketSnapshot.displayRowsAt()` and Dart
  `ShadowQuote.displayPriceAt()` use quote → instrument reference → explicitly
  supplied original last-known record. Original quote accessors stay null for
  reference-only stocks, preventing accidental use as a current valuation price.
  History must match company/symbol and precede the display cutoff. Reference
  prices expire independently; private backend fields are not exposed.
- The price job's original ratio calculations were ported as the pure
  `fundamental_frame.price_ratios()`. Tests execute the actual legacy calculation
  AST without importing its retired SDK. All 81 preserved company inputs match
  exactly, including 64 using the supplied market cap. This proves calculation
  parity using preserved inputs, not fresh fundamental accuracy or valuation
  authority. The helper is not yet wired to application-table publication.

## Actual verification

| Check | Result |
| --- | --- |
| Managed Python workers | 209 cases pass |
| Publisher | 18 Deno cases pass |
| SQL015 + inherited v1 behavior | 32 isolated cases pass |
| PHP reader | Syntax and v1/v2/reference/history checks pass |
| Flutter | Clean analysis; all 70 cases pass |
| Local chain | Python producer → TypeScript archive binding → SQL publish/authenticated read → PHP display passes |
| SQL result through Flutter | Exact generated SQL fixture passes the mobile reader |
| Saved genuine capture | All 17 references pass offline publisher binding with an explicitly historical virtual clock |
| Original evidence | Saved archive hash and published v1 candidate exactly unchanged |
| Original ratio rules | All 81 preserved company inputs match the legacy calculations |

SQL and local-chain checks used fresh synthetic databases on a `/tmp/` Unix
socket with TCP disabled; the chain's database was dropped afterward. No hosted
credentials or sources were used. The genuine-capture check was an offline replay,
not a second capture or live acceptance. No models, genuine ledgers, observations,
source timestamps, portfolio assignments or billing settings were modified.

The authorized independent reviewer found no blocking flaw. Independently reran
14 fallback tests, one legacy-AST parity case, 18 Deno cases and PHP checks;
inspected the SQL/Flutter receipts without another broad run. This accepts the
local implementation only, not deployment, new trial or production activation.

The first Flutter analysis found two brace-style notices; they were corrected,
then analysis and the full suite passed. One conflict test initially supplied
a price in the wrong fixture locale; corrected before the successful final runs.

## Exact release state

Private immutable package: `private/display-integration-20261029/upgrade-package/`.

- Runtime: **41 files / 339,396 bytes**; manifest SHA-256
  `c99bd6761eeb95709517b60cc4c55f871568db36a37cabd5d64600936cb4ece7`.
- Upgrade manifest SHA-256:
  `f7955ce56f4407c666a09ef514f56430de4f895af64969ac1b4b9e9cdf441ed7`.
- Additional selected SQL/reader/fixture/test files: nine. No credentials, source
  profiles, raw data or model files are included. Tests reference the project's
  existing baseline fixtures; this is not a standalone test environment.
- Completed hosted scope: SQL015 committed and **only private-app-publisher**
  updated, with every control/enable flag still off. Do not reapply SQL009–015, overwrite
  older review packages, update the other functions or repeat the consumed trial.

Fresh hosted readback verified all nine source files against the pinned packages.
Archive and projection functions remain version 6; the upgraded app publisher is
version 7. All three endpoints return their exact disabled HTTP 503 responses.
All 15 application-table fingerprints, archive/candidate/trial rows and unrelated
functions are unchanged. Anonymous exposed application relations: zero. Database:
333,436,595 bytes at this check; the protected recovery backup hash was reverified.
The original private v1 candidate is unchanged. No source requests, secret writes
or account changes occurred. **No real signed-in preview acceptance occurred**:
Auth still had zero accounts at the last account check.

Receipt: `private/display-upgrade-20261029/run-20261029T171126Z-87175b60/receipt.json`.
The first attempt stopped before mutation because deployed metadata versions had
advanced despite identical source bytes. The successful installer verified those
bytes and captured actual versions before applying the authorized delta.

## What remains before users see this

1. The disabled backend upgrade is complete. Do not repeat its approval or install.
   The consumed one-capture trial must not be repeated automatically.
2. Complete normal user-driven signup/email confirmation and a newly scoped
   signed-in acceptance. Do not invent a password/account or revive the old trial.
3. Finish getprice's application-table update behavior: ratio/full-market fields,
   latest-price persistence and original new-listing/enrichment coordination.
   The existing market screens still read the original application tables; the
   upgraded **feed readers** are ready, but screens have not switched to the feed.
   Do not claim website/mobile cutover or full getprice parity from these tests.
4. Continue the other original jobs against FUNCTION_MIGRATION_PARITY.md, then
   reviewed private scheduling and app cutover. Keep the focus on old behavior.

Private evidence: `private/display-integration-20261029/` contains SQL logs,
synthetic-chain receipts and output, Flutter logs, the labeled saved-capture replay,
and the 81-company ratio comparison. All provider identities/native bindings stay
private. No Git commit/push or release APK build occurred.

# Price job company-input repair — November 2, 2026

The user resumed the main website/mobile/automation migration. Prediction work
remains excluded. The email routing server setting is still pending; see
`AUTH_REDIRECT_FIX_20261102.md`. No Appwrite access occurred.

## Fixed

The full price job previously loaded saved company inputs through the separate
enrichment publisher and its fundamental-provider index/lease. That made price
collection depend on enabling a different provider/service. New cloud price jobs
now read these inputs through their own existing price publisher and quote lease.
The explicit legacy `--company-index` mode remains supported; a failed new read
never silently falls back to it. Explicit local snapshots remain supported too.

Additive SQL025 supplies `read_price_company_context`, a service-only read RPC.
It requires the same quote lease with archive, shadow-feed and projection
capabilities; all existing archive/provider/feed/application controls; and the
exact approved provider, mapping-document/hash, recipe and application-field pins.
Current company ID/name/symbol mappings must agree. The old SQL functions, bodies,
ACLs and data are preserved. The endpoint has a separate default-off
`APP_PRICE_CONTEXT_ENABLED` switch behind the existing publisher authentication.

Only nine allowlisted company fields are returned. There are no portfolio/Auth
joins or raw-response disclosures. Original company dates and actual accepted
fundamental availability timestamps remain separate from retrieval time. The
response is bounded and identity-checked in SQL, the managed function and Python.
The exact context is stored with a pending quote job; retries do not fetch newer
fundamentals or change its prepared prices/cutoffs. Model and valuation authority
remain unchanged; application publication remains shadow-only.

## Installation and verification

- SQL025 installed; existing price-publisher function updated and exact source
  bytes read back. It acknowledged deployment version 14 at installation.
  Use source hashes/fresh metadata rather than assuming this counter stays fixed.
- A fresh 55,682,351-byte custom backup was created and every stream decoded.
  SHA-256: `cd834f13a69ad4e1368a5b10d6c172a2fb005be9a22c84b970e21aa5cc874285`.
  Auth/platform schemas are excluded; this is not a full restore drill.
- Backup and immutable installation-plan pin:
  `5780259c54c5591d002f0b926515b0145b994ce6d77ab30261b0e33a71649d59`.
- Database size at post-install verification: 334,419,635 bytes.
- All existing public table values, original 55 private source records, legacy
  routines and anonymous application-access restrictions verified unchanged.

Initial deployment stopped after SQL commit because the private installer
expected old version metadata 8; actual metadata was 13 while the hosted source
still matched the exact accepted old source. That partial receipt/error was
preserved. The resume verified the installed SQL body/ACLs, source bytes and
disabled controls, then completed only the function update. SQL was not repeated.

## Genuine hosted read acceptance

A separate new bounded read plan, not the consumed original quote trial, passed:

- **81 mapped company inputs** returned through the deployed endpoint.
- Genuine retrieval time: `2026-11-02T19:29:24.025375+00:00`.
- The separate enrichment service remained disabled/unnecessary.
- Zero upstream requests, raw objects, market publications or financial writes.
  Archive object count stayed 2.
- Exact original provider/control state restored, the new lease revoked and
  three temporary caller/settings secrets removed. Disabled endpoint verified.
- All 55 original private records and existing public table contents reverified.
- Context SHA-256: `e08a71b46f8cd029a51369bf03eb5a2f25cf4343b7f420e6a480d8b56c2af6fd`.
- Read-plan pin: `a441bf0f15f43c92a8970a156cc2dd3250670d4533a1170aeee262d271eab78f`.

These are saved **company inputs**, not 81 fresh stock-price observations.
This proves the scoped live read and cleanup, not full-market acquisition,
official-close authority, unattended scheduling or production readiness.

Independent review caught provider-state restoration and busy-revocation risks
in the private acceptance runner before it executed. Both were fixed: exact
provider restoration, bounded gate-contention retries and separately committed
revocation before restoration. Two isolated cleanup tests pass.

## Worker release and tests

Private worker commit: `15e41fe9784047a32701124d81a8ce894688d59b`.
71 payload files plus manifest verified; ten unrelated reference files preserved.
Distribution pin: `1b26a6459f25b3fb8f2da2c32c1951e03404dd436e475174454018379b9e1c28`.
Private cloud run **41509809499 succeeded**:

- 232 standalone Python tests; 24 archive and 42 publisher-boundary Deno tests.
- Six synthetic queues uploaded/downloaded/restored exactly; synthetic artifact
  removed; zero repository artifacts remained at verification.
- No source credentials published, source requests or enabled schedules.

Main managed Python suite: **327 passed**. Isolated SQL: **64 passed**, including
58 inherited regressions. Price publisher: **27 Deno tests/typecheck passed**.
Independent review reran the 64 SQL, 27 Deno and 17 focused Python tests.
Three distribution-boundary tests also passed.

The first local package verification failed because its inherited private umask
made a supposedly unsafe test directory safe. The fixture now explicitly sets
the unsafe permissions it intends to test. Production permission checks were
not weakened. The failed package/log remain preserved; a new immutable v2 package
passed all 232 standalone tests under umask 077 before publication.

## Remaining work

1. Verify remaining acquisition/publication kinds from the intended hosted runner
   under separately bounded plans; this read test does not substitute for them.
2. Finish/review recurring policy, lease lifecycle, retention and actual shared
   free compute/storage allowance. No schedules are enabled and no full allowance
   is inferred from synthetic-run success.
   A local configuration check also found cadence drift to resolve explicitly:
   the original depth cron is `*/5 8-15 * * 1-5`, while the replacement's current
   gate permits only the first 15 minutes of each hour and uses hourly slots.
   Original dividend cron is `0 6 * * 1`, while the current worker gate uses a
   Friday evening window. Do not describe these as equivalent or activate them
   without reconciling the original cadence, timezone and free-budget requirements.
   Raw configured schedules were inventoried without contacting the retired service
   in `private/main-fixes-20261102/legacy-schedule-inventory.json`.
3. Verify official closing-price/session evidence before enabling saved daily P&L.
4. Complete pending Auth redirect configuration, real email/second-account/device
   acceptance. Existing source authority is supplied; do not request it again.

Private evidence: `private/main-fixes-20261102/`, including the immutable review
bundle, backup, partial/resumed install receipts, failed/successful package logs,
cloud receipt and `context-acceptance/receipt.json`. Preserve these records and
the unrelated dirty main worktree. The main repository was not committed/pushed.

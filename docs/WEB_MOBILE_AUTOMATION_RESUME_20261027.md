# Latest paused handoff — October 27 evening continuation

Implementation is **paused at the owner's request**. Resume only when asked.
This is the newest checkpoint; read it before
[the earlier handoff](WEB_MOBILE_AUTOMATION_HANDOFF.md).

The priority remains website, phone and private managed app automation before
prediction work. Never reconnect to Appwrite. Preserve the original recovery,
private ownership/timestamps, genuine ledgers, frozen models and unrelated WIP.
No provider names/domains/native field aliases may enter public files or pushes.

Private evidence and native configuration:
`private/app-resume-20261027T192358Z/`. Also read that directory's `HANDOFF.md`.
Never print or publish its configuration/raw files. Both real-user email mappings
remain in the earlier ignored account record, with implementation deferred.

## Completed this continuation

### Updated keys, privacy and clients

The saved publishable and server keys initially failed with **Unregistered API
key**. SQL connectivity and private database grants still worked; this was not
evidence of a newly exposed database. The owner replaced the keys locally.
Both updated keys then passed read-only API checks; PostgreSQL TLS/read-only
checks also passed. No credentials were printed or uploaded to GitHub.

- Fresh privacy verification **passed** with valid credentials: all 15 app tables
  reject anonymous reads, owner policies/RLS remain intact, no public Storage
  buckets, no anonymous recovery access and no exposed internal REST schemas.
- The verifier now checks API-key acceptance first. Invalid keys/outages cannot
  be misreported as proof of private data access. SQL and API results are separate;
  new receipts do not overwrite earlier receipts. Five regressions passed.
- Web public-key refresh is explicit, atomic and preserves the administrator.
  It refuses project/configuration-shape changes. Five writer tests passed.
- Local PHP and Flutter public runtime configurations now use the new publishable
  key. The migration/admin keys are not client configuration.
- Live PHP Auth/trade integration passed with the new keys: login/refresh/logout,
  CSRF/cookies, authenticated market reads, owner isolation, exactly-once retry
  and concurrent oversell prevention. Temporary confirmed users were deleted;
  no signup email or real-user assignment occurred.
- Debug APK rebuilt successfully against the new public key. The old APK's key
  was retired; use the new artifact only after the remaining checks below.

**New debug APK:** `myinterpreter_app/build/app/outputs/flutter-apk/app-debug.apk`

- 192,654,818 bytes.
- SHA-256: `a393474b317f68f48152903618f62761628a94148f18c4e164c39062f09be018`.
- Debug only; no release build or deployment.
- Fresh APK secret-literal rescan and real-device validation are **pending**.
- Actual mobile SDK integration passed in the previous continuation; it was not
  rerun after this key rotation. The current PHP live test and key checks passed.

### Versioned market normalization and local archival

Added `automation/managed/market_frame.py` and `market_collect.py`.

- Separates instrument references, stock quotes, index observations and market
  status. A catalog/reference price is never silently inserted as a missing quote.
- Parses numeric formats explicitly with Decimal, preserves raw bytes and SHA-256,
  rejects invalid/zero prices, duplicates/conflicts, stale/future source dates,
  wrong index identity and incomplete expected-universe coverage.
- Retains naive source timestamps verbatim with **UNKNOWN timezone**; source clock
  text never becomes UTC merely because the HTTP receipt has a timezone.
- Preserves actual capture time separately. Observation identities depend on the
  source namespace, raw capture and physical row, not ticker/date alone. They
  remain stable across replay processing times; duplicate physical rows remain
  distinct and conflicts are flagged.
- Recorded replay requires a verified raw hash and receipt and can initialize
  only isolated SQLite storage. It cannot connect to the live database.
- All output remains UNPROMOTED, prediction-ineligible and valuation-ineligible.
  A COMPLETE frame does not confer source/closing-price authority.

**Actual recorded-response verification:** the saved original body/receipt hash
matched; normalization preserved 81 references, 66 same-date detailed stock quotes,
one MASI observation and one status record. Fifteen detailed quotes are absent.
The archived replay correctly returned **INCOMPLETE**, with those gaps explicit.
The compressed envelope was 18,158 bytes. Original receipt time was preserved,
not replaced with this replay's processing time. This is not a forward capture.

### Order-book normalization, manifests and bounded collection

Added `automation/managed/depth_frame.py` and `depth_collect.py`.

- Reuses the existing authorized request builder through private request templates;
  native request/response paths stay in ignored configuration.
- Binds responses to requested securities, retains source level order and clock
  text, handles zero/null empty placeholders, and flags malformed quantities,
  crossed or unordered books without inventing replacements.
- Produces batch manifests with explicit expected, attempted, missing, failed,
  duplicate and unexpected captures. Raw hashes, actual receive times and source
  observation identity are preserved.
- Normal collection enforces its window/logical slot even when called directly.
  Diagnostic mode is explicit; neither path grants prediction authority.
- New/archive data was stored **only in isolated local files**, not live Supabase.

**Real diagnostics, not active market-session capture:**

| Check | Observed result |
| --- | --- |
| Single after-hours request | HTTP success; correct security; 5 bids and 5 asks; source timezone unknown |
| Bounded full-universe diagnostic | 81 expected, 81 attempted, **81 raw responses preserved** |
| Successfully normalized snapshots | **66 complete snapshots** |
| Other 15 responses | `INVALID_NUMBER`; exact field/reason not yet investigated |
| Overall batch | **INCOMPLETE**; no quotes/snapshots fabricated |
| Elapsed local time | **69.92 seconds**, including the existing 0.5-second pacing |
| Raw entity-body bytes | 144,811 |
| Compressed complete envelope | **48,567 bytes** |

All 81 raw responses, including the 15 that failed normalization, are preserved
inside the private compressed diagnostic envelope. **Do not recollect or treat
those 15 as lost.** Inspect the saved bodies first; do not suppress INVALID_NUMBER
just to obtain COMPLETE. Their overlap with the missing 15 market quotes was not
established. The new snapshots are after-hours diagnostics, not additions to the
original cloud-history or genuine forward-capture counts.

### Tests

**74 worker tests passed**, including the prior 21 cases and the new market/depth
normalization, collection, replay, archive/restart and window checks. The privacy
verifier's five tests and web config writer's five tests also passed.

No new Stage 1–2D/prediction-model test run or production acceptance is claimed.
No source/authority promotion, historical rewrite, retraining or ledger write
occurred. No live SQL schema/role was installed in this continuation.

## Free-tier findings: measured, with limits

The existing GitHub Pro plan/budget analysis still applies: 3,000 included private
minutes; proposed 1,882 total planning minutes including a manual reserve; exact
remaining account usage unknown; $0 extra-spend cap unchanged. No new cloud jobs,
private-package pushes or recurring schedules ran in this continuation.

The measured 69.92-second depth batch is a **local after-hours** timing, not a
cloud/daytime guarantee or proof that dependency setup plus quote/depth collection
fits the proposed two-minute job. A cloud benchmark remains necessary.

Using these two single-sample compressed envelope sizes and the proposed cadence
would imply about **22.3 MB/month before PostgreSQL overhead or other growth**.
This is an illustration, not a production storage forecast. The last connected
DB size was 332,732,083 bytes; the draft 350 MB archive guard leaves about 17.3 MB.
A bounded private raw-data archive/capacity policy is needed before continuous
activation. Do not silently delete original evidence or raise guards automatically.
Prefer separating raw object archives from compact queryable app data once the
platform quota and least-privilege upload path are actually verified.

## Exact next steps

1. Resume from this checkpoint and inspect git/private evidence. All changes in
   this continuation are **uncommitted**; no main or private-worker push occurred.
   Preserve all unrelated WIP and source evidence. The earlier private repository
   still has its older eight-file package; current new modules/tests are not there.
2. Finish the fresh APK secret-literal check and actual mobile SDK test with the
   rotated key, then device validation when available. Do not reuse the old key/hash.
3. Diagnose the 15 depth `INVALID_NUMBER` cases from the saved raw batch and decide
   the correct explicit missing/format policy. Compare identities with the missing
   stock quotes privately; do not assume they are identical or fill unavailable data.
4. Finish normalizer/spec validation and actual collector integration. Existing
   GitHub collection YAML still invokes the old generic worker; wire the new
   market/depth entry points and per-job configurations explicitly, after review.
   Retain source clocks as UNKNOWN unless evidence establishes their timezone.
5. Review/synchronize only the generic private worker package, excluding all native
   profiles/raw data, emails and keys. Configure source recipes as encrypted secrets
   only. No Supabase admin/secret/database URI belongs in the worker repository.
6. Run an explicitly identified private-cloud normalization/timing test. Existing
   earlier cloud reachability passed, but these new batch collectors have been
   tested locally only. Keep schedules and production collection disabled.
7. Finish fundamentals/dividend adapters, status/health handling, separate app quote
   projections and ratio logic; implement bounded daily valuation and maintenance
   without broad worker access to private accounts. Preserve recovered originals.
8. SQL007 is still a draft, not installed live. Audit current ownership/capacity,
   review/test the narrow role and immutable archive boundary, and design raw
   retention/export before activation. New normalized app feeds are not live yet.
9. SMTP is still UNKNOWN; the owner previously answered “Not sure.” Public/secret
   project API keys do not grant Management access to SMTP settings. No real inbox
   delivery test ran. Keep email confirmation enabled and prepare callback/reset
   flows; do not claim real public signup delivery works yet.
10. Review/test the exact web/APK cutover set, then activate only after required
    technical/permission gates. No website deployment, release APK or schedule
    activation has happened in this continuation.
11. Owner-deferred account assignment remains deferred. Both emails are recorded
    privately. Later require confirmed ownership of the matching email and a newly
    chosen password; never guess or reuse an unverified old password.
12. After current migration work is complete, research and move/de-emphasize the
    rare owner-only Société/MAJ navigation item. No navigation redesign occurred.

Both running operations finished before pause documentation: the diagnostic
archived its raw responses and the Auth test deleted its temporary users. No new
background collection or test server remains from this continuation. No local
PostgreSQL server was started. Temporary formatter/helper files may disappear;
important helpers/profiles/results were copied into the ignored evidence folder.

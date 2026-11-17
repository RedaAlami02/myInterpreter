# Application quote/index preview — October 28 continuation

Read after `PRIVATE_ARCHIVE_GATEWAY_HANDOFF.md`. Exact private evidence and scripts
are in `private/app-feed-20261028T194844Z/HANDOFF.md`. App work remains ahead of
prediction work; real account assignment and owner navigation redesign stay deferred.

## Implemented and tested

- `automation/managed/app_feed.py` verifies the original gzip bytes/hash, raw capture
  and normalized values using the private recipe before deriving a separate
  `app-market-candidate/v1`. Prices remain exact decimal strings. No catalog/book
  fallback, index averaging, arbitrary conflict selection or source timezone guess.
- Exact mapping verification passed for **81 original companies / 81 formats**;
  every format name matches a company and its symbol matches the expected universe.
  MASI has a separate explicit index mapping. Files and manifests were checked.
- A legacy-ID compatibility option accepts only recorded replay archives whose
  missing fields are derived capture/observation IDs. All price/time/coverage fields
  must still match. Derivation is declared; no original archive is changed and
  current acquisitions cannot use this bridge.
- `tools/prepare_app_feed.py` has no remote-write option; outputs must stay private.
  Isolated SQLite stores only the latest candidate per allowlisted provider,
  with retry, older-capture rejection and equal-time conflict detection.
- Draft **SQL010** stores bounded shadow candidates against verified SQL009 archive
  references, exact current company mappings and pinned recipe/mapping hashes.
  Publishing is service-only; reading requires a verified signed-in subject.
  Native IDs, raw hashes/observations and source bindings are excluded from reads.
- Read-time checks withhold expired/future prices and missing archived evidence.
  Expiry is capped by capture age, source-event age and the next market-day boundary.
  Global/source disablement and missing snapshots have explicit empty responses.
- New PHP and Flutter readers consume only `app-market-preview/v1`, preserve
  decimal text, filter private properties and expire cached prices. They do not
  convert previews to legacy documents or update holdings/P&L/predictions.
- `automation/app-publisher/` is the staged trusted publisher the worker token
  could not provide. It accepts only a canonical candidate, its exact hash-pinned
  mapping and both hashes over a separate `app_publish_` token; re-reads the exact
  archived object by digest; requires the archive contract, receipt time,
  completeness and frame date to agree; and requires every submitted observation
  (identity, decimal text, receipt time, row index) to equal the stored frame, with
  no dropped or shared observations. Only then does it call the service-only
  publication RPC with the key held inside the function.
- `automation/managed/app_publish.py` builds that candidate with `app_feed.build`
  and refuses replays, legacy-ID derivations, unpinned mapping/recipe, and local
  isolated stores. `market_collect.py --publish-profile` publishes right after an
  archive save in the same managed run; `run_collection.py quotes` forwards it.
  Both the function and SQL010 remain **not installed**; the publish token and
  private profile are not provisioned.

**Actual preserved-response test:** 81 stocks + MASI. At the original receipt:
67 reported values, including MASI, and 15 missing stock quotes. At the current
cutoff: **67 stale captures / 15 missing quotes / zero current display prices**.
The original archive's SHA-256 stayed identical. Source execution remains recorded
replay, timezone UNKNOWN, newly derived identities explicitly labeled.

## Verification

| Check | Result |
| --- | --- |
| Local managed worker suite | **130 passed**, including 15 app-feed and 14 publisher cases |
| Publisher boundary | **15 Deno cases passed**; Python-to-Deno loopback integration passed |
| New SQL010 integration | **13 passed** in isolated PostgreSQL |
| Existing archive SQL/concurrency | **25 passed**, unchanged code |
| Flutter analysis | Clean |
| Full Flutter test suite | **42 passed**, including seven preview-reader cases |
| PHP reader | Syntax and focused checks passed, using shared synthetic decimal/expiry fixtures |
| Private cloud | **116 worker + 19 gateway passed**; 38 SQL cases explicitly skipped there |
| Private publication | **39 generic files pushed; all remote hashes verified** |

The first Flutter analysis found three missing-brace lint issues; those were fixed
and clean analysis/full tests passed. Formatting changed only the two new Dart
files. The Snap SDK required execution outside the sandbox; no live service was
used by Flutter tests. No release build or new APK was produced.

The private publication includes generic worker/SQL code and tests, not the PHP/
Flutter runtime files, native mappings, data or credentials. Main project changes
remain uncommitted. Existing recovered application tables and active readers were
not changed. No Appwrite/source requests, live SQL, schema/function deployment,
collection activation, emails, owner assignment or genuine-ledger/model writes.

## Exact remaining work

1. Independent review and the previously documented deployment/Management/quota/
   outbox-fallback gates. SQL009/010, the gateway and the publisher are still **not
   installed**. This API is not available on the hosted project yet; localhost/
   fixture checks do not prove hosted REST/storage acceptance.
2. Provision the independent `app_publish_` token, the private publish profile
   (mapping plus approved pins) and the publisher function; verify hosted denial,
   error shapes, read-back, quota, expiry and current-session timing before a manual
   trial. Do not reuse the archive token or give CI a privileged key.
3. Wire an explicitly enabled preview into website/mobile only after installation
   and review. Existing `data`/`latest_prices` consumers remain separate. No active
   page or portfolio valuation has been switched. AVAILABLE means the preview
   snapshot exists; individual quote status/expiry still controls display.
4. Finish fundamental/dividend adapters, owner company writers, daily portfolio
   valuation and maintenance. Every preview remains SHADOW_ONLY and valuation/
   prediction-ineligible; date-only clock evidence is not a verified event time.
5. Complete SMTP delivery, confirmation/reset/callback handling, physical-device
   validation and reviewed web/APK cutover. Deferred accounts/navigation remain so.

Latest-row storage bounds logical records, not PostgreSQL physical growth. TOAST,
MVCC, metadata and indexes still require measurement/maintenance and the existing
capacity guards. Do not infer long-term free-tier sufficiency from row counts.

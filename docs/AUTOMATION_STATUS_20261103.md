# Application automation status — November 3, 2026

Regular collection and official-close collection/review are enabled. This concerns
application data and portfolios; prediction execution remains outside this work.

| Job | Configured Casablanca window | Verified so far |
|---|---|---|
| Quote collection | Weekdays 09:00–17:00, 15-minute slots | Original collectors/fallbacks reused; hosted live-session proof pending |
| Order books | Weekdays 09:00–17:00, 5-minute slots | Original collector reused; hosted live-session proof pending |
| Dividends | Monday 07:00–08:00 | Existing collector/projection retained; next scheduled source cycle pending |
| Company information | Weekdays 17:00–19:00 | Genuine hosted collection, raw archive and projection succeeded |
| Official closes and daily valuation | Weekdays 17:35–19:00 | Source reachable; independent verifier tested; first eligible hosted cycle pending |

The private runner wakes every five minutes between 08:00 and 18:55 UTC on
weekdays, plus Monday 06:05/07:05 UTC. A versioned Casablanca-time dispatcher
selects due work; additional wakes do not force collection outside these windows.
GitHub schedules can start late. Readiness and source-age gates fail closed.
No always-on personal computer is required.

## Deployed and verified

- SQL026/027 regular acquisition/publication and SQL028 official-close automation
  are installed. Existing data and all 55 original private recovery records were
  reverified. Separate database backups were hash-checked and fully decoded.
- Four managed boundaries are deployed. Exact deployed bytes were checked. The
  archive gateway additionally supports bounded official-acceptance lookup.
- Private worker commit `b1ed0f5e32d170af151abb20fcc4295bad563bae`, distribution
  `874f195e2ea632d29c3e75548dbb39c5e21e5c252f5e86c62f9dde6a83995516`:
  all 91 selected Git blobs verified; 10 unselected files preserved.
- Hosted verification `41703417398` succeeded, including actual PDF dependency
  installation, synthetic worker and boundary tests and artifact roundtrip.
- Genuine upgraded checkpoint run `41704611961` succeeded after hours. It restored
  the previous live checkpoint and persisted/read back its successor. This is
  recovery evidence, not proof of a new market capture.
- All five regular/official switches were read back as enabled. Official source,
  parser and identity pins match the approved private configuration.
- Website current-price cutover was published and read back earlier this session.
  Only same-day, unexpired observed quotes overlay historical reference prices.
- Mobile recurring-reader integration passed 106 Flutter tests and analysis.
  Its separate branch is `fix/mobile-recurring-market-20261103`, commit
  `4d451d2b608f9cacc7076d77ae19ca4212e69219`; cloud build **41704803678
  succeeded**. APK downloaded and SHA256 verified:
  `0e63fe62950b2b91da8689d939b40a75e027935def186e1a3b9aa66f2284d990`
  (54,306,286 bytes). Physical-device acceptance remains pending.

## Financial and recovery guarantees

The collector never receives the financial caller token or signing key. Those
credentials reside in a separate GitHub environment restricted to the default
branch. The verifier independently downloads the approved report with verified
TLS, reparses its exact PDF bytes, compares mapped prices and signs a short-lived
attestation bound to the report, parser, policy, identities and reviewed commit.
The server checks the signature before its bounded financial RPC can run.

The owner-controlled master switch is never rearmed by report processing. Control
initialization v2 permits a pinned, enabled source with no first batch: the
unchanged valuation function returns PRICE_UNAVAILABLE and writes nothing until
a real approved batch exists. The batch foreign key remains intact.

Existing owner/day records are never overwritten. Source timestamps remain actual;
unknown publication/close clocks remain unknown. Valuations use holdings at
execution and only verified official prices in the original 17:00–19:00 window.
Missing company coverage skips that owner's valuation. No quote/reference fallback
can become an official close. No valuation was created during installation.

Checkpoint v4 preserves restoration of original v1/v2/eight-channel v3 manifests.
Individual receipt compaction retains exact original bytes, including more than
64 official sessions. Quarantine queues retain failed intents and fail closed at
their bounded capacity; no automatic destructive retention was enabled.

## Tests and measured limits

- Full managed Python suite: **356 passed**; standalone hosted subset: **261**.
- Official/recurring SQL regression suite: **84 passed** in fresh isolated local
  PostgreSQL; independently rerun by the reviewer.
- Financial boundary: **4 passed**; existing boundaries: **69 passed** locally.
- Distribution/security checks: **5 passed**; public mobile config: **7 passed**.
- Flutter: **106 passed**, analyzer clean.
- Read-only capacity: **334,968,499 bytes** of database; **15,031,501 bytes** before
  the stricter 350 MB application stop. Raw private storage: **36,831 bytes** across
  three objects. Database growth since the prior snapshot: **516,096 bytes** over
  about 23.2 hours, including migrations. This is not a daily ingestion rate.
- Shared artifact inventory and conservative checkpoint reserve were checked;
  current shared compute credit cannot be read. The owner's zero-dollar spending
  stop remains unchanged. Free operation is bounded, not promised indefinitely.

## Remaining evidence and work

1. Observe a genuine scheduled quote/depth session and its published coverage.
   Display readiness must not call unknown-date reference prices current quotes.
2. Observe the first hosted official-report archive, independent review and
   eligible daily valuation. Today's genuine report (80 securities, 77 closes)
   was fetched at 19:23 UTC, outside the execution window; it was preserved
   privately and never used to backdate a valuation.
3. Current read-only coverage check: **13 of 14 holding rows** have mapped
   official closes; **one of two portfolios** has complete coverage. The other
   is deliberately skipped while its missing holding lacks an official close.
   Investigate unmatched identities using evidence, never guessed price bindings.
4. Measure representative full-day database, storage, duration and artifact growth;
   review bounded quarantine capacity and a nondestructive archival/retention plan.
5. Install and physically check the latest APK. Mobile portfolio current-quote
   parity is implemented and passed111tests; physical installation awaits approval.

Detailed private receipts are in `private/complete-automation-20261102/`. Credentials,
source identities and raw upstream evidence must remain private. No Appwrite
request or prediction-model work is required by the deployed application jobs.

## Late follow-up

Mobile portfolio quote overlays are implemented: same-day current company quotes,
expiry back to dated references, conflict rejection and suppressed mixed-date totals.
Dates use IANA Casablanca rules independently of the device timezone. All111Flutter
tests and analysis pass. Cloud build41742171126 succeeded from isolated branch
`fix/mobile-portfolio-quotes-20261103`, commit0f25ebbdc45afcbbbbc339fde394364ccc152aca.
APK55,256,786bytes, SHA256d22317a3e1990f0d2e4d7445e07366d87699962faa370f8689094501290ca614.
No main-branch merge or physical installation was performed.

Fresh read-only backend verification23:51UTC: all six backend controls and five
GitHub switches ON, four valid source policies,55original records verified,
zero official batches/valuations and database334,968,499bytes. The next eligible
market session remains necessary for live acceptance. Searching16local files found
170related records for the missing holding, with no ISIN or OFFICIAL_CLOSE evidence;
these do not justify inventing a current official price.

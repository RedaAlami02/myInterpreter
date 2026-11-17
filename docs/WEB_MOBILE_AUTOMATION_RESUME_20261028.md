# Website, mobile and private automation — October 28 continuation

Read this before the October 27 checkpoints. Current private receipts and revised
depth configuration are in `private/app-resume-20261028T183324Z/`; that directory's
`HANDOFF.md` records the exact evidence paths. Do not publish private files.

## Progress estimate

Approximately **70% complete / 30% remaining** for the website, phone app and
replacement app automation. This is a planning estimate based on tested
capabilities, not a measured percentage or a production-readiness claim. Prediction
model work is separate and remains deferred.

The major completed foundations are recovered data, private database access,
Supabase web/mobile sessions and trades, and tested independent acquisition code.
The largest remaining work is turning acquisition into a bounded, operational
application feed with email delivery and a verified deployment.

## Completed and verified this continuation

| Area | Confirmed result | Limit |
| --- | --- | --- |
| Actual mobile SDK, updated keys | Login, authenticated/anonymous access checks, owner isolation, trades, retries, session restoration and logout passed; temporary accounts deleted | No email sent; physical device validation remains |
| Existing rebuilt debug APK | Hash verified; 546 decompressed entries scanned against four known sensitive literals and secret-key patterns; no hits | Known-literal scan cannot establish absence of all unknown/transformed secrets |
| Saved depth diagnostic | All 81 original raw responses hash verified and normalized into 81 complete book frames; three books empty | Reprocessed after-hours evidence, not new live sessions or predictions |
| Missing last-trade summaries | All 15 previous parse failures were empty strings in an optional summary field; revised private recipe explicitly retains null | No last-trade prices invented; malformed nonblank numbers remain errors |
| Quote coverage comparison | Those same 15 identities are missing from the preserved detailed quote response | Detailed market quote frame remains INCOMPLETE; complete books do not fill quotes |
| Batch manifest | Failed normalization now preserves the raw response hash, receipt time and error code in the draft v2 manifest | Earlier archive/manifests unchanged; raw bytes remain preserved separately |
| Manual workflow routing | Explicit versioned quote/depth entry points with separate private recipe secrets; no legacy fallback | Fundamentals/dividends remain unimplemented in the new workflow |
| Local worker regressions | **82 tests passed**, including blank-field, invalid-number, raw-receipt and dispatch checks; compilation passed | No model/Stage regression run claimed |
| Private worker publication | **19 generic files pushed; all remote SHA-256 hashes verified**; no project credentials, native recipes or raw data uploaded | Main public project was not committed or pushed |
| Private cloud verification | **82 tests passed** on a standard hosted Linux runner, with synthetic isolated fixtures only | No market source/database accessed; not a live collection timing/completeness test |
| Web cutover syntax review | All **36 selected PHP runtime files** passed lint | No website deployment or full cutover acceptance |
| Database/storage review | Fresh read-only TLS check: **332,740,275 bytes**; draft collector schema/role both absent | No live SQL, role or data change |

The original depth diagnostic archive retains SHA-256
`7b74ca4e8e0fe181d2e2b1a65545bbb0237791d6113cfc5e6ef1e32dfcb143a7`.
The derived replay has separate identity and explicitly records its original
after-hours execution and original INCOMPLETE result. Every original capture,
capture ID, raw body and receive timestamp remains identical. It is not relabeled
as a successful original capture, a genuine forward observation or price authority.
Naive source clocks still have UNKNOWN timezone.

Debug APK remains at `myinterpreter_app/build/app/outputs/flutter-apk/app-debug.apk`,
192,654,818 bytes, SHA-256
`a393474b317f68f48152903618f62761628a94148f18c4e164c39062f09be018`.
No Dart runtime changes or APK rebuild occurred this continuation; the previously
rebuilt artifact was verified and its SDK connection re-tested with updated keys.

## What is taking time and what remains

1. **Operational data feed and bounded storage — largest remaining implementation.**
   Quote/book acquisition is not yet an app quote, dividend, fundamental or daily
   portfolio service. Finish the remaining adapters, explicit company/identity
   mappings, separate app projections, ratio rules, owner-only daily valuation and
   maintenance. Owner/company editing handlers still require their migration;
   the legacy compatibility client's network calls deliberately fail.
2. **Raw archive capacity and restricted cloud persistence.** The draft 350 MB
   database guard has only 17,259,725 bytes of headroom at the new measurement.
   Earlier two-sample planning suggested about 22.3 MB/month before database/other
   growth, not a reliable production forecast. Continuous raw writes cannot safely
   start with this design. Verify a private raw-object/export quota and bounded
   archive policy; retain original evidence. Do not raise guards or delete history
   automatically. SQL007 remains draft; no collector role or database credential
   has been provisioned. Keep elevated database/API keys out of workers.
3. **Actual private-cloud acquisition test.** The new generic package is now
   published and cloud-tested against synthetic fixtures. Revised native recipes
   remain local; they have not been uploaded as collection secrets. A durable raw
   sink and narrow credential boundary must be ready before a live batch test.
   Existing reachability success is not that test. The earlier 69.92-second batch
   was local/after-hours; combined job runtime and daytime coverage remain unproven.
4. **Email confirmation/reset and callbacks.** Custom SMTP is still UNKNOWN and no
   inbox delivery was tested. No Management/SMTP credential is available through
   the project API keys. Finish configured callback/reset behavior and verify actual
   delivery after sender/redirect settings are established. Keep email confirmation
   enabled; password login success does not prove signup email delivery.
5. **Device testing and reviewed cutover.** Validate the debug app on a real device,
   review the exact website/APK release set and permissions, then deploy only under
   the required authorization. The main public worktree contains extensive unrelated
   work and historical sensitive source references; never blanket-add or push it.

No automatic schedules, production collection, website deployment, release APK or
prediction execution were activated. The private cloud test had no secrets or
artifact uploads. The previously supplied $0 extra-spend cap was not changed.
The prior 1,882-minute plan still needs actual collection measurements and account
usage monitoring; a fast synthetic test is not a runtime or billing guarantee.

Both saved account assignments remain owner-deferred, with matching emails kept
only in the private record. Later require confirmed email ownership and newly
chosen passwords. The owner-only navigation redesign remains after the current
migration. No real-user assignment, original recovery rewrite, frozen-model change,
genuine prediction/outcome write or Appwrite request occurred.

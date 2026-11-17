# Genuine archive and shadow publication verified — October 29

The owner updated the scoped Management token to Secrets Read-write. Provisioning
then succeeded. **One genuine current quote/MASI capture was acquired, privately
archived, byte-verified and published to the private shadow candidate.** All trial
controls and credentials were disabled/removed afterward and independently
rechecked through fresh read-only connections.

The complete trial remains **partially accepted**: its final authenticated preview
check stopped because Supabase Auth has **zero existing user accounts**. No account
was created, no password chosen and no email sent. Do not turn that failure into a
successful signed-in acceptance claim or reopen the revoked trial automatically.

## Confirmed result

| Check | Actual result |
| --- | --- |
| Genuine capture | 2026-10-29 15:52:46 UTC; original timestamps/raw bytes preserved |
| Private compressed archive | 25,224 bytes; STORED; fresh downloaded bytes exactly equal local evidence |
| Shadow candidate | 82 rows, exactly matching the published document and payload hash |
| Same-date quote availability | 64 stocks + MASI |
| Missing quotes | 17 stocks explicitly MISSING_QUOTE; no substitutions |
| Acquisition completeness | INCOMPLETE; never relabeled complete |
| Available-price status | REPORTED_DATE_ONLY; source event timezone/time authority remains unverified |
| Portfolio/model eligibility | False for every candidate row |
| Signed-in preview | Not accepted: no real Supabase Auth user exists |
| Original application data | All 15 table fingerprints still match the protected original snapshot |
| Privacy | Anonymous original-table access denied; both private/public URL forms deny the real archived object |
| Cleanup | Archive/feed/projection controls off; provider off; trial revoked; zero active leases |
| Endpoint state | All three functions return exact disabled HTTP503 responses |
| Secrets | Both caller hashes and both enable flags absent |
| Database size | 333,436,595 bytes; 16,563,405 bytes below the existing 350 MB guard |

The object and shadow candidate remain private for evidence. No application table,
portfolio, genuine prediction/outcome ledger or frozen model was updated. No cloud
schedule, app reader, website/APK deployment, Git commit/push or production model
execution was activated.

Local raw-response inspection also confirms **81 instrument references, exactly
64 quote rows, one index and one session-status row**. Normalization kept those
same row counts and reported zero frame issues. The missing 17 are absent from
the returned quote view; they were not dropped by parsing. Why the source omitted
them remains unknown. Instrument-reference prices are not automatically accepted
as current quotes or used to fill the gaps.

## Actual execution and failures

The first attempt failed before creating a lease: the session pooler applied the
postgres role's **two-minute** timeout after connection startup, ignoring the
requested 20-second startup option. SQL014 correctly rejected that configuration.
Its transaction rolled back, and early cleanup removed the inactive caller hashes.
There were zero source requests and zero leases from that attempt.

The operator runner now sets `SET LOCAL statement_timeout='20s'` in a **separate
statement before** issuing/revoking a lease. This changes no role defaults or
hosted contract. The corrected run created one trial, performed the actual capture
and received both archive STORED and shadow PUBLISHED receipts. Final preview
acceptance then failed for missing Auth users. Its original receipt and overall
failure status are preserved unchanged. Cleanup succeeded despite that failure.

The runner's report previously set its `shadow_published` flag only after preview
acceptance, making that flag false despite the genuine PUBLISHED receipt. Future
runs now record publication acknowledgement immediately and require a separate
preview flag for overall acceptance. This reporting correction does not rewrite
the original attempt or promote the current partial result to full success.

## Evidence and resume

Private directory: `private/manual-trial-20261029/`.

- `current-*/receipt.json` and transition journals preserve both the rolled-back
  timeout attempt and the actual partially accepted capture. The latter contains
  the private evidence directory location and exact raw/archive/payload hashes.
- `capture-final-*.json`: fresh read-only final verification, including original
  fingerprints, exact stored candidate/readback, existing Auth count, privacy,
  secret removal, no active trial and three disabled endpoints. Its `ok` field
  covers these checks; `whole_trial_accepted` remains false.
- Host-owned 0700 evidence directory contains original response bytes, original
  compressed archive and exact candidate. Do not publish or rewrite these files.
- `quota-owner-evidence.json`: owner dashboard image hashes and bounded-budget
  interpretation. No extra organization access is needed for this completed trial.

**Do not rerun this capture, renew its lease or attempt to reactivate its preview.**
The approved one-capture scope has been consumed. The 17 missing quotes still
need source-level coverage investigation; the capture demonstrates the backend
path works, not a complete current market session or production-ready data feed.

Next priorities:

1. Finish real signup/email confirmation and first-account acceptance using the
   existing web/mobile implementation. Previous Auth test users were temporary;
   historical MAU billing counts do not prove a current Auth account exists.
   Never invent passwords, auto-assign preserved portfolios or send setup emails
   without the agreed user-driven account flow.
2. Complete the signed-in preview check under a new explicit, bounded acceptance
   scope; retain this trial and its evidence unchanged. SQL014 will not admit old
   objects under a new window. Do not weaken that provenance boundary.
3. The first local-only coverage investigation is complete: the response itself
   omitted 17 quotes, with all 81 references present and zero normalization issues.
   Investigate that coverage gap further without promoting reference prices or
   treating absent rows as parser failures. No second source capture is authorized
   by this consumed trial scope.
4. Complete private recurring-worker publication/outbox/quota setup, then separately
   approve recurring collection and application cutover. The user wants focused
   progress; reuse accepted checks rather than restarting broad reviews.

The previous 80% estimate was implementation-oriented and overly optimistic as an
overall usability measure. Report these concrete milestones and remaining gates.

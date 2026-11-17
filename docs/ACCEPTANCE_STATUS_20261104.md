# Acceptance follow-up — November 4, 2026

Current evening status: [ACCEPTANCE_FOLLOWUP_20261104.md](ACCEPTANCE_FOLLOWUP_20261104.md).
Storage cleanup and collector repairs are now deployed; older paragraphs below are historical.

Fresh read-only invalid-token recovery probes returned HTTP 303 to the requested
website and Android callback destinations. Neither routed to localhost. This
supersedes the redirect failure recorded November 2, but does not verify valid
email delivery, templates, PKCE completion or password reset. Management Auth
configuration access remains denied. No Auth settings were changed here.

Database size is 335,328,947 bytes, leaving 14,671,053 bytes below the documented
350,000,000-byte guard. Migration staging occupies about 114 MB including indexes.
Its 110,723 documents contain 84,640,163 bytes of other payloads and 21,422 bytes
of personal recovery payloads. The installed saved-portfolio claim function uses
staging. Wholesale removal is unsafe. No rows were deleted, no guard increased.
A proposed full private backup was blocked by automatic approval review pending
explicit authorization to export personal recovery records. No backup was made.
Any cleanup still requires verified preservation, dependency review and a restore
test; logical deletion does not guarantee immediate physical disk reclamation.

The connected Android device reports API 19; the final parity APK requires API 24.
The configured app package was not found. Use a compatible device for acceptance.
The existing APK was inspected, not installed or rebuilt.

The deployed durable workflow is active on the default branch and contains its
weekday schedule, but the scheduled-event history returned zero runs. This is
unresolved trigger acceptance, not proof of collector failure. A normal manual
`auto` dispatch (41824585954) was accepted with bootstrap false and existing gates;
it cannot count as scheduled-event proof. At the initial check there were zero
official-close batches and valuation receipts. Official acceptance must occur in
the genuine eligible window, without backdating or fabricated prices.

Private diagnostic scripts and receipts: private/acceptance-20261104/.
The browser connector could not connect to its local debugging endpoint; no new
signed-in browser acceptance was established.

Run 41824585954 completed with failure in collection. All subsequent checkpoint
pack/upload/readback/retention steps succeeded. The failure cause is not yet
known: automatic approval review blocked downloading the private failure log
because it could contain sensitive data. Explicit permission was requested.
No log was exported, and no claim of successful market acquisition is made.

## Authorized follow-up

The owner confirmed that the displayed URL configuration already matches the
required website and mobile callbacks; no redirect-setting mutation is needed.
They explicitly approved private staging backup and failed-run log inspection,
and deferred phone connection/testing until another time.

The downloaded failure log reports INCOMPLETE with 77 requests, 77 snapshots and
3 missing identities. The auto dispatch selected only depth and returned exit 2;
it did not attempt quote publication. Collection lasted approximately 86 seconds.
The current depth collector has an 80-second acquisition budget, so budget
exhaustion is a plausible cause, not proven by the summary log. The completeness
check correctly remained closed; no source-universe or valuation rule was changed.
The prior approval-review export block is resolved by explicit owner permission.

The authorized staging backup completed: 110,723 documents plus 16 dataset
metadata records; gzip size 11,078,886 bytes. Full decompression, JSON parsing,
record count and uncompressed SHA256 verification passed. No database rows were
changed or removed. The shared project mount ignored chmod, so the archive,
backup receipt and failure log were moved with matching hashes to the owner-only
host vault ~/.local/share/myinterpreter/acceptance-20261104/ (directory 0700,
files 0600). Shared workspace copies were removed. The local reconstruction
check uses SQLite; it must not be described as a PostgreSQL restore rehearsal.

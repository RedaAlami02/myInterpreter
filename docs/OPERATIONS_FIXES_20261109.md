# Operational repairs — November 9, 2026

Private worker commit `d926dc8d0d479d1c91586adc9f2d699d5704e39f`
was published with exact remote readback. The official-review pin was updated and
verified; collection/review gates were restored. No website/mobile runtime changed.

Health cron's UTC wakeups did not coincide with the hours accepted by its database
local-time gate. Hourly weekday wakeups now allow the existing 12/20 local-time
gate to select execution regardless of offset. The existing daily cap, cooldown,
permissions and retention remain. Manual acceptance dispatch reached GitHub:
run 42590526260 completed successfully with HEALTHY, database size 223,688,371
bytes and headroom 126,311,629 bytes. Automatic gate-time execution and new-email
receipt still require observation; the manual run is not automatic-tick proof.

Official admission used an 8 MB estimate against an 8 MB daily policy budget.
Friday's first unusable report consumed only 7,881 bytes, but every subsequent
preflight failed because 7,881 + 8,388,608 exceeded the daily budget. Only the
OFFICIAL_CLOSE preflight estimate now uses one byte to determine whether any
budget remains for an attempt. Final reservation still checks actual archive bytes;
daily caps, global storage limits, time windows, leases and financial review remain
unchanged. The exact prior function definition was saved privately. The guarded
SQL migration records this repair. Genuine close/valuation acceptance remains due
in the next eligible window.

The dividend source returned 200 for the required current-year calendar and 302
for the optional future calendar. The worker now skips optional HTTP302 responses,
without following the redirect or treating its body as calendar evidence, matching
the existing optional404 handling. Required redirects still fail. Six focused tests
passed, including optional versus required redirects. Live acquisition/normalization
returned COMPLETE, one capture and zero errors, without publishing or financial
writes. The next scheduled publication remains a separate acceptance step.

At inspection there was an accepted official batch and valuation receipt for
November 5. This does not establish daily success for November 6 or later.
Receipts and raw diagnostics remain private under the owner acceptance vault.

Hosted verification initially stopped before tests because unrelated Microsoft
APT repositories returned HTTP403. All three PDF-dependent workflows now update
indexes using only `/etc/apt/sources.list.d/ubuntu.sources`, excluding unrelated
runner repositories. Signature verification remains enabled. The first deployment
attempt waited for an active collector to finish; no in-progress collection was
cancelled. Final runtime-fix commit: `52e334d335ef920bb31ae9266103a31ce190a4da`.
Hosted verification run: `42591270884` (result recorded separately).

The full local worker suite passed all 371 tests after the dividend fix.

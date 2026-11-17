# Private object archive — October 28 continuation

This follows `WEB_MOBILE_AUTOMATION_RESUME_20261028.md`. Website/mobile automation
remains the priority; prediction work and both account assignments stay deferred.
Private details: `private/archive-gateway-20261028T185149Z/HANDOFF.md`.

## Implemented

The staged gateway separates growing raw gzip files from PostgreSQL metadata.
It is an alternative to draft SQL007, not an installed extension. Code is in
`automation/archive-gateway/` and `migrations/supabase/009_private_object_archive.sql`.

- Workers use a separate scoped token and exact project binding. No elevated
  project key, database URI, user access or archive read API is given to CI.
- Gateway authentication precedes body reading. Request/decompression bounds,
  calendar/aware receipt times, raw hashes and capture IDs are checked. Replays
  and diagnostics are excluded; all stored evidence remains UNPROMOTED.
- SQL serializes budget reservations, accounting for project Storage and pending
  writes. Unknown sizes or a non-private bucket fail closed. Uploads use hash-only
  paths and no overwrite, followed by full read-back/hash verification.
- Finalization retains attempts and commits a COMPLETE logical slot once. Missing
  committed objects cause explicit failure. No automatic evidence deletion or
  reservation expiry. Interrupted uploads can finish the original reservation.
- A private bounded outbox fsyncs transmission copies before upload. Failures retain
  bytes; an exact receipt removes only that copy. Collectors retry pending copies
  before fetching again; `flush_outbox.py` supports inspection and exact retries.
  Interrupted partial filesystem writes remain for operator review.

The outbox survives a process restart on the same filesystem. **It does not
survive disposal of an ephemeral runner.** A verified private cross-run fallback
is required before schedules. None has been enabled. Old pending captures that
never obtained a reservation require explicit historical recovery after the
new-admission freshness limit; their timestamps must not be changed.

## Verified evidence

| Check | Result |
| --- | --- |
| Local worker tests | **101 passed** |
| Local gateway tests | **19 passed**, no network/environment permissions |
| Local SQL regressions | **23 passed**: 16 object archive + 7 existing acquisition |
| Concurrent SQL tests | **2 passed**: capacity serialization and unique slot commit |
| Python-to-Deno HTTP | Synthetic loopback integration passed, including complete/incomplete evidence, retry, tamper and replay rejection |
| Private cloud | **101 worker + 19 gateway passed**; 25 SQL tests explicitly skipped without an isolated database |
| Private publication | **35 reviewed generic files pushed; all remote hashes verified** |
| Live read-only review | TLS/read-only passed; DB **332,740,275 bytes**; **0 Storage buckets/objects**; archive schema absent |

PostgreSQL 18.6 was unpacked into `/tmp`, not installed system-wide. SQL tests
rolled back changes or dropped their disposable database/roles. The temporary
server and HTTP fixture were shut down. No credentials/native profiles were
uploaded. No source request, live SQL, bucket/function deployment, new signup
email, app-table update, model/ledger change or schedule activation occurred.
Main-project changes remain uncommitted; only the private package was pushed.

## Capacity and activation gates

Free limits list 500 MB database per project and 1 GB Storage, with Storage billed
at organization level. This project's Storage is empty; other projects' usage is
unverified. SQL009 starts disabled, with upper guards of 750 MB objects and 350 MB
database. These are not claims of available quota. File metadata/receipts still
grow PostgreSQL. Measure real growth/egress/runtime before activation.
[Official quotas](https://supabase.com/docs/guides/platform/billing-on-supabase)

The earlier 22.3 MB/month illustration used two samples. GitHub's included-usage
reference now expresses Pro compute as $18, while its Actions page also lists
3,000 minutes. Verify actual account allowance/usage before activating the earlier
1,882-minute plan. The $0 extra-spend cap is unchanged. No spare artifact capacity
is assumed for fallback storage.
[Included usage](https://docs.github.com/en/billing/reference/product-usage-included),
[Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

Live installation still requires:

1. Independent technical/security review of gateway, SQL ownership/grants and recovery.
2. Scoped deployment authorization and Supabase Management/CLI access. Earlier
   instructions prohibit cloud deployment. Source-use approval remains supplied;
   current project API keys do not supply Management deployment access.
3. Organization quota allocation and a private cross-run fallback plan.
4. Private bucket creation through the Storage API, transactional SQL009 installation
   and function deployment with enable switches off. Verify hosted auth, REST/error
   behavior, access denial and exact read-back before any authorized manual trial.
5. Private token provisioning, encrypted recipes and actual cloud/session testing.
   Recurring schedules remain a separate gate.

Detailed steps: `automation/archive-gateway/README.md`. No real write token was
generated. Two revised profiles were prepared privately with only the project
binding added; native bindings and source namespace are unchanged.

## Continue app work

The archive does not update app tables. Continue quote/index projections and exact
identity mappings, fundamentals/dividend adapters, company admin writers, daily
portfolio valuation and maintenance. The preserved bulk response still has only
66 detailed quotes for 81 references; do not fill missing prices from books/catalogs.
Naive source clocks remain UNKNOWN.

SMTP/real inbox delivery, confirmation/reset/callbacks, physical-device validation
and reviewed website/APK cutover remain unfinished. Keep confirmation enabled.
Account assignment and the rare owner-only navigation redesign remain deferred.
This checkpoint does not claim production readiness or revise the overall estimate.

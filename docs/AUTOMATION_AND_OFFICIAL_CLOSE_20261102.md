# Automatic updates and official-close continuation — November 2

No prediction/model work. No Appwrite requests. Source identities and raw
reports remain private. Collection, valuation and cloud schedules remain OFF.

## Verified today

One bounded TLS-verified request retrieved the current-session daily report:
245,753 original PDF bytes, captured at 20:10:20 UTC on November 2.
The existing retained parser produced 80 securities, 76 available closes and
zero close/next-reference discrepancies. Four missing closes remain missing.

`automation/managed/official_close.py` now reuses that established table layout
with exact decimal strings, strict session matching, explicit missing prices,
per-row observation identities, duplicate-identity rejection and exact
close/reference agreement. PDF extraction is bounded and does not execute any
research pipeline. Unknown publication/close clocks remain null. Parsing does
not approve authority, map company identities, archive remotely or write P&L.

The genuine report passed the new parser, with identical identities and numeric
values to the retained parser (80/80). The original report is stored privately in
host storage, and its receipt/hash and both parsed outputs are under
`private/automation-close-20261102/`. Existing historical evidence is untouched.

A fresh repeatable-read/read-only verified-TLS database connection confirmed
source/valuation controls OFF and no active source lease. Across 12 distinct
company names in current holdings, nine have unique normalized-name report
candidates with closes. IAM, MUTANDIS and T2S Group Holding require explicit
identifier bindings. Name candidates are not approved identity mappings. No
user IDs, amounts or credentials were printed; no financial records changed.

## Scheduling and cost

The actual retained schedule configuration has five-minute depth captures,
fifteen-minute quotes, Monday dividends and weekday cleanup. The replacement's
existing manual worker windows instead have hourly depth and Friday dividends.
This drift is confirmed; neither replacement schedule has been activated.
The retired cron timezone still needs evidence before claiming exact parity.

`automation/managed/schedule_plan.py` enumerates the retained cron expressions
under an explicitly labeled candidate UTC interpretation. It never dispatches
or changes the active worker's accepted timing contracts. November 2026 has
2,016 depth, 672 quote, five dividend and 21 cleanup job starts: 2,714 total.

Current official GitHub documentation lists $18 monthly included Pro compute
and $0.006/minute for standard two-core Linux, rounding every job upward.
Separate one-minute jobs would consume $16.284; separate two-minute jobs would
consume $32.568. These are scenarios, not measured recurring-run acceptance.
Retries, fundamental/valuation jobs, excess overhead, artifact storage and the
other repository's shared usage are excluded. Remaining account credit is
unknown. The planner cannot authorize activation, including when a supplied
budget fits. Do not declare the original schedule free based on the old
hourly-depth estimate.

Sources: [included usage](https://docs.github.com/en/billing/reference/product-usage-included),
[runner rates and rounding](https://docs.github.com/en/billing/reference/actions-runner-pricing).

## Checks

- All managed Python regressions: **341 passed** (including 14 new parser/cost tests).
- Worker distribution boundary checks: **3 passed**.
- Genuine report: 80/80 identity/value parity, 76 closes, zero discrepancies.
- Database inspection: read-only; controls remain OFF; financial writes zero.
- No deployment, schedule activation, prediction, model or genuine-ledger changes.

## Remaining practical work

1. Bind report instrument IDs to existing company IDs using retained identity
   evidence; resolve the three unmatched holdings names explicitly. Preserve the
   report's four unavailable closes instead of inventing them.
2. Connect this separate official-report acquisition to durable private archive
   and SQL021 approval. Parsing alone does not satisfy stored-archive checks.
3. Add an owner-safe unattended valuation entry point and independently test its
   existing locks, idempotency and execution-time holdings semantics. SQL021's
   existing 17–19 Casablanca execution window had passed before today's capture;
   do not backdate a genuine valuation or silently change that rule.
4. Implement and verify recurring source admission/retries, confirm schedule
   timezone, measure actual hosted collector runtimes and verify shared budget.
   Manual trial leases do not authorize unattended recurring collection.
5. Enable only verified schedules with bounded cost/storage and retry recovery.

## Confirmed email blocker

The owner tested a confirmation email and landed on localhost:3000. This is
confirmed broken routing, not acceptance. A fresh Management Auth-config GET
again returned 403; no settings changed. The dashboard URL settings in
`AUTH_REDIRECT_FIX_20261102.md` were requested again. Do not retain the owner's
complete authentication code/link in documentation. Mobile routing is not yet
verified by a fresh real email and device.

# Scheduled-trigger review — November 4, 2026

Fresh GitHub checks found a private, non-fork repository with Actions enabled,
all actions permitted, default branch main, an active durable workflow on that
branch and all five application gates enabled. Scheduled-event history was empty.
The existing manual run started normally. Billing usage access returned 404;
remaining account allowance is unknown, not verified as sufficient.

A bounded recovery attempt was published at 12:20 UTC:

- Private commit ffd97825a9021d76dc7cb153fc717c648d97230f changes only the weekday
  cron from `*/5 8-18 * * 1-5` to `2-59/5 8-18 * * 1-5`.
- The workflow was enabled through the API and its active state read back.
- Exact published bytes were verified. All 132 shifted weekday wakeups for the
  checked date select the same kinds in the existing Casablanca dispatcher.
- Monday dividend wakes, collection gates, spending restrictions, source pins,
  official-close policies and financial writes were unchanged.

This removes top-of-hour wakes and refreshes the schedule definition. It does not
prove the original cause or successful triggering. GitHub documents best-effort
schedules, including delays/dropped runs under load. Only an observed `schedule`
event can establish trigger acceptance; manual dispatches are not substitutes.

Private rollback, commit receipt and timestamped scheduled-event observations are
in private/acceptance-20261104/. No unrelated root-worktree changes were published.

## Resume check at 15:32 UTC

Scheduled-event history still had zero runs more than three hours after the
published cron change. The recovery attempt has not established triggering.
The independent-timer option was presented to the owner; no alternative timer
was installed while that consequential hosting choice remained unanswered.

Read-only backend checks: pg_cron and pg_net are available but not installed;
Supabase Vault is installed. Database size is 335,468,211 bytes. An independent
backend timer is technically possible, but is not already configured. It would
need a dedicated GitHub credential restricted to Actions access for the worker
repository, protected secret storage, bounded execution records, an off switch
and checks against duplicate dispatches. Do not copy the existing broad local
GitHub credential into the database. Preserve the existing zero-dollar limit.

Next acceptance must distinguish: timer execution, GitHub dispatch acceptance,
actual runner start, data coverage/publication, and checkpoint preservation.
A fallback dispatch is a workflow_dispatch event and must be labelled as such;
it does not establish repair of GitHub's native schedule trigger.

## Independent timer activation at 15:44 UTC

The owner selected the independent timer and supplied a dedicated fine-grained
GitHub token. The first token selected the wrong repository; the replacement
successfully read the required private workflow. No token values were logged.

The two-file Edge Function private-schedule-dispatcher was deployed with exact
source readback. Thirteen isolated Deno tests and entrypoint type checking passed.
Anonymous calls returned 401; authorized calls while disabled returned 503.
PostgreSQL installation verified disabled ticks, private schema/function denial
for anon/authenticated/service_role, paused jobs, recent-attempt and daily-limit
guards. Guard test mutations were rolled back. The first installation attempt
rolled back on a denied direct cron.job update; the supported cron.alter_job API
was used successfully instead.

Two Supabase Cron jobs are active with the private control enabled. GitHub commit
cc60d4333b9002867ad679c08d9ce3f866d0b57d removes only the old native schedule block;
workflow_dispatch and existing application gates remain unchanged. Exact GitHub
file readback passed. This is replacement of the unreliable trigger, not proof
that GitHub native scheduled events were repaired.

Caller secrets and GitHub credentials are separately stored in Vault and Edge
Function secrets. Owner-only deployment receipts, native-cron rollback and ongoing
observations live in ~/.local/share/myinterpreter/scheduler-20261104/.
Actual cron/dispatch/collection acceptance is recorded separately below.

Emergency stop (database owner):

```sql
BEGIN;
UPDATE app_timer.control SET enabled=false WHERE singleton;
SELECT cron.alter_job(jobid,active:=false) FROM cron.job
 WHERE jobname IN ('app-private-timer-weekday','app-private-timer-monday');
COMMIT;
```

No historical data was deleted and no storage guard or account spending limit was
raised. Only this timer's new cron execution history is bounded to seven days.

### First genuine independent tick verified

At 2026-11-04 15:47:00 UTC, Supabase Cron ran app_timer.tick without manual
invocation. The job succeeded, pg_net received HTTP202 DISPATCH_ACCEPTED without
timeout, and GitHub created run 41861323770 at 15:47:04 UTC on commit
cc60d4333b9002867ad679c08d9ce3f866d0b57d. The runner entered in_progress.
This verifies the independent cron → function → GitHub dispatch → runner chain.
The GitHub event correctly reads workflow_dispatch. It is not a native schedule
event. Collection completeness and checkpoint outcome remain separate acceptance.

### First-run collection result

Run 41861323770 completed with overall failure because depth coverage was
incomplete: 75 snapshots, 4 missing identities. Quotes returned exit0 with
PARTIAL_DISPLAY_PUBLISHED; this is partial display publication, not full coverage
or prediction eligibility. The auto dispatcher reported jobs quotes=0, depth=2.
All checkpoint pack/upload/readback/retention steps succeeded. Private failure-log
inspection was authorized and the raw log is stored only in the owner-only vault.
The independent trigger is verified operational for this first tick; full-session
reliability and depth completeness remain open. No coverage safeguard was relaxed.

## Evening repairs and operational monitoring

See [ACCEPTANCE_FOLLOWUP_20261104.md](ACCEPTANCE_FOLLOWUP_20261104.md) for
verified repeated afternoon triggers, the deployed slot-based cadence correction,
collector/official-review repairs, the matching review pin and the new health monitor.
A full corrected market session remains pending.

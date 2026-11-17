# Independent timer

Supabase Cron invokes a token-protected Edge Function through pg_net. The function
checks the existing private GitHub workflow for active/recent runs before a fixed
`auto` dispatch on the configured branch. Collector gates, current timestamps,
financial review and checkpoint handling remain in the existing workflow.

Only a dedicated fine-grained token restricted to the worker repository with
Actions read/write is acceptable. Never copy the local broad GitHub credential.
GitHub credentials live in Edge Function secrets; Vault contains only the caller
token and fixed function endpoint. The timer accepts no caller-selected job,
repository, branch or bootstrap flag. Do not publish private runtime values.

`install.sql` creates a private control row and two paused jobs with a disabled
control gate. The daily dispatch-attempt cap is 134, with one attempt per five-minute
slot, an additional one-minute cooldown and a single enqueue lock. Slot checks
allow the next cron tick even when GitHub created the preceding run seconds late.
Dispatcher queries fail closed. Its total
GitHub request budget is 15 seconds; pg_net waits at most 20 seconds. Only this
timer's new execution records older than seven days are pruned. No historical,
market, portfolio or recovery rows are deleted. pg_net response retention must
also be checked during installation.

Before activation:

1. Validate the dedicated token against the fixed worker repository without
   exposing it. Review and deploy the two TypeScript files, with JWT verification
   disabled only because the function validates its own hashed bearer token.
2. Install SQL transactionally, verify jobs and control remain disabled, ownership,
   RLS and execute permissions, and test ticks while disabled. Check transaction
   rollback on any failure. Disabled-state and guard tests were verified on the hosted PostgreSQL installation.
3. Store a fresh caller secret in Vault and its SHA256 in Edge Function secrets.
   Configure APP_TIMER_GITHUB_TOKEN, APP_TIMER_REPOSITORY, APP_TIMER_WORKFLOW,
   APP_TIMER_BRANCH and APP_TIMER_ENABLED. Verify unauthorized requests fail.
4. Remove the native schedule block from the GitHub workflow with a pinned,
   one-file update and exact readback; retain workflow_dispatch. Do not disable
   the workflow itself, which would stop fallback dispatches too. Preserve the
   native cron for rollback. This avoids racing two timer systems.
5. Enable the private control and the two jobs, then observe a genuine cron tick,
   Edge response, dispatch event, runner job and preserved checkpoint. Verify
   actual coverage/publication separately. Never call an HTTP202 a collected batch.

Stop by disabling app_timer.control.enabled and both named cron jobs. Credential
expiry must be recorded and renewed. HTTP/permission failures must remain visible;
this timer does not establish external alert delivery or unlimited free capacity.

Tests: `deno test automation/schedule-dispatcher/handler_test.ts`.

Native GitHub event remains workflow_dispatch under this design. This is an
independent trigger, not evidence that GitHub's native scheduling was repaired.

Deployment status and acceptance: docs/SCHEDULE_TRIGGER_REVIEW_20261104.md.

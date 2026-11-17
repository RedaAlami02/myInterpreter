# Operational health notifications

The private PostgreSQL timer sends a bounded aggregate snapshot to the authenticated
health dispatcher. It dispatches only `health.yml` on the configured private worker
branch. No source names, account identifiers, prices or credentials enter the
snapshot or workflow logs. The workflow fails when checks need attention, using
GitHub Actions failure-email notifications selected by the owner.

Checks cover actual storage headroom against the live guard, stale or incomplete
quote/depth archives during the session, a genuine official-close batch after
19:15 Casablanca time, valuation receipts when holdings exist, and the latest
collector result. A missing close is reported as unverified; it is not a claim
that every weekday is a trading day. No prices are synthesized and financial
eligibility is never relaxed. Receipt existence does not certify every holding.

Automatic checks run at 12:07 and 20:07 in the database Casablanca timezone on weekdays.
Hourly UTC wakeups let the function select the eligible local hours regardless of offset. The daily cap is
three attempts, allowing one manual acceptance check in addition to the two
scheduled checks. A ten-minute cooldown, advisory lock, strict body validation,
20-second HTTP budget and seven-day cron-history retention bound execution.
Installation starts disabled. Function execution, tables and schema are denied
to public application roles. The health function reuses the existing restricted
Actions token and protected caller credential; it receives no financial credential.

Delivery depends on GitHub notification settings and the user's inbox. A workflow
failure alone does not prove email delivery. Likewise, the same database/GitHub
outage can prevent this monitor from running; this is not an external uptime monitor.
The first acceptance dispatch is manual and must not be counted as a scheduled tick.

Stop: disable `app_timer.health_control.enabled` and pause cron job
`app-private-health`. Deployed receipts are in the owner's private acceptance vault.

Tests: `deno test automation/health-dispatcher/handler_test.ts` and
`PYTHONPATH=automation/managed python3 -m unittest discover -s automation/managed/tests -p test_health_check.py`.

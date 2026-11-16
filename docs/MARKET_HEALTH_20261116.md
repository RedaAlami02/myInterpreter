# Market data health audit — 2026-11-16

`automation/managed/market_health.py` and `tools/audit_market_freshness.py`
produce a read-only freshness report for the public Supabase market tables. The
audit runs entirely in GitHub Actions and writes no database rows.

## What it checks

| Area | Check | Default attention threshold |
|---|---|---|
| Prices | `latest_prices` row exists, `pa > 0`, last date age | more than 7 calendar days |
| Fiscal year | `company.fiscal_year` present, not older than last year, not a future/uncompleted year | missing, before `as_of.year - 1`, or `>= as_of.year` |
| Shares | `company.na` present and positive | missing or zero |
| Dividends | latest dividend year and `confirmed` flag | no row, or last year older than `as_of.year - 1` |
| Shareholders | parsed `company.shareholders` list | empty or malformed |

Seven calendar days is deliberately tolerant of weekends and short holidays. It is
a staleness alarm, not a market-calendar assertion. A suspended instrument will
still be flagged; that is intentional and should be reviewed rather than hidden.

## Cloud operation

Workflow: `.github/workflows/market-health.yml`.

- Manual: Actions → *Market data health* → set the age threshold.
- Daily: 06:30 UTC, only when repository variable `MARKET_HEALTH_ENABLED=true`.
- Secrets: `SUPABASE_PROJECT_URL`, `SUPABASE_SERVICE_ROLE_KEY` (the same service
  role used by the reconciliation writes).
- Outputs: `market_health.json`, `.csv`, `.md`, uploaded as a private artifact
  and summarized in the job page.

No local runtime is required. The same pure audit can be run offline against
exported rows for tests.

## How it complements reconciliation

The live acquisition and publication path is the private managed runner
(SQL026/027/028 and the private workers), not this repository. This audit observes
its output; it does not replace it. If prices are stale, inspect that runner's
checkpoint and source-age gates before adding another collector.

- **Reconciliation** answers “is the share count and annual row internally
  consistent with the exchange?”
- **Health** answers “is the website's stored data recent and complete?”
- Both are cloud artifacts; neither writes company data except the explicit
  reconciliation RPCs.

## Limitations

- Price age uses the stored `date`, not a source latency measurement. A fresh row
  can still contain a delayed quote.
- A missing dividend record does not prove the company did not pay; it means no
  confirmed row is stored.
- Shareholder presence is not a completeness check; a non-empty but outdated list
  still passes.
- The audit does not validate annual units or accounting scope. That remains the
  reconciliation/annual-review responsibility.

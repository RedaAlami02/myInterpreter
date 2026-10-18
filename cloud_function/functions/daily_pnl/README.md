# Weekday portfolio P&L

Writes one daily unrealized P&L record per tracked user to the existing
`benefits` collection. No new column or migration. Uses the same pre-fee
valuation as the portfolio summary: sum(quantity × price − total_cost).
Realized trading profit, taxes, fees and dividends are not added.

## Status: implemented, not deployed

The user approved weekday automation after market close. Activation is a
separate production change and has not been performed. `function.json` is a
single-function configuration fragment, not an automatically registered job.
The shared Appwrite configuration has unrelated local edits and was not changed.

## Scheduling

Proposed UTC cron: `15,45 16-17 * * 1-5`. The function additionally checks
Africa/Casablanca time and runs only on weekdays from 17:00 to before 19:00.
The first eligible slot is 17:15 local both at UTC+1 and during the UTC+0 period;
later slots retry failures without overwriting a successfully saved day.
Timezone rules come from the installed `tzdata` package, not the host files.

This leaves a buffer after the exchange's normal session and existing price
ingestion schedule. Reference: [official trading hours](https://www.casablanca-bourse.com/market-data/horaires-cotation-comptant),
checked 18 October 2026. Revisit the window if market/ingestion hours change.

## Safety and semantics

- Pagination covers all holdings and quotes. Historical `benefits` user IDs
  also identify sold-out portfolios, whose unrealized P&L becomes zero.
- A position needs a positive, finite quote observed on the same local date
  at or after 15:45, and not in the future. If any position is missing a valid
  quote, skip that user's entire record; retry later. No zero-price fallback.
- Existing records for the date are preserved, including old manual snapshots.
  A deterministic hashed user/date ID prevents duplicate concurrent creates.
- Records retain only `read("user:ID")` and `write("user:ID")` permissions.
  Verify collection-level permissions are private and document security enabled
  before activation: document permissions cannot cancel broad collection access.
- Authentication uses the per-execution dynamic key with `documents.read` and
  `documents.write`. No public execution permission. No credentials in code.
- Logs/responses contain counts only, not users, holdings or financial values.
- Day timestamps are UTC midnight labels for the Casablanca calendar date,
  compatible with historical records, not the exact calculation time.

## Deployment checklist (requires approval)

1. Review/merge only the `function.json` entry into the deployment configuration,
   or create that single function through the console. Do not bulk-deploy the
   unrelated functions currently being edited.
2. Set `APPWRITE_ENDPOINT` and `APPWRITE_PROJECT_ID` in the function environment.
   Do not set a persistent API key. Grant only the two document scopes above.
3. Verify `benefits` attributes (`user_id`, datetime `date`, float `value`), its
   user index, private collection permissions and document security.
4. Build/deploy this function only; initially leave its schedule disabled.
   Validate with a safe test database/account before enabling the proposed cron.
5. Inspect the first scheduled execution's aggregate counts and verify one
   record per eligible user/day via an authorized account. A `partial` result
   returns HTTP 503 to make missing valuations/write failures visible.

Rollback: disable this function's schedule. Existing history is not deleted.
Restoring the manual web control requires reverting its UI commit separately.

## Tests and limits

```sh
python3 -m unittest discover -s cloud_function/functions/daily_pnl/tests -v
python3 -m compileall -q cloud_function/functions/daily_pnl/src
```

Tests use a fake database; no live account or schema changes were made.
Weekdays are not an exchange holiday calendar. A weekday holiday may produce
a carried-price valuation if ingestion publishes fresh observations; stale
quotes are skipped. This is an after-close portfolio valuation, not an official
closing-price certification. Positions are those present at execution, not
reconstructed historical holdings; avoid concurrent trade edits while it runs.
New empty accounts without holdings/history have nothing to save. Historical
user IDs are scanned each run; at larger scale replace this with an active
portfolio registry and account-deletion cleanup. This task does not add that
schema or transaction locking.

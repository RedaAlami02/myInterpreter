# Company page optimization deployment, 18 November 2026

Implemented and deployed the first performance recommendation. Supabase remains
in Ireland. No hosting accounts, DNS, users, market records, portfolio rows or
collector schedules were changed.

## Result

- Initial company rendering fetches only the newest data observation, preserving
  the row used for market-cap/implied-share calculations. It no longer paginates
  the company's complete history before returning HTML.
- Independent shared-market reads use bounded parallel cURL batches. Directory
  reads run together; newest data, latest price, dividends and order book run
  together. Optional read failures leave other successful panels usable.
- The current local ADDOHA path changes from up to 13 sequential backend reads to
  approximately five dependent network stages when parallel cURL is available:
  authentication, current feed, directory batch, detail batch and recent sessions.
  There are still nine HTTP requests on that initial path, rather than five.
  This is code analysis, not a production authenticated browser trace. Sequential
  fallback remains available when any required multi-cURL function is disabled.
- Recorded chart history loads after the initial browser frame through an
  authenticated, read-only RPC. It selects the latest UTC observation per day,
  breaks timestamp ties by descending record ID, returns only day and price, and
  rejects an over-limit result rather than silently truncating it.
- Loading, empty, unavailable and retry states are translated. Existing periods,
  range controls and chart plugins are retained.
- Chart and stored financial-profile endpoints release the PHP session lock once
  authentication is validated. Profile reads no longer require enabling direct
  upstream requests. The upstream request function keeps its existing disabled
  guard. Authentication and per-user portfolio protections remain intact.

## Database validation and measurements

The new `read_company_daily_history_v1(text)` function is SECURITY INVOKER and
STABLE, with an empty search path. Only authenticated callers receive execute
permission; the body also rejects missing identities. It reads only shared
`company` and `data` tables and performs no stored-data writes.

A rollback-only migration trial passed before the additive function was applied.
The applied-function checks verified exact daily price/date equivalence:

| Company | Daily observations | Median RPC SQL round trip, five samples |
| --- | --- | --- |
| ADDOHA | 866 | 71.5 ms |
| AFMA | 867 | 70.5 ms |
| AFRIC INDUSTRIES | 869 | 71.0 ms |

These timings include SQL networking from the execution machine and JSON result
transfer, not PHP, PostgREST or browser rendering. Earlier ADDOHA raw-history
pagination measured 340.8–399.2 ms across two five-sample runs. The new actual RPC
is consistent with the approximately 78–81% history-stage reduction found during
measurement; the history stage is now also outside the initial HTML path.

No full-page percentage improvement is asserted. The connected browser could
reach the live website, but its session was signed out. The signed-out HTML is
not a valid performance sample for the stock detail view. A request to sign in
was sent so an authenticated browser comparison can follow without sharing
credentials in chat.

## Verification

- All 30 offline PHP regression suites passed; the legacy live-backend suite was
  intentionally skipped by the existing runner.
- New PHP tests cover authenticated history calls, bounded normalized responses,
  invalid dates, invalid prices, ordering, duplicates, missing auth, malformed
  requests and redacted backend failures.
- Market-reader tests cover user-scoped batching, strict validation, optional
  failure isolation and strict-mode rejection. Existing partial-cURL fallback
  regression passes.
- Browser-script regression covers deferred fetch, chart creation, failure/retry,
  insufficient history and company identity mismatch.
- The real controller/template rendered with fictional records, asserting an
  initial latest-price panel and one-row history read, without embedded full
  history arrays.
- Five deployment-tool tests, PHP syntax checks, JavaScript syntax checks,
  Python compilation, catalog checks and whitespace checks passed.
- Proposed runtime files were scanned for configured private source hostnames;
  none were present.

Live browser checks after deployment:

| Request | Result |
| --- | --- |
| New chart script | 200, JavaScript |
| History request without a signed-in session | 401, JSON |
| History request with an array instead of a company name | 400, JSON |

The browser console records expected network errors for the deliberate 401/400
checks; these were negative validation probes.

## Deployment and rollback

The existing encrypted-FTP deployer uploaded eleven explicitly reviewed runtime
files and verified all uploaded bytes by reading them back. Existing files were
saved privately at `/tmp/myinterpreter-deploy-ygw1vayq` before upload. No remote
files were deleted. The SQL migration is not uploaded to the PHP public tree.

The deployment includes the market clients, compatibility batch adapter, history
helper/endpoint/script, stored-profile endpoint, company template and three locale
catalogs. `deploy.py` now includes the new runtime dependencies for future full
deployments.

For application rollback, restore the previous runtime files from the private
backup and upload those exact paths with the existing deployer. The additional
history RPC can remain unused, or an operator can drop precisely
`public.read_company_daily_history_v1(text)` after restoring the application.
No data migration needs reversal.

Evidence:

- `company_history_install_preview_20261118.json`
- `company_history_install_applied_20261118.json`
- `migrations/supabase/20261118_company_daily_history.sql`
- Original timing evidence in `HOSTING_DECISION_20261118.md`

The outdated order-book collection is a separate issue; this performance update
does not claim to restore fresh order-book captures.

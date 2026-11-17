# Additional refresh endpoints — 2026-11-16

Extracted the owner-specified source project's endpoint catalog and source definitions into an ignored private catalog: 29 tabular records, 31 URL observations, 26 distinct URLs across 15 hosts. These are discovery observations, not 26 verified APIs. The inventory includes documentation and product pages.

## Three additional observed and tested routes

| Operation | Response | Observed useful fields | Limits |
| --- | --- | --- | --- |
| Company statistics | HTML | Company name, exact ISIN, sector, capitalization, total shares, float, historical gross/net dividends and ex/payment dates | No financial effective date; sample dividend history stops at 2018; financial authority unverified |
| Daily price series | JSON | 243 timestamp/price pairs from November 17, 2025 through November 16, 2026 | Price series, not annual statements or accepted official-close evidence; current-day point can change |
| Intraday price series | JSON | Five timestamp/price pairs in the sample | No proven live latency or full-session completeness |

Request templates, endpoints, exact source instrument IDs, capture hashes and raw bodies are private. Templates resolve the application's actual base path and omit URL-rewritten session identifiers. The sampled company statistics were matched to the expected ISIN. This validates one instrument mapping; it does not establish mappings for every company.

The first diagnostic accidentally used the acquisition client's default POST instead of GET for page inspection. That was corrected without labeling its failures source outages. The first chart requests omitted the frontend application prefix; both corrected JSON routes then returned successfully. Original failed evidence remains private. Another source page returned HTTP 403 on the explicit GET and is not marked available for discovery. The separate frontend's small HTML response contained insufficient content to discover financial operations.

## Safe extraction

Added `tools/supplemental_company.py`: exact Decimal extraction of French formatted numbers; strict company-table and dividend-table layouts; expected-ISIN matching; preservation of old dividend dates; rejection of booleans, NaN/infinite values, ambiguous numeric formats, duplicate identity fields, invalid dates and fractional share counts. Capture time never supplies an unknown effective date, publication date or currency.

A live parse of the statistics page succeeded. Its stated share count was ten times the count implied by capitalization divided by the latest chart price. Since a common effective date and currency are not established, this is a corroboration finding, not permission to correct the share count or infer a replacement value. All extracted fields remain unpromoted candidates.

Six parser regression tests passed; compilation passed. Existing source files were not modified and no production company values were written.

## Fit for the refresh button

These routes add company identity/sector, share-count cross-checks, historical dividends and market-price cross-checks. They do not fill the current gap in reliable annual bank earnings, balance sheets or accounting scope. The existing annual API remains subject to period/unit/forecast validation. Nothing in this phase claims that a new annual-financial source was found or connects unverified values directly to production.

Private reusable request definitions: `private/additional-refresh-apis-20261116/recipes.private.json`. Raw captures and the original discovery remain in the owner-only additional-refresh-apis vault. The button's background request/status integration remains separate work.

# New financial-source research check — 2026-11-16

The `/mnt/shared/Share/studies/Coding/Codex/bourse_data` and previously reviewed `/home/redachen/studies/Coding/Codex/bourse_data` paths resolve to the same directory. Seventeen files were added or modified after the previous source review. They contain a new fundamentals research package, not just the earlier market-data work. Its source inventory is research; it did not claim fresh successful API replay.

## Fresh checks performed

| Data source role | Result in this environment | Use |
| --- | --- | --- |
| Official structured instrument page | Request failed with network timeout/failure | Promising embedded company identity, annual figures, ratios, dividends and capital events; not marked live-verified |
| Official daily-history JSON route | Request failed with network timeout/failure | Documented historical-contract lead; not marked live-verified |
| Primary FY2025 bank financial report | Downloaded PDF, 6,289,691 bytes; text/unit evidence checked | Four explicit bank profit/equity facts corroborated at the annual period and group/total level |
| Secondary bank financial-research page | Downloaded HTML; exact CIH ISIN/ticker checked | Financial-summary table, embedded structured JSON, share-count context and separate indicator series |

Source URLs, identities, raw evidence and complete request definitions remain private. No access-denial workaround or production update was performed.

## Useful new financial coverage

The primary bank report distinguishes group-owner profit, total consolidated profit, group equity and total equity. Four research candidates were matched to actual PDF table rows and the “thousands of dirhams” unit headers on physical PDF pages 95–97. Their decimal scaling was checked. First publication time and final publication approval remain unresolved. The source's historical structured summary combines group profit and total equity; copying that pair into group-owner ratios would mix attribution scopes.

The secondary bank page exposes a parseable JSON object directly in its HTML; no browser or guessed JSON endpoint was needed. Its metadata includes ticker, ISIN, sector, schema, currency, displayed update date and a latest-share field. The visible year-summary table produced 37 observations across 2016, 2017, 2018, 2019, 2020, 2021, 2024 and 2025: group profit, group equity, total assets, dividend per share and period share counts. Million/billion/per-share units were preserved explicitly. Rounded table figures remain marked rounded.

Twenty-four indicator series are also embedded. They include quarterly/cumulative series and trailing-twelve-month measures. They were not substituted for annual reported figures. The latest displayed share count stays separate from the year-summary count, with its corporate-action effective date unverified. A displayed page update does not date every financial input.

These are substantive additions for the bank-fundamental gap. They are not evidence that all banks or the entire company universe can now be synchronized safely. Other bank primary-report links and company mappings remain research leads until independently retrieved and checked.

## Retained results and integration state

A private immutable-input hash snapshot of the new API catalog, route additions and source registry was retained under `private/new-research-check-20261116/`. Primary and secondary candidate facts are saved separately there. Fresh raw responses and retrieval receipts remain in the owner-only new-research-check vault.

The standalone checks assert identity, PDF units, decimal scaling and unique targeted primary rows. Production company values were not changed; no mobile code was touched. The live button's protected background request/status connection remains unfinished. This check supplies new source material for that implementation; it does not claim the button has been deployed with fresh fetching.

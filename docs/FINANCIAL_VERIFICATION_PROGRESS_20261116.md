# Financial verification progress — November 16

## Evidence and trust boundary

Three fresh private fundamental captures (ADH, IAM, MUT) completed with 20 responses each and no transport errors. Their source still labels 2025 net profit as forecast. A fresh capture is therefore not evidence of reported 2025 earnings.

Added financial_evidence.py and tools/prepare_financial_review.py: exact decimal source facts, evidence hashes/capture timestamps, source-year labels and raw value paths. Forecasts are separate from reported-source labels. Missing units, consolidation scope and publication date remain unknown; integrity verification never enables publication. Actual pilots produced 280 reported-source facts, 24 forecast facts and 11 unavailable values. Candidate files stay in the owner-only vault, not runtime data.

Added primary_statement.py: strict extraction from explicitly labeled annual tables, matching issuer, page, scope context, year columns and KMAD unit header. Ambiguous rows, units and figures fail closed. Exact KMAD→MAD conversion is retained with raw header/row evidence. Six focused evidence/primary-parser tests passed. Extraction by itself is not automatic promotion authority.

## Primary-reviewed pilot correction

Independently re-fetched the previously reviewed primary report for T2S. Parsed 33 annual facts across 11 metrics/three years, with explicit consolidation or group-share scope. Verified the dated listed-security count separately against the approved report and prior reviewed listing.

Found the stored company mixed 2025 revenue/profit with a 2024 fiscal-year label and older equity. Applied a coherent primary-reviewed 2025 correction through the existing administrator RPC after rollback testing, row locking and concurrent-change checks. Private before-image and market_admin.financial_review_receipts preserve evidence and applied values. No personal portfolio or historical price records changed.

Ratios retain the application's documented conventions: EPS normalized by dated listed shares, ROE on closing group equity, FCF as operating plus investing cash flow. These are derived metrics, not falsely labeled issuer-reported metrics. Unsupported annual dividend and five-year-growth values were cleared rather than attributed to the new year. Publication date remains unknown; evidence capture and knowledge-availability times are truthful.

Live signed-in T2S page verified: “Exercice 2025”, EPS 9.06, no PHP fatal error. Database readback verified the applied fields. A literal UI-equity string check did not match its formatting and was not treated as proof; equity verification used exact database values against the primary evidence.

## Regression protection

Found an older automatic projection could refill NULL financial fields in a newer-year record. Added 20261116_protect_reviewed_financials.sql:
- Older or unknown fiscal periods cannot fill a newer-year financial gap.
- Explicit primary-reviewed records reject unreviewed automatic financial replacement, including NULL gap filling. Future authoritative reviews use the explicit reviewed path.
- Unreviewed companies retain their same-year/newer-year publication behavior; biography gap filling and evidence collection remain operational.
- Receipts distinguish actual stored fiscal year, incoming source year and review-required state.

Automatic approval review rejected the first proposal because integration coverage was insufficient and its NULL default could block too broadly. Corrected the default to explicit TRUE-only protection and tested the complete publisher body in a disposable PostgreSQL container with no network, host mounts or production credentials. Eight full-body period/protection cases, eight tampered-payload rejections and private-function access checks passed. External admission helpers were fixture dependencies; unchanged live admission wrappers were not reimplemented in that test.

The corrected deployment was approved and applied after exact live-source comparison. Deployment changed no company data, verified by before/after fingerprints. Production helper cases and readback passed. Evidence is in the owner-only financial-verification-20261116 vault and private task folder.

## Remaining work

- Primary-document discovery and review for ADH, IAM, MUT and remaining companies.
- Broader table layouts/currency-unit and accounting-scope support, plus statement revision/publication-date handling.
- A protected review/publication interface and scheduler integration for the new evidence workflow; current candidate preparation is an operator tool.
- Coverage and freshness reporting that distinguishes captured, corroborated and approved data. The company universe is not claimed fully verified.

No APK build or physical phone work required for this phase. New runtime schema changes are the financial-review audit table and automatic publisher guard; candidate/parser tools are local preparation tools, not a new unattended production publisher.

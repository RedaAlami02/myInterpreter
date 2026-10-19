# Website deployment — 19 October 2026

Published the Workspace website with French, English, Arabic and Darija, followed
by the reviewed T2S supplement. No cloud-function or Flutter deployment and no
Git push were performed. Existing private runtime configuration was preserved.

Deployment tooling now selects tracked runtime files only, includes locale JSON,
uses encrypted FTP, compares file contents, snapshots remote targets before any
write and verifies uploaded bytes. Research, tests and design screenshots are
excluded. Explicit paths cannot escape the repository.

Production exposed a partial cURL-multi implementation: initialization existed
but execution was disabled. Both database batches and chart enrichment now
fall back to sequential requests when any required operation is unavailable.
This preserves parallel reads on capable hosts. Chart enrichment on this host
can consequently be slower (T2S observed at approximately 13.5 seconds after
the main page); improving that requires a separate caching/performance pass.

Verification: PHP lint, catalog tests for all four locales, reviewed-disclosure
tests, sector tests, deploy-manifest tests, partial-cURL regression and read-only
query equivalence. Synthetic browser checks passed English/Arabic at seven
widths in both themes. Live English and Arabic T2S checks confirmed annual and
interim figures, dated ownership, charts, dark mode and no mobile overflow.
Live screener and dividends rendered populated tables; logged-out portfolio
rendered the login screen. No real account/trade submission was tested.
The screener initially still showed its pre-correction 10:49 ratio snapshot;
it reads stored price-job ratios, not the company table directly. It will pick
up the new annual basis on the next normal price-job run. No history was rewritten
and no broad market-refresh function was triggered just to update this issuer.

## Rollback material (local only, ignored, never uploaded)

Copies are retained under `private/deployment-backups/2026-10-19/`:

- `myinterpreter-deploy-5mg2v_9t`: website before language/design deployment.
- `myinterpreter-deploy-2wpapfhw`: before the T2S supplement.
- `myinterpreter-deploy-xpixzek3`: before hosted-cURL compatibility changes.
- `myinterpreter-deploy-qz_mrdes`: before final sector-label localization.
- `myinterpreter-company-7ct3b0k3pbj4fVP1mZ7`: original T2S public company record.

Each website backup lists newly introduced paths in `new-files.txt`. Backups
are private and are not part of Git. Restore only reviewed targets over the
configured encrypted connection. A Git revert alone does not revert the
Appwrite company record; restoring that record requires a separate reviewed
database patch. Historical price records were not modified.

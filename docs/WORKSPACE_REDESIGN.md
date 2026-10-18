# Workspace redesign — 18 October 2026

## Accepted direction

The user selected Workspace over the alternative prototype and approved both
light and dark modes. This supersedes the earlier, unconfirmed Atlas Ledger pilot.
Use horizontal navigation, cool neutral surfaces, restrained blue accents,
compact comparison tables and grouped metrics. Avoid glass, glow and decorative
entrance animations. Preserve semantic gain/loss colors and numeric signs.

## Implementation

- `core/theme.php` loads the local theme boot script and shared Workspace CSS.
- `assets/js/theme.js` applies the saved preference before body rendering,
  otherwise follows the device preference; toggling works even with storage
  blocked. Only the theme preference is stored. Charts retain their data and
  update their labels, grid and categorical colors with the theme.
- `assets/css/workspace.css` supplies both palettes, responsive top navigation,
  flat panels, tables, form/modal treatments and reduced-motion support.
- Shared navigation and index, portfolio, company directory/detail, screener,
  dividends, results and update pages use the same shell. The portfolio puts
  holdings before allocation charts. External Google font requests were removed.
- Existing uncommitted company-directory filters, portfolio sector allocation
  and screener refinements are preserved and included with their helper/CSS
  dependencies in the page-integration commit. No trade, dividend or permission
  rules are changed by the redesign.

## Verification

Run `node tools/test_workspace.mjs` with Node 22+, PHP and local Chromium.
It renders real index/portfolio templates with invented data, not a real account.
It checks both themes at 1365, 412 and 320 pixel widths, charts, portfolio tabs,
sector controls, submitter payload, preference persistence, system preference,
blocked-storage fallback, base text-token contrast and JavaScript exceptions.
Screenshots are generated under `design-review/screenshots/prototypes/`.
The browser may fetch existing public chart/icon libraries; no remote browser
service receives the application source or account data.

Optional read-only public-route checks:

```sh
php -S 127.0.0.1:8022
WORKSPACE_PUBLIC_ORIGIN=http://127.0.0.1:8022/ node tools/test_workspace.mjs
```

The public checks cover screener, company directory and dividends, including
filter/search state across theme switches. Run PHP lint on changed PHP files,
`php tests/sector_allocation_test.php` and `node tools/test_loading_ui.mjs` too.

## Limits and rollback

Authenticated backend requests and actual buy/sell submissions are deliberately
not exercised. Synthetic views cannot verify live permissions or every data
shape. Company enrichment, results and admin-only states need a final manual
check with a safe account. Token contrast checks are not a full accessibility
audit. This is not a new LCP audit or a field-performance claim.

Changes are split into an inert theme-foundation commit and a page-integration
commit. Revert integration first, then foundation if desired, preserving later
work. No push or deployment is part of this change. Do not deploy tests,
design-review artifacts or configuration secrets as web assets.

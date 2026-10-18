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

## Follow-up refinements — 18 October

- Kept the primary company description; removed the repeated enrichment description.
- Removed the company snapshot table and redundant portfolio snapshot table;
  historical records and the portfolio P&L chart are preserved.
- Replaced crowded canvas legends with keyboard/touch-operable HTML legends.
  Allocation circles are larger; slices below 5% omit their in-circle label but
  retain exact values in tooltips and percentages in the legend.
- RNPG, CA and EBE have plain-language French explanations on hover or focus.
- Removed update/schedule notices and the manual snapshot form/POST handler.
  Removed the portfolio query used only to display its last synchronization time.
- Responsive checks now include 320, 412, 768, 1024, 1365 and 1920 pixel widths.

The user approved reusing `benefits` for automatic weekday P&L after market
close, without adding a column. `cloud_function/functions/daily_pnl` implements
this independently of page visits, with private per-user permissions,
idempotent document keys and incomplete-valuation guards. See its README for
schedule, deployment and limitations. It is **not yet deployed or activated**;
no live schema or schedule was changed. Until deployed, the removed manual
control has no automatic replacement.

## Wide-screen and interaction follow-up

- Removed the 280px sector-list cap so all coverage rows use the card rather
  than being cut off behind an unnecessary internal scrollbar. The allocation
  track no longer stretches both slides to the taller slide's height.
- Financial canvases now have explicit fluid containers and disabled aspect
  ratio preservation. The shareholder donut has its own square container.
  Financial-chart animations are disabled to avoid stale plotted positions
  after resize/theme changes. Shareholder colors continue matching their list.
- Quarterly results are sorted by year and then quarter, not lexicographically
  by a quarter-first key.
- Frais/Équilibre controls animate the movement and appearance of table cells,
  expose `aria-pressed`, handle rapid toggles and respect reduced motion.
- The header restores the existing `favicon.svg` identity, centers navigation
  and aligns its bounded inner layout with content instead of separating the
  brand and account across the entire 2560px screen.
- Browser fixtures now execute the actual asynchronous company-chart script
  with invented API responses, cover admin navigation and a long sector list,
  and extend both-theme checks to 2560×1440. Checks include rendered bar spread,
  circle geometry, matching canvas/container width and logo loading.

English/Arabic research is in `docs/LOCALIZATION_PLAN.md`; translations are not
implemented in this refinement. The daily P&L job remains undeployed.

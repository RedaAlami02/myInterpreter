# Redesign Validation

Validated 2 September 2026 against local PHP server `http://127.0.0.1:8765` at baseline commit `a323dca`. The working tree contains the uncommitted pilot. No production write, deployment, release build, or protected-account access was performed.

## Preview Artifacts

| State | Desktop | Mobile |
|---|---|---|
| Before | [`screenshots/before/screener-desktop.png`](screenshots/before/screener-desktop.png) | [`screenshots/before/screener-mobile.png`](screenshots/before/screener-mobile.png) |
| Atlas pilot | [`screenshots/after/screener-desktop.png`](screenshots/after/screener-desktop.png) | [`screenshots/after/screener-mobile.png`](screenshots/after/screener-mobile.png) |
| Atlas table, horizontally scrolled | — | [`screenshots/after/screener-mobile-table.png`](screenshots/after/screener-mobile-table.png) |

Alternative direction previews remain available at [`screenshots/prototypes/atlas-ledger.png`](screenshots/prototypes/atlas-ledger.png) and [`screenshots/prototypes/night-desk.png`](screenshots/prototypes/night-desk.png).

## Checks Performed

### Rendering and data preservation

- Local PHP response: HTTP 200; public screener rendered 81 companies with 26 visible under the default PER `< 22` filter at observation time.
- Browser console errors: none. Uncaught page errors: none.
- Saved before/final HTML responses contained 1,053 `data-per`, `data-score`, `data-href`, and `data-val` attributes; the complete ordered attribute sets were identical. This verifies that the presentation change did not alter public row values or hooks during the stable comparison.
- Desktop and mobile screenshots were visually inspected after animations settled.

### Filters, sorting, and navigation

- Default PER sort: `aria-sort="ascending"`; first PER value `9.6009405002939`.
- Price sort: first click ascending with lowest visible value `24.5`; second click descending with highest visible value `6680`.
- Preset sequence: default `26`; PER ≤10 `3`; PER ≤10 plus score 4/4 `0`; all PER plus score 4/4 `2`.
- Manual PER `15` produced `10` visible rows.
- Keyboard `Enter` on the company sort button changed the column to ascending; the control accepts focus.
- Desktop row click and mobile company-link click both opened the row’s unchanged `infoAction.php?name=...` target.

### Narrow-screen behavior

- Tested at a 390×844 browser viewport (384 px document client width with scrollbar).
- Document width equaled client width: no page-level horizontal overflow.
- All five metric regions and all five navigation destinations remained inside the viewport.
- The actual table scroller measured 348 px client width versus 1,119 px content width.
- The 190 px company column remained fixed while the table moved 430–500 px (`sticky` position delta `0`). Long names wrap instead of consuming the full viewport.
- Score controls stayed on one row with 42 px-high touch targets.

### Static checks

- `php -l screener.php` — pass.
- `php -l core/sidebar.php` — pass.
- `git diff --check` — pass.

## Refinements Made During Inspection

- Corrected a mobile grid selector that initially stacked score buttons vertically.
- Constrained the sticky company column after a first scrolled screenshot showed it obscuring nearly all comparison values.
- Re-captured previews from a fresh default route so filter state from interaction tests did not contaminate the before/after comparison.

## Limitations and Remaining Risk

- The Atlas direction is Codex-recommended, not yet user-confirmed. Only the screener receives the new palette and structural treatment; concise shared navigation labels changed globally.
- Portfolio, transaction history, and fee/break-even presentation were audited from source only. No safe demo account was available, and known financial correctness defects remain untouched.
- No Android device or emulator was connected. Flutter received no changes and no visual validation.
- Native tooltip rendering, screen-reader announcements beyond DOM semantics, and multiple physical touch devices were not tested.
- The test environment lacks PHP’s DOM extension. A read-only regex attribute comparison replaced the planned DOM comparison; the browser behavior checks provide the stronger functional evidence.
- The existing full-row click remains easier to exercise on desktop; the sticky mobile company link is the reliable explicit target.

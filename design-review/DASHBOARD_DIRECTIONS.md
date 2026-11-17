# Dashboard Direction Studies

Five review-only dashboard directions adapt the user’s eight visual references to myInterpreter. All use illustrative Casablanca-market content and preserve the same core product concepts; no production route, data access, calculation, or application architecture was changed.

## Comparison

| Direction | Reference grouping | Strongest use | Main tradeoff |
| --- | --- | --- | --- |
| **01 Market Grid** | Temastock, images 1/4/5 | Screener, holdings, dense desktop workflows | Familiar and practical, but least distinctive |
| **02 Night Signals** | Dark portfolio/market, images 2/3 | Market overview, visual signals, presentation | Dark contrast and chart colors need strict accessibility control |
| **03 Lime Flow** | Fundcy, image 6 | Friendly overview, dividends, personal analytics | Rounded cards consume space on dense tables |
| **04 Research Desk** | ACRU, image 7 | Whole-product navigation and mixed research workflows | Requires careful simplification to avoid widget-dashboard clutter |
| **05 Ember Noir** | Added dark cash-flow reference | Monitoring, portfolio analytics, focused night mode | Less suitable for long daytime research sessions |

## Structural Recommendation

Use **Research Desk** as the strongest whole-project foundation: its sidebar, compact command bar, modular content grid, and mixed chart/table hierarchy can cover public market pages and protected portfolio tools. Borrow **Market Grid’s** table density for the screener and company history. Treat **Ember Noir** as a possible dark theme, not a separate architecture. Lime Flow is the most distinctive accent direction, while Night Signals is best reserved for a focused market-summary surface.

Before implementation, confirm the foundation and whether dark mode is required. Then inventory routes and shared components, define responsive navigation and design tokens, migrate one vertical slice (`dashboard.php` → `screener.php` → `infoAction.php`), and verify behavior before expanding. A rewrite of data access or financial calculations is not required for this visual restructuring.

## Artifacts

- `prototypes/dashboard-directions.html` — interactive five-direction switcher
- `prototypes/dashboard-directions.css` — isolated prototype styles
- `screenshots/prototypes/dashboard-{temastock,night,fundcy,acru,ember}.png`
- Matching `*-mobile.png` captures at a 390 px browser viewport

Validation: every direction rendered at desktop and mobile widths, produced no console errors, and kept document width within the 375 px mobile content viewport.

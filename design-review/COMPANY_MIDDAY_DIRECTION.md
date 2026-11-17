# Company Midday Direction

The user supplied five accounting-dashboard references on 2026-09-02 and asked to try their visual direction. The references establish a calm, monochrome interface: white canvas, black typography, thin gray rules, a compact icon rail, generous whitespace, dense tables, and restrained overlays.

The prototype adapts those principles to myInterpreter rather than copying the source product. It preserves the existing French financial vocabulary and representative Maroc Telecom content, then organizes the company page into:

- a global company search and compact navigation rail;
- a clear company identity and current quote;
- persistent tabs for overview, financials, valuation, dividends, and history;
- four high-priority metrics before secondary detail;
- a large price chart paired with valuation context;
- a conventional, scan-friendly financial table.

Green and red are reserved for meaningful financial states. Most hierarchy comes from type scale, spacing, borders, and alignment. Numeric values use tabular monospace styling. At 390 px, the rail becomes bottom navigation, metric cards form a two-column grid, tabs scroll horizontally, and wide data remains contained without page-level horizontal overflow.

Artifacts:

- `prototypes/company-midday.html`
- `prototypes/company-midday.css`
- `screenshots/prototypes/company-midday-desktop.png`
- `screenshots/prototypes/company-midday-mobile.png`

This is a review artifact only. Production routes, business logic, calculations, and data access were not changed.

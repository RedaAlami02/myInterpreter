# Design Specification

## Decision Status

**Pilot direction:** Atlas Ledger, selected by Codex on 2 September 2026 as a recommendation pending user review. This is not recorded as a user-confirmed choice. The working implementation is intentionally scoped to the public screener; shared rollout and Flutter translation wait for feedback on the light-versus-dark branch.

## Candidate Directions

### A. Atlas Ledger — recommended

[`screenshots/prototypes/atlas-ledger.png`](screenshots/prototypes/atlas-ledger.png)

A warm paper workspace with a deep green navigation rail, restrained gold identity detail, editorial heading, and compact ledger-like data table. It removes decorative glow/glass and gives the project a recognizable Casablanca-oriented identity without copying exchange or bank branding.

Why recommended:

- It most directly addresses the reported “AI-made” feeling rather than refining the same neon dashboard formula.
- Warm neutral content provides high contrast for long research sessions and separates product identity from semantic green/red values.
- Flat bands and rules make comparisons clearer than independent floating cards.
- It retains financial density and tabular alignment.

### B. Night Desk — fallback

[`screenshots/prototypes/night-desk.png`](screenshots/prototypes/night-desk.png)

A quieter version of the existing dark workspace: opaque charcoal surfaces, cyan accent, square controls, hairline dividers, and no ambient gradients. It has lower migration risk and may suit night use, but is less distinctive from the current application and common developer dashboards.

## Atlas Ledger Rules

### Identity and color

- Canvas: warm neutral `#f5f3ec`; data surface: `#fffef9`; primary ink: `#17231f`.
- Navigation/identity: deep green `#123c32`; interactive accent: `#08664e`; gold is limited to the brand marker/active navigation detail.
- Profit/loss and ratio states retain text/signs in addition to color. Do not use identity green alone to imply a financial result.
- Avoid ambient glows, glass blur, gradient buttons, and decorative shadows. One low shadow may indicate a principal data plane.

### Type and numbers

- Use an editorial serif only for top-level page titles; UI copy stays in the existing sans-serif stack.
- Use the existing monospaced stack for prices, percentages, ratios, timestamps, and counts.
- Body/secondary copy must not depend on very low opacity. Uppercase tracking is reserved for short labels.
- Show units in headers or labels (`Cours (MAD)`), and show signs on changes.

### Layout and components

- Lead with task and freshness context, followed by one connected metric band, controls, then comparison data.
- Prefer separators and grouped planes over a card per value.
- Default desktop radius is 0–6 px. Pills are reserved for real status or compact selection controls.
- Sorting controls are native buttons inside table headers with visible focus and `aria-sort`.
- On phones, metrics use a contained 1+2 grid, filter controls wrap inside the viewport, and wide comparisons scroll only inside the table with a sticky company column and visible instruction.

### Motion and states

- Keep entrance motion short and nonessential; honor `prefers-reduced-motion`.
- Freshness, “non traité,” empty, and error states must be expressed in text.
- Never invent data freshness or convert a last-known price into an implied live price.

## Pilot Scope

Implemented in `screener.php`, `assets/css/screener-pilot.css`, and concise shared navigation labels in `core/sidebar.php`. Existing data retrieval, thresholds, filters, sort column indexes, row links, and calculation functions remain unchanged.

## Acceptance Criteria

- Five summary values form an intentional layout at 1440 px and 390 px.
- No document-level horizontal overflow at 390 px; the comparison table itself remains scrollable.
- All filter presets and manual PER input update both result counts.
- Every table heading is keyboard-focusable; sort direction is visible and reflected in `aria-sort`.
- Default ordering remains PER ascending, and blanks remain last in either direction.
- Company links and row navigation continue to open the same detail route.
- The same runtime values are rendered before and after, except expected backend changes.
- PHP lint passes, and the page returns HTTP 200 without exposing credentials.
- The pilot is reviewed before Atlas rules are propagated to company, dividend, portfolio, or Flutter screens.

# Portfolio redesign comparison

Two isolated, interactive directions for the October redesign discussion.
Open `index.html` through the local PHP server; no PHP or backend is used by
these files. No existing production route or stylesheet was changed.

- **Ledger**: warm neutral palette, editorial title, left navigation, open
  sections, larger overview. A quieter reading-oriented direction derived from
  the earlier Atlas study, now applied to a portfolio.
- **Workspace**: top navigation, cooler neutrals, compact summary, bordered
  work areas, denser rows. Prioritizes repeated daily checks.

Both include light and dark palettes. Use the top comparison controls to switch
layout independently of theme. The chosen direction, theme, and view are kept
in the URL so a specific comparison can be bookmarked. They do not change any
preferences in the real application.

Portfolio and overview navigation, filtering, empty state, name/value sorting,
chart-period selection, synthetic CSV download, and an ephemeral note field
work. The overview adds a fictional market breadth summary and orders holdings
by daily movement. It is a dashboard sketch, not a complete replacement for
the current index page. Buy/sell, authentication, dividends, and company-detail
workflows are outside this design comparison.

All six companies, holdings, daily movements, and historical chart points are
invented. Current portfolio values and gains are computed from the fixtures;
the chart series is illustrative and ends at the same total. Nothing loads
from a real account, data service, external font host, or analytics service.
The note field is not saved or transmitted. CSV downloads are labeled fictional.

Validation: `node tools/preview_refresh.mjs` runs an isolated local Chromium
preview with no production data. It checks row count, search/empty state,
sorting, chart-period changes, and view switching, then captures all eight
direction/theme/viewport combinations. Desktop is 1365×900 and mobile 412×915;
all passed the document-overflow check. Tables scroll horizontally on narrow
screens and keep the company column fixed. Desktop and mobile screenshots were
visually reviewed. This is not a full accessibility or authenticated-flow audit.

Snapshots: `design-review/screenshots/prototypes/refresh-*.png`.
The runner injects local files into a localhost fixture and never sends source
to a remote browser. No deployment was performed. Design selection is pending.

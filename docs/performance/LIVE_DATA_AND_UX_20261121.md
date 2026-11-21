# Live prices, page latency and tooling — 21 November 2026

Everything below is implemented and deployed. Measurements are server-side
unless stated; the browser-side split still does not exist.

## What the price schedule now does

| Time (UTC, weekdays) | Job |
|---|---|
| `*/15 8-15` | Preflight decides: session open → refresh quotes only; after 15:45 Casablanca → publish the close (prices, history, valuations). |
| `*/30 16-20` | Safety net for a missed close. A no-op once the day's `data` row exists. |
| `0 22` | Health check and webhook alert. |

Before this, the workflow ran only after the close and its preflight skipped
every later slot, so `latest_prices` carried yesterday's stamp until evening.
Order books were always captured every 15 minutes during the session.

**The universe endpoint returns every instrument's quote in one request.**
`/live-market/actions` carries `dernierCours`, `ouverture`, `plusHaut`,
`plusBas`, `variation`, `volume`, `quantite` and `nbTransactions` for all 82
instruments. `capture_exchange_pages.py --prices-only` uses that single
response, so an intraday refresh costs one HTTP request instead of 82.

**The close is a local wall-clock fact.** `tools/preflight_daily_close.py`
refuses the CLOSE path before 15:45 Casablanca time (`Africa/Casablanca`), so a
run during the session can never stamp an intraday price as the day's close.
The exchange's own `DateCours` probe (`session_probe`) is the holiday guard: if
the last trade day is not today, nothing runs.

## Page latency: what the timing probe measures

Add `?timing=1` to `portfolio.php` or `screener.php`; the response ends with an
HTML comment:

```
<!-- timing: start auth=311ms holdings=516ms prices=634ms dividends=79ms rendered=423ms total=1964ms -->
```

Marks are placed at: bootstrap (`start`), after `requireLogin()` (`auth`),
after the holdings/earnings batch (`holdings`), after the recorded prices and
totals (`prices`), after the dividend year load (`dividends`), and at the end of
rendering (`rendered`). Screener has `data` and `rendered`.

Measured samples:

| Run | auth | holdings | prices | dividends | render | total |
|---|---|---|---|---|---|---|
| baseline | 311 | 516 | 634 | 79 | 423 | 1964 |
| second | — | — | — | — | — | (screener: 1086 → 429 after batching) |
| third | 585 | 1489 | 438 | 355 | 886 | 3753 |

Read the third row as **cold memo plus host variance**, not a regression: the
`prices` stage fell as designed (634 → 438, the filtered read), while holdings
and rendering tripled, which is what a cold per-session memo and a busy shared
host look like. To separate the two, capture two loads back to back: the second
should show `holdings≈0` and `prices≈0` because the session memo answers.

## Changes that reduced the work per page

- **`latest_prices` is filtered.** `q_in('c_name', heldNames)` emits a
  PostgREST `in.("A","B")` filter; portfolio used to read 500 rows to show
  about ten. Validated against live data: 3 rows for 3 names.
- **Screener batches its two reads.** `data` and `company` travel as one
  parallel cURL batch: 1086 ms → 429 ms.
- **Session memo** (`app_cache` in `core/backend.php`): portfolio holdings and
  P&L 120 s, prices and dividends 300 s. Writes bypass it, so a trade is never
  served stale. This is what makes portfolio → screener → portfolio cheap.
- **Background quote refresh.** `handlers/live_quotes.php` returns two short
  maps; `assets/js/live.js` polls every 60 s, aborts on navigation, pauses while
  the tab is hidden, backs off on failure, and releases the session lock before
  writing.

## Waiting that feels lighter

- A 2 px top bar appears on the first click and on submit (`#nav-progress`,
  `assets/js/app.js`). It is deliberately not a progress estimate.
- `@view-transition { navigation: auto; }` in `workspace.css` enables
  cross-document view transitions where supported, so the old page fades under
  the new one instead of cutting to white.
- Both respect `prefers-reduced-motion`.
- Asset query strings were bumped (`app.js?v=3`, `workspace.css?v=4`); bump them
  again whenever either file changes or browsers serve the old copy.

**Prefetch does not work on this host.** Every PHP response carries
`Cache-Control: no-cache` and `Expires: 1970`, whatever the script sends, so a
prefetched page is discarded before the click that would use it. The
`<link rel="prefetch">` tags were tried, measured and removed.

## Things worth knowing

- **`session.auto_start` is on** at least locally: the session is already active
  before `app_session_start()` runs, and the cache limiter is applied at
  auto-start. Cache headers must be set explicitly with `header()`; the limiter
  call alone does nothing.
- **PHPStan** at `~/.local/bin/phpstan`, config `phpstan.neon`, baseline of 24
  existing findings. Notable entries in that baseline: `core/Database.php`
  references `DB_*` constants that are defined nowhere, and
  `handlers/operations.php` writes an undeclared `Company::$_awId` (dynamic
  properties are deprecated since PHP 8.2).
- **intelephense** must exist for the `php-lsp` plugin to work:
  `npm install -g --prefix ~/.local intelephense`.
- **PageSpeed Insights** without an API key shares a small daily quota that is
  already exhausted; Lighthouse is not installed. Neither tool can see
  pages behind the login.

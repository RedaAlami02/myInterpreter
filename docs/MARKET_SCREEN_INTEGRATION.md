# Website and phone market screens — October 30

The existing website dashboard/selection pages and Flutter screener/detail now
have an **opt-in current market preview** connected to the full-row reader.
The setting remains off. This continuation changed local frontend code only;
it made no hosted requests, deployment, schedule, account or real-email changes.

## Implemented behavior

- `MYINTERPRETER_MARKET_PREVIEW` defaults false. PHP accepts the explicit process
  value `true`/`false` or a boolean `market_preview` in ignored local config.
  Flutter uses the corresponding boolean build define. Invalid settings fail
  closed; public-config writers keep elevated credentials out and preserve an
  existing website setting during public-key refresh.
- The website uses the existing authenticated v3 reader in `core/backend.php`.
  With preview selected, `index.php` and `screener.php` render the shared
  `core/market_preview_panel.php`. They skip legacy historical-price requests and
  the dashboard's old direct market-status request/config dependency. An unavailable
  preview stays unavailable; it never substitutes old history as a current price.
- The existing website navigation/theme remain. Cards show companies, MASI,
  prices, available ratios, search, explicit reference/quote basis, source date
  when known and separate receipt time. Reference trade dates stay unknown.
  MASI uses points and does not link to the company-only page. Website receipt
  times use the existing Casablanca formatter. New strings have local English,
  Arabic and Darija translations.
- `assets/js/market_preview.js` clears price **and ratio** values at expiry,
  and checks visibility/page restoration. It does not refresh in the background,
  issue trades or preserve expired numbers. Refresh is an explicit user action.
- Flutter adds an optional `MarketDisplayBackend`, implemented by the existing
  Supabase backend. Session/recovery restrictions apply. History and portfolio
  methods are unchanged. The preview flag enables only a read RPC, not collection.
- The Flutter screener reuses existing stock cards with quote/reference/date
  context, MASI and search. A failed/disabled feed gets a bounded unavailable
  state without raw errors or history fallback. Preview cards have no trade action.
- Flutter expiry timers clear prices/ratios and recheck on app resume. The detail
  page keeps its current card independent of historical loading/errors, labels
  the recorded history separately, uses index points in current/history/tooltips
  and suppresses index ratios/trade controls. Preview detail has no buy/sell form.
  Receipt/source-event times are explicitly labeled UTC on the phone.
- The PHP/Dart reader output now carries its already-validated public asset key
  and application expiry for the screens. Backend contracts and deployed function
  bytes did not change. No AppDocument/valuation conversion was introduced.
- The website deployment allowlist explicitly includes the new shared reader,
  panel and assets, including untracked runtime dependencies. Private evidence,
  credentials, tests and screenshots remain excluded. No upload was performed.

## Validation and corrections

| Check | Result |
| --- | --- |
| Complete Flutter suite | **80 pass**, including eight new market-screen cases |
| Flutter analysis | Clean; `dart format lib test` completed |
| Actual PHP controllers/templates with network stubs | Four cases pass for both pages |
| Public web/mobile build configuration | 11 cases pass |
| Website deployment publication boundary | Three cases pass |
| PHP v1/v2/v3 readers, i18n, changed PHP syntax, JS syntax | Pass |
| Chromium real-template checks | **16 layouts pass**: both pages, desktop/mobile, all four languages and both themes represented |
| Browser search, disabled feed, expiry and restored-page clearing | Pass; zero backend/source/external requests |

The new cases cover default-off/no-preview-RPC behavior; unavailable/error privacy;
no historical fallback; references with unknown trade dates; MASI; search;
independent expiry deadlines; resume/disposal; read-only navigation; and keeping
the current detail visible while historical data loads/fails. A synthetic
index-history case verifies points and absence of stock-trade controls.

The first failed-feed retry test exposed an unhandled source error. The screen
now catches read/parser failures into its unavailable result. Independent review
also caught index values labeled MAD and current detail hidden by historical
loading/errors. Both were corrected, including index history/tooltips and the
website's company-only index link. Test-fixture omissions and navigation-frame
timing were corrected before final passing runs.

The reviewer independently passed the four PHP controller/template cases and
syntax checks, inspected the Flutter cases, and found no remaining concrete
blocker. Independent Flutter execution was stopped by the sandboxed Snap launcher
before running tests; the complete 80-case execution is the primary agent's
recorded run. This is local implementation review, not hosted/device acceptance.

Private evidence: `private/market-screens-20261030/` contains final logs, browser
receipts and desktop/mobile screenshots. Browser fixtures use the actual PHP
templates and invented quotes, with runtime includes/network functions stubbed;
they load no credentials. The Flutter image is a widget-test geometry capture
using the test font/bundled dark theme, **not** a real-device visual acceptance.
An initial full-theme capture attempted an unavailable font under the test HTTP
stub; production styling was not changed to work around that test-only capture.

## Exact current state and remaining work

Both local website and mobile build-config preview settings were read back as
**false**, printing no keys. The last hosted checkpoint remains SQL016 + publisher
v8, disabled and empty, as recorded in
[APPLICATION_PRICE_PUBLICATION.md](APPLICATION_PRICE_PUBLICATION.md). No new SQL,
function deployment, source request or hosted data verification occurred here.
Models, genuine ledgers, recovered observations, timestamps and private portfolio
assignments were not modified. No APK release build, Git commit or push occurred.

Next steps:

1. Verify real user-driven signup/login/logout and confirmation/reset delivery;
   custom SMTP readiness remains unconfirmed. No passwords were guessed and no
   real account or email was created/sent by these tests.
2. Run newly scoped authenticated preview acceptance and actual device/hosted
   checks. Do not repeat/revive the consumed earlier trial or silently activate
   flags. The flag alone cannot start a collector or enable backend controls.
3. Finish existing new-listing/enrichment dispatch, verify fundamental/dividend
   publication, daily P&L and safe operational retention, then updated private
   worker distribution, budget checks and explicitly approved recurring schedules.
4. Review the exact frontend publication set before site/app cutover. Preserve
   unrelated dirty-worktree changes and source privacy. Existing completed
   backend installations must not be requested or applied again.

The owner-only administration navigation placement and private portfolio/account
assignment remain deferred as requested. Keep emails and provider identities in
ignored private handoffs. Prediction-model work remains a separate later phase.

# Interface languages

French (`fr`), English (`en`), Modern Standard Arabic (`ar`) and Moroccan Darija
(`ary`) are available through the header selector. English and French use LTR;
both Arabic variants use RTL. All four support light/dark themes.

## Architecture

`core/i18n.php` resolves an allowlisted query, session or cookie preference before
output, defaulting to French. The selector preserves scalar query filters.
The language cookie is HttpOnly, SameSite=Lax and Secure on HTTPS.

French source strings serve as message IDs. `locales/en.json` is the complete
English catalog; tests enforce matching keys and placeholders with the Arabic
base. `locales/ar.json` is the Arabic base;
`locales/ary.json` overrides conversational wording, retaining shared financial
terminology. Missing messages fall back to the original text. Use `te()` for
escaped HTML, `t()` for text, and named placeholders for dynamic values.
`core/theme.php` exports the local catalog as HTML-safe JSON; `assets/js/i18n.js`
provides the equivalent browser helper. No external translation service is used.

`assets/css/rtl.css` handles logical alignment and spacing. Financial tables,
numeric inputs, Latin identifiers and chronological chart axes deliberately
retain LTR ordering and Western digits. Company names/tickers are unchanged.
Internal IDs, filter values and financial calculations must never be translated.

## Verification

```sh
for locale in fr en ar ary cookie invalid; do php tests/i18n_test.php "$locale"; done
node tools/test_workspace.mjs
UI_LOCALE=en node tools/test_workspace.mjs
UI_LOCALE=ar node tools/test_workspace.mjs
UI_LOCALE=ary node tools/test_workspace.mjs
node tools/test_loading_ui.mjs
```

Set `WORKSPACE_PUBLIC_ORIGIN=http://127.0.0.1:8018/` for read-only public-route
checks against the local PHP server. Synthetic authenticated fixtures cover
portfolio, dashboard, login and company charts at seven widths (320–2560px),
both themes, invariant trade payloads and chart values. Inline scripts are
syntax-checked before browser tests. English, Arabic and Darija also passed public
screener, company directory and dividends checks at desktop/mobile widths.
English passed all seven fixture widths in both themes, with explicit English
heading/loading/period-label assertions and an HTTP preference-persistence check.

## Remaining review / deployment

Native-speaker review is still recommended for wording, financial help and
sentence fragments. Stored company descriptions remain in their original
language; unexpected backend error messages can fall back to French. Live
authenticated trading/admin writes were not exercised: tests use synthetic
accounts and do not submit real trades. This change adds no database schema or
scheduled job and does not deploy anything. The earlier daily P&L job remains
inactive until separately deployed/configured.

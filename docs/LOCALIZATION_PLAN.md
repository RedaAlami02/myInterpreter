# French, English and Arabic — structure proposal

Status: research/proposal only. No language switcher or translated production
interface has been introduced. French remains the existing language. Arabic
register needs confirmation (recommend Modern Standard Arabic, not Darija).

## Feasibility and scope

This PHP/JavaScript site can support three languages without rebuilding it or
duplicating its pages. It is a medium-sized change, not a risk-free switch:
strings live in templates, server messages and dynamically built chart panels.
Layouts and financial formatting also need review. Start with one fully
translated page before rolling out the rest; do not ship a header-only language
selector that implies the entire site is translated.

## Research: Arabic is more than alignment

W3C recommends declaring the page direction with `dir="rtl"` on the root HTML
element; language is separate, so use `lang="ar"` too. Use CSS logical properties
such as `margin-inline-start` and `text-align: start` instead of hard-coded left
and right. Arabic paragraphs can contain Latin names and numbers: isolate such
runs using `bdi` or explicit direction rather than reversing text manually.
Use `dir="auto"` for user-entered text with unknown direction. Keep Unicode
text in logical order.

Sources:

- [W3C: structural markup and RTL text](https://www.w3.org/International/questions/qa-html-dir.en.html)
- [W3C: inline bidirectional markup examples](https://www.w3.org/International/articles/inline-bidi-markup/bidi_examples.en.html)

## Recommended project architecture (engineering proposal)

1. A shared `core/i18n.php` resolves an allowlisted `fr`, `en` or `ar` locale
   before output. Use a persisted preference with French fallback. Keep locale
   independent from the theme and authentication; preserve query filters when
   switching languages. Validate the locale, never interpolate arbitrary paths.
2. Keep equivalent keyed catalogs in `locales/fr.php`, `en.php`, `ar.php`.
   Translate headings, navigation, forms, errors, empty/loading states, help,
   accessibility labels and financial explanations. Test matching key sets and
   placeholders. Escape output normally; translations are not trusted HTML.
3. Export only the page's needed translation strings as safe JSON for JS.
   Dynamic chart legends, trade feedback, filters and tooltips use the same keys.
4. Apply the root `lang` and `dir` server-side before paint. Audit Bootstrap's
   physical spacing utilities and custom layout rules; use its compatible RTL
   build where needed. Preserve the current light/dark design.
5. Use locale-aware date/number formatting without changing underlying numeric
   values or stored dates. Keep financial amounts/signs and ticker strings in
   isolated LTR runs. Agree on Western versus Arabic-Indic digits before rollout;
   for this Moroccan market UI, Western digits are a practical initial proposal.
6. Keep legal company names, ticker symbols and the logo unchanged. Company
   descriptions from stored data need separately reviewed translations; don't
   silently present them as translated or send private data to a translation API.
7. Mirror directional navigation where appropriate, not logos or charts blindly.
   Keep chronological chart axes predictable and explicitly test chart legends,
   numeric signs, percentages, currency and tooltip placement in RTL. Decide
   table column order deliberately rather than inheriting an accidental reversal.

## Rollout and verification

First migrate the shell plus the complete market dashboard, with native-speaker
review of Arabic financial terminology. Then portfolio/trades, company detail,
screener and dividends, followed by admin and error states. Review plural forms
and sentence placeholders instead of assembling translated sentence fragments.

Test each language × both themes × 320–2560px, including keyboard navigation,
touch, mixed Arabic/Latin company names, long labels, negative amounts, zoom,
form errors and authenticated/admin views. Verify trade payloads and calculation
results are identical across locales. Public language URLs and hreflang can be
added later if translated pages should be independently indexed; that is a
separate SEO/routing decision.

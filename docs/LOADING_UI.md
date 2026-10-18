# Loading feedback

The site renders its main pages in PHP before returning HTML. A full-page
skeleton cannot cover that initial server wait without changing the delivery
architecture. Keep the current page readable during navigation instead.

This update replaces the blocking blur/spinner overlay with a thin cyan activity
bar and a small French status message after 180 ms. The bar is indeterminate:
it does not claim a percentage or completion. No loading UI is shown on initial
page render, and navigation does not intercept focus or pointer input.

The financial-details section already fetches its content after page load. Its
existing loading placeholder now gets a static, theme-colored skeleton with
decorative shapes hidden from screen readers. The existing data-fetch success
and error behavior is unchanged. Skeleton labels contain no data-source names,
account information, or financial values.

Form feedback uses the actual submitter and keeps its name/value in the POST.
Further submissions of that form are prevented while feedback is pending.
Back/forward navigation restores labels and ARIA state. At eight seconds the
message acknowledges a slow response; at twenty seconds the feedback resets.
For forms it explicitly asks the user to verify the outcome before retrying.
This is UI protection, not server-side transaction idempotency, and a timed-out
indicator does not cancel a request or imply that a transaction failed.

Modified clicks, new windows, external links, anchors, downloads, cancelled
events, dialog forms, and the existing `data-no-overlay` opt-out are respected.
Reduced-motion users get a static bar. The dividend calendar now includes the
same shared script as the other public pages.

## Validation

Run `node tools/test_loading_ui.mjs` with Node 22+ and local Chromium. It serves
only a synthetic fixture on a temporary localhost port; it does not authenticate,
call financial services, or upload source to a remote browser. Fonts are excluded
from the fixture to avoid external font requests. It exercises 26 browser checks,
including submitter payload, pending submission protection, timers, Back/forward
reset, excluded links, reduced motion, theme colors, and mobile width. Screenshots
are generated in the system temporary directory as `loading-ui-desktop.png` and
`loading-ui-mobile.png` and contain only synthetic content.

The checks dispatch DOM events and simulated lifecycle events, with controlled
timers; they do not submit actual purchases, test a real authenticated session,
or exercise a real browser back-forward cache entry. Real data and credentials
were not needed for this change. The tests do not assert an LCP improvement:
this change improves feedback during waiting, not server response time.

The remote browser test was rejected by automatic approval review because it
would transfer local source to an external execution service. Validation was
completed locally instead. No remote-browser approval is required to use the
local runner.

## Design references

- [Nielsen Norman Group: Skeleton Screens 101](https://www.nngroup.com/articles/skeleton-screens/)
- [W3C: Respecting reduced-motion preferences](https://www.w3.org/WAI/WCAG22/Techniques/css/C39.html)

## Deployment and rollback

Runtime files: `assets/js/app.js`, `assets/css/global.css`, `dividendes.php`.
The tests, runner, and this document do not need to be deployed. No deployment
or push is performed by this update. Revert its dedicated commit with
`git revert <commit>` to restore the previous loading behavior while preserving
the earlier performance commit. Resolve or save overlapping local edits first.

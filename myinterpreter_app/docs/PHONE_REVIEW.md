# Phone review — 2026-11-09

Installed a debug copy under com.myinterpreter.myinterpreter_app.debug. Existing production package could not be updated because signing certificates differ; its data was preserved.

Confirmed startup reaches French login. Found signup-row overflow on the physical phone; changed Row to Wrap in source after installation. The installed debug APK still needs rebuilding to include that fix.

Further adjustments: replace default Flutter launcher/splash with approved branding; reduce excessive vertical whitespace on login; verify keyboard-open layout and larger system fonts. Debug build used existing local public configuration, whose enabled authentication features differ from the installed production app. Verify feature flags before release. Authenticated portfolio/market views were not inspected; user sign-in is required. No credentials entered, no financial writes performed.

## Follow-up fixes

Login now starts near the top with a bounded 440 px form, a shorter brand-to-form gap, and scroll access with the keyboard open. Signup copy wraps; the stay-signed-in label also wraps at enlarged system text sizes. Added email autofill and next-field keyboard action. Android icon uses the existing website favicon's m and gradient, with a dark branded launch background including Android 12+ splash resources. Debug builds use a separate application ID to preserve the production installation.

Analysis and 116 existing tests passed; a new regression test passed at 320×640, 150% text, and 240 px keyboard inset, for login and signup. Authenticated screens still require the owner's sign-in for physical-device verification; no credentials were entered by the agent.

## Authenticated test-account check

Successfully signed into the preview after correcting automated keyboard input (Android Select All was not honored; retries had appended password text). The supplied credentials were valid. Account identifier and credentials are deliberately omitted here.

Confirmed all four tabs open, empty portfolio guidance appears, market purchase form opens, and empty quantity is rejected without a write. T2S detail opens, but shows an English empty-history message and range controls; buy/sell labels are also still English. Found legacy market rendering treats MASI as an equity (MAD, ratios and purchase control), and uses excessive raw numeric precision. These require follow-up fixes. Trade form's keyboard/enlarged-font layout requires a scrollable container. No successful purchase or sale was submitted. Populated portfolio and realized-sale calculations were not physically tested.

## Second review — 2026-11-09

Fixed legacy MASI cards to use points, round prices to two decimals, and omit equity ratios and purchase controls. Trade sheets now scroll within the available keyboard viewport, use French controls and validation, offer a decimal keyboard, and normalize decimal commas before the existing idempotent submission flow. Chart periods wrap rather than clipping; missing history is explained in French. Single-point charts show a dot; straight segments avoid implying unobserved price excursions. History refresh waits for the request, and market preview retains available rows while refreshing.

Android production label is now myInterpreter; the separate debug installation is myInterpreter Preview. Existing cyan/dark m icon retained after visual inspection. It is supplied in all five Android bitmap densities; dedicated adaptive/monochrome launcher resources are still absent.

Flutter analysis passed and all 120 tests passed, including new regressions for legacy index controls, decimal-comma trades with keyboard and 150% text at 320×640, and empty-history layouts. No real financial writes were made. This does not establish production readiness across every device: populated portfolio/sale flows still need physical verification, and the app does not yet offer the website’s theme/language switches. Preview backend feature flags differ from production, so authentication/recovery and market-feed parity require release-specific verification.

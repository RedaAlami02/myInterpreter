# Mobile interface rules

Keep four stable destinations: Marché, Portefeuille, Dividendes, Stats. Preserve tab state and scroll position. Show portfolio value first, then indicative gain/loss. Reveal calculation explanations and position fees on demand; keep incomplete-estimate status visible.

Use French interface copy consistently. Do not translate company identifiers or database fields. Use app_colors.dart for the current palette; avoid importing the application entry point into screens. A full light theme still requires migrating these constants to semantic Theme colors across all widgets.

Use at least 12 logical pixels for metadata and larger text for essential values. Let text wrap; check narrow phones and enlarged system fonts before release. Give actions accessible labels and standard Material touch targets. Loading placeholders are static, announced once, and only replace content on initial loading. Keep previous data on refresh. Never show raw backend errors or invent financial values.

Keep financial calculations, missing-value handling and authorization independent of presentation changes. Test financial states, tab refresh, authentication and disclosures. Do not build a release APK locally.

## Validation of this pass
Flutter analysis and 116 regression tests validate this pass. Physical-phone visual inspection remains required. No release or deployment was performed.

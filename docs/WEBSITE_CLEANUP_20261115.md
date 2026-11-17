# Website cleanup and sync serialization fix — November 15

Deployed with private rollback copies and exact remote byte verification:

- Removed market-preview panels from index.php and screener.php. Dashboard header now leads directly into its existing metrics; removed dashboard quick actions. Screener starts with its summary counts, preserving an accessible, visually hidden page heading.
- Removed the screener's unused preview RPC request. Dashboard retains the snapshot read used by its other market indicators.
- Dividend timeline has arrows between stages, right/left on desktop according to text direction and downward on narrow screens. Short note: “Depuis 2022, 96 % des versements ont lieu entre mai et septembre.” Percentage remains dynamically calculated from recorded payments, not mislabeled as a percentage of companies. Translations added.
- Admin JSON serialization uses shortest-roundtrip float encoding locally and restores the hosting setting afterward. It does not round financial inputs or relax database numeric validation.

Diagnosis: the exact PHP bulk-sync payload construction reproduced 75 of 81 database scale violations with serialize_precision=17, while the six records without problematic numeric payloads passed. Current profile payloads passed SQL validation in rolled-back administrator-context transactions. After the client fix, all 81 payloads pass the numeric-scale audit under both -1 and 17 precision settings. No company updates were committed by these checks, and the production bulk sync was not silently rerun.

Verification: all applicable PHP fast suites passed; one legacy integration suite skipped. Added regression for decimal serialization and restoring the host setting. Signed-in live browser confirmed no preview/quick-action blocks, dashboard metrics in the requested order, screener beginning with 29 results / 81 companies, shortened dividend sentence, and responsive arrow direction without horizontal overflow at desktop and 390px widths.

Publication: private/website-cleanup-20261115/website/publication-receipt.json. Scope: nine runtime files (three pages, two stylesheets, admin client, three locale catalogs). No mobile changes or APK build required.

# Profile completion button — 2026-11-16

The administrator entry and destination now both say “Compléter les fiches sociétés”. The entry explains that application follows a preview and financial figures stay unchanged. The page explicitly uses saved profiles, without claiming a live collection or financial certification.

The preview shows captured dates in UTC, readable proposed field values, and the selected batch. Empty or malformed shareholder lists are excluded. No available proposal means no new biographical complement; it does not certify that a company is current. Existing values remain protected. A versioned session plan rejects previews created before these rules.

Results distinguish database-confirmed changes, values already present, and changes not applied. A transport error reports an unconfirmed outcome; it never claims that no write happened. A failed read hides the preview instead of suggesting a successful empty sync. Mutation remains administrator-only, POST-only, CSRF-protected and bounded to 25 companies.

Validation: planner and presentation regression tests; complete fast PHP suite (one legacy live-backend integration test skipped). The publication receipt and rollback are private under `private/credible-profile-sync-20261116/website/`. No mobile code changed.

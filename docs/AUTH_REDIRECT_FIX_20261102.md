# Email confirmation routing — November 2, 2026

Current priority: verification links before other migration work. Prediction
work remains excluded. No Appwrite access is permitted.

## Confirmed causes

Three bounded invalid-token probes confirmed the hosted default and both
explicit website/mobile destinations return HTTP 303 to localhost. No email was
sent, user created or valid token exchanged. Management Auth configuration GET
returns **403**; read/write access was requested and is pending. No Auth server
setting has yet changed. Do not claim the complete routing issue fixed.

The old Android release omitted `MYINTERPRETER_MOBILE_AUTH_LINKS=true`, leaving
the existing secure callback disabled; signup relied on the hosted Site URL.
Website email URLs also depended on request Host/HTTPS headers.

## Implemented and published

- Website destinations now use a configured public HTTPS application URL,
  independent of Host/proxy headers. Invalid configuration raises an error
  instead of silently dropping PKCE/redirect arguments. Signup/reset/resend
  retain their intent-bound PKCE and password-login/recovery separation.
- The public config writer upgrades/preserves `public_url`, administrator and
  existing gates. No elevated key is published.
- Four website files were uploaded with private rollback and exact FTPS
  readback. Anonymous login renders with HTTP 200 in Chromium. Python/curl
  connections were closed by the host; the browser check succeeded.
- Release workflow explicitly enables mobile email callbacks; the public build
  writer carries the strict boolean define. SDK auto-adoption remains off;
  the existing MobileEmailAuth/AppLinks implementation performs the exchange.

New APK: `private/auth-redirect-fix-20261102/mobile-apk/app-release.apk`.
Cloud run **41417855937 succeeded**. Branch `fix/mobile-email-redirect-20261102`,
commit `b9b2a729a70250fac1bc711a7a21e5c903c19c91`. Three screened files only;
no default-branch merge or dirty main-worktree commit. No local release build.
54,257,134 bytes, ZIP-verified, SHA-256:
`0363971374efcd4485ac6978951f3e0e035e0312c0822de52713b4ac20682646`.
Physical installation and real inbox/device acceptance are not yet verified.

## Hosted settings still required

Supabase → Authentication → URL Configuration:

| Setting | Required value |
| --- | --- |
| Site URL | `https://myinterpreter.infinityfree.me` |
| Additional Redirect URL | `https://myinterpreter.infinityfree.me/auth_callback.php` |
| Additional Redirect URL | `com.myinterpreter.app://auth/callback` |

Preserve other deliberate redirects and require email confirmation. Inspect
confirmation/recovery templates: their verification links should use the
server-generated `{{ .ConfirmationURL }}`, retaining per-request destinations.

The narrow private `configure_auth.py` is ready for `--prepare` and exact pinned
`--apply` after access exists. It creates a 0700 host backup, rechecks the pinned
unrelated security-settings hash before mutation, requires confirmation to remain
enabled and checks exact readback. Only known broken link targets are eligible
for correction; unsupported custom/OTP templates stop for actual review. Inspect
actual templates in the concrete prepared plan before applying. Never print full
Auth configuration or copy a secret-bearing backup into the shared worktree.

After applying, repeat all three invalid-token routing probes. Install the new
APK, request fresh links and test confirmation/reset in the same browser/device
that started the request. Old emails/APKs are not repaired retroactively.
If token access cannot be expanded, the owner can save these URL values in the
dashboard; probes can verify destinations without private settings access.

## Validation and evidence

PHP PKCE, auth-adapter and intent/recovery suites pass; changed PHP files lint.
15 public build-config tests, 37 isolated mobile auth/backend/widget tests and
five isolated management-plan tests pass. Independent review closed code/safety
findings. This is not actual SMTP/server-template/device acceptance.

Private receipts, scripts, rollback and probes:
`private/auth-redirect-fix-20261102/`. No genuine emails, accounts, financial
records, source archives, schedules or prediction assets changed.

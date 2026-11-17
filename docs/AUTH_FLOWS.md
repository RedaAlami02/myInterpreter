# Signup confirmation and password reset

Web flows are implemented and unit-tested; **email delivery is not verified**. Supabase's SMTP
settings remain unknown, so nothing here claims that an email reaches an inbox.

## Pages and endpoints

| Piece | Role |
| --- | --- |
| `index.php` login modal | signup with confirmation, password-reset request, resend confirmation |
| `auth_callback.php` | exchanges the emailed PKCE code and verifies identity |
| `auth_reset.php` | sets a new password from a recovery session |
| `SupabaseAppClient::recover` | `POST /auth/v1/recover` |
| `SupabaseAppClient::resendConfirmation` | `POST /auth/v1/resend` (type `signup`) |
| `SupabaseAppClient::exchangeCode` | `POST /auth/v1/token?grant_type=pkce` |
| `SupabaseAppClient::updatePassword` | `PUT /auth/v1/user` |

## Flow

1. Signup sends an S256 PKCE challenge and a `redirect_to` query parameter pointing
   at `/auth_callback.php`; the verifier, exact normalized email, flow and start
   time stay in the server session. Intents expire after one hour and are consumed
   once; starting a new intent invalidates the old one. If Supabase
   returns a session immediately (confirmation disabled), it is stored and the
   verifier discarded. With confirmation enabled the user sees a notice and can
   resend the email. Resend requires a matching unexpired signup intent and
   rotates its S256 challenge. Recovery and resend also put `redirect_to` in the
   URL query, matching the Auth protocol.
2. The emailed link lands on `auth_callback.php`, which accepts `?code=...` only.
   It exchanges the code server-side using the stored verifier and checks the
   returned identity against both the intent and `/auth/v1/user`, requiring a
   confirmed email. URL-fragment or POST bearer tokens are not adopted. The
   stored intent alone selects signup versus recovery. Responses use no-store
   and no-referrer headers; invalid URL credentials are cleared from history.
3. A confirmation redirects to the dashboard; a recovery link redirects to
   `auth_reset.php`, which requires a separate recovery session valid for at most
   15 minutes and remotely rechecks its confirmed identity. An ordinary login
   cannot authorize this page. It enforces 8–128 characters and matching
   confirmation, updates the password, clears the local session and returns to
   login. Success and cancellation attempt remote signout; remote revocation
   cannot be guaranteed if that request fails. Recovery never creates a normal
   application session or remember-me cookie.
4. Password reset requests always answer identically whether or not the address
   exists; no account enumeration, and no password is ever sent to the recover
   endpoint.

## Required Supabase settings (owner)

- Keep **email confirmation enabled**.
- Site URL: the site root. Redirect URLs must include the exact callback URL,
  e.g. `https://myinterpreter.infinityfree.me/auth_callback.php`.
- Keep the default email-template links (`{{ .ConfirmationURL }}`) so Supabase
  redirects to the callback. If a template is customised to send
  `{{ .TokenHash }}` straight to the site, server-side token-hash verification is
  not implemented yet; that template must be reverted or the flow extended.
- The hosted password policy must accept 8–128 characters.
- SMTP must be configured and delivery verified with an authorized test recipient
  before signup or reset is described as working. Opening a link in a different
  browser than the one that started the flow fails by design (PKCE).

## Mobile continuation — October 29

Opt-in Android confirmation, resend and password-recovery code is now implemented
and locally tested, including a controlled PKCE callback handler and temporary
recovery screen. It is disabled by default. See
[MOBILE_EMAIL_AUTH_HANDOFF.md](MOBILE_EMAIL_AUTH_HANDOFF.md) for exact contracts,
the build flag, tests, session boundaries and required hosted/device acceptance.

The custom callback `com.myinterpreter.app://auth/callback` has **not** been added
to the hosted redirect allowlist. No email was sent or existing user reset, and
no new APK was built. The existing web callback above remains separate.

## Remaining

- Mobile: SMTP, hosted allowlist, actual Android intent/device acceptance and
  reviewed opt-in enablement remain pending; no domain-verified HTTPS App Links.
- Delivery, callback redirects and the reset form are unverified on the hosted
  project.

## Verification

```
php tests/supabase_pkce_test.php
php tests/supabase_app_test.php
php tests/supabase_session_test.php
php tests/supabase_email_intent_test.php
php tests/supabase_portfolio_claim_client_test.php
php tests/render_workspace_fixture.php index fr
```

These use a fake transport and an invented session; they prove request shapes,
token validation order and page rendering, not email delivery.

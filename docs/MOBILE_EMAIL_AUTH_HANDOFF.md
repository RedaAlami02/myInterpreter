# Mobile email confirmation and password recovery — October 29

**November 2:** the release workflow now explicitly enables this implementation.
The corrected signed APK was built successfully (run41417855937). Hosted redirect
settings still reject the callback and need Auth-config permission. Read
[AUTH_REDIRECT_FIX_20261102.md](AUTH_REDIRECT_FIX_20261102.md) for current state;
the disabled-release statements below describe the earlier checkpoint only.

Implemented locally and tested. **Disabled by default; no emails were sent and no
hosted configuration, accounts or data were changed.** This checkpoint follows
`AI_MIGRATION_HANDOFF.md`; the website/app remain ahead of prediction work.

## Progress and actual verification

The website/mobile/backend migration is approximately **75% complete / 25%
remaining**. This is an engineering estimate, excluding prediction work and final
cloud-data recovery completeness. Passing local tests does not imply production
readiness.

| Check | Result |
| --- | --- |
| Current managed Python baseline | 188 tests passed; no worker code changed |
| Flutter analysis | Clean |
| Full Flutter regression suite | 65 passed: previous 42 plus 16 email-controller and 7 widget cases |
| Preserved original quote and depth diagnostic archives | Both files exist and match their previously recorded SHA-256 values |
| Dependencies | Offline resolution; existing app_links 7.2.2 became a direct dependency; no package version changed |
| Hosted auth, SMTP, device / APK build | Not exercised by this checkpoint |

Initial analysis caught two interface type checks and two test brace lint issues;
these were corrected before clean analysis and passing tests. Evidence and logs
are under ignored `private/mobile-auth-20261029/`. The worker baseline emitted
existing SQLite resource warnings and the deliberate duplicate-ZIP fixture warning;
all 188 tests passed. Those warnings were not hidden or treated as new failures.

## Implementation

- `lib/mobile_email_auth.dart`: project-scoped secure pending intent, explicit
  PKCE confirmation, reset and resend; remote account verification; bounded
  recovery session; safe cancellation and sanitized errors.
- `lib/backend_contract.dart`: optional `EmailAuthBackend` interface, separate
  from application data access. Existing fake/data backends need not implement it.
- `lib/supabase_backend.dart`: integrates the optional flow and blocks restore,
  reads, trades and ordinary sign-in during provisional exchange/recovery.
- `lib/backend.dart`: explicitly selects PKCE, keeps SDK automatic URL adoption
  disabled, and reads the build-only opt-in below.
- `lib/main.dart`: controlled Android cold-start / warm-link listener; duplicate
  callbacks are ignored. Post-frame navigation explicitly requests a frame so a
  link received while the UI is idle can still navigate.
- `lib/screens/login.dart`: opt-in forgot-password/resend actions and neutral
  request notice. Confirmation clears the password field.
- `lib/screens/password_recovery.dart`: matched-password form, explicit cancel,
  no route back to application data, and sign-in required after completion.
- `android/app/src/main/AndroidManifest.xml`: exact custom callback intent filter;
  Flutter's automatic deep-link routing disabled in favour of the controlled handler.
- Tests: `test/mobile_email_auth_test.dart` and
  `test/mobile_email_auth_widget_test.dart`.

All `lib/`, `test/` and `android/` paths above are under `myinterpreter_app/`.

## Contract and session boundaries

The single callback is `com.myinterpreter.app://auth/callback`. Only one nonempty
`code` query parameter is accepted, with bounded safe characters. Wrong scheme,
host/path, user-info, explicit port, fragment, duplicate/extra parameters and
implicit access/refresh-token URLs are rejected. URL fields cannot select an
account or a recovery intent.

A request must have started on this device within the previous hour. Only one
request is outstanding: sending a newer link supersedes the earlier verifier.
Pending intent, email and start time use project-scoped secure storage; no
password, email code or token is added to the pending record. The SDK's existing
project-scoped secure PKCE store holds its verifier. A pending request can survive
restart. A completed recovery session is memory-only and cannot survive restart.

After exchanging the code, the server's `/user` response must match the session
user ID and requested email and show a confirmed email. Recovery additionally
requires the recovery event recorded with the SDK's verifier. Every provisional
session has persistence disabled before exchange, including while the SDK emits
an auth event. Confirmation signs that session out and returns to password login;
it never assigns preserved portfolio records.

Recovery lasts at most 15 minutes. Expiry boundaries and local clock rollback fail
closed. Account data, trades, session restoration and ordinary password sign-in
are blocked until recovery finishes or is cancelled. Password update requires a
fresh `/user` identity check and 8–128 characters, then signs out. If remote
revocation fails after local cleanup, the UI returns to login with an explicit
unconfirmed-revocation notice. Unexpected upstream text is never rendered.

This is client-side separation, **not a server-scoped recovery JWT**. Supabase's
recovery token is an authenticated user session at the hosted service. Server RLS
continues to govern that user's access; the UI guard does not narrow token rights
outside the app. No database policy was weakened or changed.

## Opt-in and hosted acceptance still required

The build flag is `MYINTERPRETER_MOBILE_AUTH_LINKS=true`; it defaults to false and
is not added to normal build configuration or the release workflow. No existing
APK was rebuilt or replaced. The new Android filter is present in source, but
disabled builds perform no email callback exchange and hide the new actions.

Before any reviewed enablement:

1. Keep Supabase email confirmation enabled and verify SMTP delivery with an
   authorized recipient. Do not send unsolicited tests or reset real users.
2. Add the **exact** custom callback above to Supabase's redirect allowlist;
   preserve existing web redirect entries and the default ConfirmationURL templates.
   No allowlist or template was changed here.
3. Use a separate opt-in debug build for acceptance, retaining public client
   configuration only. Never build a local release APK.
4. On an Android device, test cold start, running-app callbacks, idle navigation,
   restart before/after exchange, expiry, newest-link behaviour, confirmation,
   reset, cancel, logout, remember preference and ordinary owner-isolated trades.
   Verify actual installed Android intent matching; widget streams do not prove it.
5. Custom schemes are not domain-verified Android App Links. PKCE rejects code
   exchange without the device verifier, but another installed app can register
   the same scheme and intercept navigation. Reviewed HTTPS App Links would need
   a controlled domain and signing-certificate association; those are not configured.
6. iOS is outside this checkpoint: there is no iOS app target or URL registration.
   Do not claim this Android manifest provides iOS callback support.

For protocol reference see the official
[Supabase PKCE flow](https://supabase.com/docs/guides/auth/sessions/pkce-flow) and
[password-based auth](https://supabase.com/docs/guides/auth/passwords) documentation.
Implementation details were verified against the installed gotrue 2.27.3 and
supabase_flutter 2.18.3 code, rather than assuming newer online SDK signatures.

## What still takes time

Most remaining work is connecting and accepting staged services in the actual
hosting environment: review and authorized SQL009–013/function deployment,
private pins/tokens, storage and Actions headroom, durable outbox destination,
real-session capture/timing, deliberate preview integration, SMTP/device acceptance
and reviewed website/APK cutover. These require evidence from hosted services;
more synthetic tests cannot substitute for it. Recurring schedules remain off.

Next work should follow `docs/DEPLOYMENT_PACKAGE.md`: prepare the scoped review /
installation set and verify prerequisites without deploying or enabling anything
implicitly. Preserve both deferred portfolio assignments and the later owner-nav
request. Never reconnect to Appwrite or resume model work instead of app tasks.

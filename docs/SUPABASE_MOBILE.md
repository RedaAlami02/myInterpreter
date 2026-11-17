# Flutter Supabase integration

Implemented and live-tested on 2026-10-24. Login, signup confirmation, logout,
market/history/dividend reads, private portfolio reads and atomic trades now use
an explicit application backend. The interface, financial rules and existing
Appwrite compatibility path are preserved. Production cutover has not occurred.

## Run the Supabase development app

From the repository root, using the existing ignored migration configuration:

```bash
python3 tools/write_flutter_build_config.py
cd myinterpreter_app
flutter run --dart-define-from-file=backend.local.json
```

The helper creates ignored `myinterpreter_app/backend.local.json`, requesting
mode 0600 and reporting whether the filesystem honors that permission.
It writes exactly three fields: `MYINTERPRETER_BACKEND`, `SUPABASE_PROJECT_URL`,
and `SUPABASE_PUBLISHABLE_KEY`. It rejects secret keys and malformed project URLs.
It never writes the database connection string or secret key, and its console
output contains status fields only. This shared project filesystem forces mode
0755 even after `chmod`; the file therefore contains public client settings only.
Actual Supabase migration secrets now live in private local storage (see below).
The public client configuration is already
prepared locally; no credentials need to be pasted into chat or shell arguments.

The publishable key is intentionally part of a compiled client; database grants,
RLS and the user's Auth token enforce access. Never replace it with a secret key.
Builds without a backend define continue using Appwrite. Supabase failures do
not trigger an Appwrite fallback or reuse an Appwrite login.

`backend.dart` selects the implementation. `backend_contract.dart` supplies
backend-independent user/document types and unchanged fee/tax constants.
`supabase_backend.dart` uses the official Supabase Flutter SDK. Existing Appwrite
calls are contained in `legacy_backend.dart`, which retains the former portfolio
write behavior during cutover; only the Supabase path has atomic/idempotent trades.

## Auth and data boundaries

- Signup respects email-confirmation settings. A confirmation-required response
  leaves the user at login with instructions; it does not fabricate a session.
- Confirm email in the browser and return to the app to sign in. Automatic
  callback/deep-link handling is deliberately disabled pending URL/platform setup.
  Production SMTP and a real inbox test remain required.
- Project-scoped Supabase sessions and PKCE verifiers use `flutter_secure_storage`.
  Choosing "Stay logged in" persists the session; opting out keeps it in SDK
  memory for this app run. This setting is separate from legacy Appwrite storage.
- Session persistence writes are queued so a delayed refresh cannot restore a
  persisted credential after the user opts out. Login explicitly persists before
  navigation; SDK Auth events persist later refreshes. Expired restored sessions
  refresh before remote `/user` validation.
- Logout clears local persistence. Remote revocation failure is reported; local
  cleanup failures prompt a retry. Already-issued access JWTs can remain valid
  until expiry, as described in the private portfolio documentation.
- Private table reads require a session and use the user's JWT. RLS applies even
  when a query omits or changes its owner filter. No secret key is used by the app.
- Trade requests contain only request UUID, side, company, quantity and price.
  Owner identity is derived inside the database. Decimal input strings survive
  without an intervening binary-float conversion into the RPC payload.
- A trade form retains its UUID and immutable payload after an uncertain response.
  Retrying the same submission is safe on Supabase. Changing inputs prompts the
  user to check holdings and deliberately start a new submission; it cannot
  silently change the meaning of an existing receipt.
- API exceptions are converted to fixed UI messages, with a small allowlist for
  actionable Auth failures. Previous raw user IDs, row dumps, stack traces and
  remote error logging have been removed from mobile screens.

The public-column allowlist is generated from the shared migration contract:

```bash
python3 tools/generate_flutter_market_contract.py          # regenerate
python3 tools/generate_flutter_market_contract.py --check  # detect drift
```

Reads allow only known tables/columns and supported query helpers. Chart limits
up to 2,000 rows are fulfilled through pages of at most 500 rows, preserving
filters, explicit offsets and stable ordering with an ID tie-breaker. Logical
requests are bounded at 10,000 rows. Unexpected columns are stripped, numeric
nulls and negative ratios survive, and duplicate IDs across a read cause an
explicit retry error. Offset paging is not a transactionally frozen snapshot.

No dividend or P&L formula was changed. In particular, the pre-existing PHP FIFO
versus Flutter historical-average realized-P&L difference remains; this work does
not establish identical realized P&L across clients.

## Verification and release configuration

Passed:

- `dart format lib test`.
- `flutter analyze --no-pub`: no issues. The vendored Appwrite SDK is treated as
  a separate package; its development tests/dependencies are not part of app
  analysis. Platform/build exclusions were added by the Flutter tool.
- `flutter test --no-pub`: **26 tests**, covering Auth confirmation, refresh,
  encrypted-storage policy, cross-project isolation, persistence races, paginated
  reads, nested annual/forecast/interim profiles, protected requests, decimal RPC
  payloads, redacted errors, shared dividend-period quality fixtures and UI flows.
- Four Python build-config tests, including file permissions, public-field
  allowlisting, secret-key rejection and CI operation without Python site packages.
- Shared contract generation check and workflow configuration structure check.
- Scoped credential scan of the mobile source/tests/new tooling: no current
  credential values or checked secret patterns found.

Explicit live SDK validation:

```bash
python3 tools/check_supabase_mobile.py --exercise-auth
```

The runner creates two synthetic confirmed accounts through the admin API,
sends no email, places test credentials in a mode-0600 temporary file and runs
`test/live_supabase_backend.dart`. It captures child output and emits only phase
names/aggregate status, preventing failed assertions from disclosing credentials.
It deletes only those accounts and dependent rows afterward.

The live run passed: anonymous market reads; 1,501 history rows across multiple
pages; real login; initially empty portfolio; repeated buy creates one ledger
record; second-user reads and explicit first-user filters reveal nothing; partial
and full sales preserve remaining average cost; repeated sale creates one sale;
real token refresh; persisted-session recovery with remote identity validation;
and logout. All temporary identities were deleted.

`.github/workflows/build.yml` now generates the same public config before its
release build. Manual dispatch can choose `appwrite` or `supabase`; a repository
variable `MYINTERPRETER_BACKEND` can select the push-build backend. Default remains
Appwrite. Supabase builds require GitHub Actions secrets `SUPABASE_PROJECT_URL`
and `SUPABASE_PUBLISHABLE_KEY`. They do not require database or secret API keys.
Those GitHub settings have not been changed and no workflow has been triggered.
Release builds remain on GitHub Actions; local validation uses debug mode only.

The first local Android build selected an incomplete Java 25 installation without
`javac`. A full Java 17 JDK was already installed. Retry locally with process-only
settings (no global Java configuration change):

```bash
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
GRADLE_OPTS=-Dorg.gradle.java.home=/usr/lib/jvm/java-17-openjdk-amd64 \
flutter build apk --debug --no-pub --dart-define-from-file=backend.local.json
```

The Java 17 debug compilation **passed**, producing
`myinterpreter_app/build/app/outputs/flutter-apk/app-debug.apk` (**166,411,794 bytes**).
All APK entries were checked against the configured server secret, database
connection string and database password: none were present. The expected public
client key was present. No release build, installation or distribution ran.

The build tool also installed its required Android SDK/NDK components. These are
local tooling caches, not changes to the hosted application or an Android release.

## Local credential storage

The shared project filesystem ignores restrictive `chmod` settings, including
on the pre-existing migration credentials. The Supabase credential file was
therefore moved, with byte-for-byte verification, to
`/home/redachen/.config/myinterpreter/credentials/supabase-migration.env`.
Its directory is mode 0700 and file is mode 0600. The ignored project path
`.supabase-migration.env` is now a symlink, preserving migration-tool access.
Keep the real credential file in that private location when editing; do not
replace the project symlink with a regular file on the shared filesystem.

No authorized Android device or emulator was connected during this check.

Still pending: device/emulator interaction and real OS keychain verification,
email confirmation with a real inbox, optional deep links, new administrator
setup and manual market-edit support, current quotes, managed Python jobs and
daily valuation writes, storage/backups, production-host checks and cutover.

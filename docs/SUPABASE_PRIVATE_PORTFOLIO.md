# Fresh-account authentication and private portfolio

October 25 recovery update: **both original users' 55 saved portfolio records**
are now restored and fully verified in separate admin-only staging datasets.
The user deferred assignment to each new login. No Auth identity was created or
assigned, and the application tables below were not populated or changed by
that staging import. See [PERSONAL_DATA_RECOVERY.md](PERSONAL_DATA_RECOVERY.md)
and `tools/restore_saved_portfolios.py`; preserve both owners and original dates.

Implemented and verified on 2026-10-24. The existing production site and Android
release still use Appwrite; deployment/cutover has not happened. PHP can now run
against Supabase through an explicit backend setting. Flutter integration is now
implemented and live-tested; see [SUPABASE_MOBILE.md](SUPABASE_MOBILE.md).

## Database boundary

`migrations/supabase/003_private_portfolio.sql` is installed in the configured
Supabase project. The migration can be repeated through its guarded runner:

```bash
python3 tools/migrate_supabase_portfolio.py       # local preparation summary
python3 tools/migrate_supabase_portfolio.py --apply
```

The runner validates the project-bound TLS connection, takes a migration lock,
refuses unrelated tables/functions/schemas, and applies everything in one
transaction. It never imports old private rows or changes existing account data.

| Table | Purpose | Client access |
| --- | --- | --- |
| `public.achats` | Buy ledger | SELECT own rows |
| `public.ventes` | Sell ledger | SELECT own rows |
| `public.portefeuille` | Remaining quantities and average-cost basis | SELECT own rows |
| `public.benefits` | Daily unrealized P&L snapshots | SELECT own rows |
| `portfolio_private.trade_requests` | Retry journal | No table access |

Owner IDs are UUID foreign keys to `auth.users`, with cascading cleanup when
that identity is deleted. Clients cannot insert, update, delete, truncate or
reassign owners directly. Anonymous access is denied. No new job/service-role
write permissions are granted yet; the valuation writer remains to be migrated.

Authenticated clients call `public.record_trade` with `p_request_id` (UUID),
`p_side` (`buy` / `sell`), `p_c_name`, `p_quantity` and `p_price`. Ownership comes
from `auth.uid()`; the RPC takes no owner argument. An invoker wrapper calls a
restricted definer implementation in the non-exposed `portfolio_private` schema.
Both functions pin an empty search path and use qualified table/function names.

The ledger, holding and retry journal change atomically. A per-owner transaction
lock serializes overlapping trades. An identical request UUID/payload returns
the original receipt; a changed payload under that UUID fails. Overselling,
unknown companies, non-finite/negative/zero quantities or prices, excessive size
and more than eight decimal places fail. Fractional quantities remain supported.

Remaining holdings use the apps' existing weighted-average cost calculation;
commissions, tax and the separate realized-P&L display algorithms are unchanged.
Recorded trades use the database timestamp. This initial RPC has no backdating,
editing or deletion flow. Existing PHP forms also only submit current trades.

## PHP configuration and sessions

Use `MYINTERPRETER_BACKEND=supabase`, `SUPABASE_PROJECT_URL` and
`SUPABASE_PUBLISHABLE_KEY` in the PHP environment, or copy
`config/supabase.example.php` to ignored `config/supabase.local.php` and fill it
locally. The default backend remains Appwrite. The web application never loads
`.supabase-migration.env`, the secret key or the database connection string.

`SUPABASE_ADMIN_USER_ID` (or `admin_user_id` in local config) must be the **new**
Supabase Auth UUID. Blank grants nobody web administrator status. Signup metadata
does not grant roles. The old Appwrite administrator ID has no Supabase meaning.
The existing manual market-edit handlers currently reject legacy writes in
Supabase mode; new authenticated market administration still needs implementation.

`core/SupabaseApp.php` uses the publishable key for Auth and the user's JWT for
private REST/RPC calls. It returns generic errors and a small allowlist of Auth
error codes, excluding raw remote messages. `core/Appwrite.php` provides the
temporary compatibility boundary for existing page read helpers, directing
public reads to `SupabaseMarketReader` and private reads through user RLS. Raw
legacy requests are blocked in Supabase mode; there is no backend fallback.

`index.php` supports signup, confirmation notice, login and logout. Signup does
not claim success as a login when confirmation is required. Production SMTP and
Supabase Site URL/redirect configuration still need setup and a real inbox test.
After confirming an email, return to the site's login form. Automatic email-link
session exchange, password recovery and mobile deep links are not implemented.

Access/refresh tokens are held in the server-side PHP session. "Stay logged in"
also sets a 30-day HttpOnly, SameSite=Lax refresh cookie scoped to the application
path. HTTPS requests set Secure. The actual host must expose its HTTPS state
correctly; reverse-proxy behavior has not yet been verified. Session IDs and CSRF
tokens rotate on login/refresh. Protected requests validate identity through
Supabase `/user`, refresh expiry proactively and distinguish unavailable Auth
from invalid sessions. Session persistence across requests and logout were tested.

Login, signup, logout and trade forms require a non-empty matching CSRF token.
Each rendered trade form has a random UUID for safe resubmission. PHP buy/sell
paths use the RPC in Supabase mode and retain their prior Appwrite behavior in
legacy mode. Shared session setup now requests HttpOnly/SameSite cookies.

Logout removes browser/local session credentials and revokes that refresh
session. Supabase access JWTs already issued can remain valid until expiry;
logout is not a claim of immediate revocation of every copied access token.

The public market adapter requires `migrations/supabase/market_contract.json` at
runtime. `deploy.py` now includes that exact JSON file once tracked, excluding
SQL migrations. The ignored backend selector is not automatically uploaded.
New runtime files must be included in the eventual reviewed deployment.

## Verification

```bash
php tests/supabase_app_test.php
php tests/supabase_session_test.php
php tests/supabase_market_test.php
python3 tools/check_supabase_portfolio.py
python3 tools/check_supabase_auth.py --exercise-auth
```

The SQL checker creates synthetic identities without emails/passwords/sessions,
exercises role/RLS and financial behavior, and always rolls its transaction back.
It covers two-owner isolation, anonymous denial, direct-write denial, snapshot
privacy, partial/full sales, fractional holdings, identical/changed retries,
overselling, invalid input and a holding-constraint failure **after** ledger
insertion to prove that partial writes roll back.

The live Auth checker creates two temporary confirmed test users through the
admin API, sends no confirmation emails, runs a localhost PHP server with only
public configuration, and deletes only those fixtures in `finally`. It passed:

- Real Auth login and refresh.
- PHP form login, CSRF rejection, refresh-cookie flags and logout redirect.
- A repeated PHP buy produces one ledger row and one correct holding.
- Anonymous and other-user REST reads reveal no private data.
- Two concurrent sells against one remaining share produce exactly one success,
  one rejection, one sale row and no remaining holding.
- All synthetic users and dependent rows are removed afterward.

Only aggregate booleans and error categories are printed. The final strengthened
SQL/Auth checks passed, and rerunning the schema migration also passed. Existing
15 Python Supabase tests and deployment manifest tests passed. PHP adapter,
session, market, i18n and calculation checks passed. Login/portfolio template
fixtures render without loading private data; the fixture was adjusted for its
evaluated template paths.

Remaining work: mobile-device validation, new administrator setup,
manual market-edit support, real email confirmation, production-host checks,
quote freshness, managed jobs/valuation snapshots, storage, backups and cutover.

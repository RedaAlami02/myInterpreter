# Administrator maintenance writes

The retired backend's direct document writers now throw. Migration
`011_admin_market_maintenance.sql` replaces the administrator paths that used them
with explicit, authorized Supabase operations. It is **staged only**: apply it,
seed the administrator and verify denial before relying on it.

## Authorization

The PHP site holds only the publishable key and the signed-in user's JWT.
`requireAdmin()` remains the UI gate, but it is not the authority. Both RPCs,
inside the database, require:

- `auth.uid()` is not null and `auth.role()` is `authenticated`;
- the caller has a row in `market_admin.admins`.

`market_admin` is a private schema with no API grants and no RLS policies; the
administrator's Auth UUID is seeded privately and must equal
`SUPABASE_ADMIN_USER_ID` in the site configuration. An empty table fails closed.
No restored row is rewritten by the migration; `public.data` only gains a nullable
`source` column.

## `public.admin_update_company(p_name, p_fields)`

Updates only the named existing company and returns
`{status: UPDATED|MISSING, name, fields}`. It never creates a company: a new
listing also needs a `format` symbol and a re-pinned publish mapping, so that stays
an explicit maintenance step.

- Editable: `bpa`, `dpa`, `tc5`, `roe`, `na`, `cp`, `beta_3y`, `beta_5y`,
  `revenue`, `ebitda`, `ebit`, `net_profit`, `fcf`, `net_debt`, `net_cash`,
  `total_assets`, `rev_growth_5y`, `rnpg_growth_5y`, `profit_margin`, `rnpg_est`
  (numeric), `fiscal_year`, `fy_est` (integer 1900–2200), `ext_name`, `sector`,
  `description`, `shareholders` (text).
- Rejected: `id`, `name`, `date`, unknown keys, wrong JSON types, non-finite or
  over-precise numbers, and fractions in `tc5`/`roe` (`0 < |v| < 1`), the error that
  formerly produced nonsense ratios.
- A JSON `null` clears a field; absent fields are untouched, as are `name` and the
  record `date`.

## `public.admin_record_operator_snapshot(p_fields)`

Inserts one explicitly operator-entered analysis snapshot into `public.data` and
returns its id. Allowed keys: `c_name` (must exist) and `pa` (required, `> 0`), plus
optional `cb`, `per`, `peg`, `pr`, `pb`.

- The row is written with `source = 'OPERATOR_ENTRY'`. Recovered and unclassified
  rows keep `source` null, so an operator analysis is never mistaken for a market
  capture. `MARKET_CAPTURE` is reserved for a future authorized collector writer.
- A missing or zero price writes nothing. `latest_prices` is never touched: an
  operator entry is not a current market quote.
- The existing `data` reads are unchanged, so the snapshot appears in company
  history as before.

## Verification

```
php -l core/SupabaseAdmin.php
php tests/supabase_admin_test.php
APP_TEST_DATABASE="host=/tmp/... dbname=... user=..." \
  python3 -m unittest tests.test_admin_market_sql -v
```

The SQL tests run only against an explicit `/tmp` Unix-socket database and roll
back every case. Applying `011` and seeding `market_admin.admins` are deployment
steps requiring review; the public client configuration never receives a
privileged key.

After applying it, re-run the database privacy check: the new schema must stay
unreachable to anonymous and ordinary authenticated callers, and `public.data`
must keep its existing authenticated read policy.

## Reviewed disclosure tool

`tools/apply_reviewed_company.php` applies one reviewed disclosure through the same
owner RPC. It signs in with `MI_ADMIN_EMAIL`/`MI_ADMIN_PASSWORD`, reads with that
user's token, refuses zero or duplicate company rows and any company whose stored
fiscal year is newer, writes a private rollback record, applies only changed
fields, and verifies the read-back. Without `--apply` it prints the change set and
writes nothing. It requires SQL011 and administrator membership; the tool itself
is never deployed.

```
MI_ADMIN_EMAIL=... MI_ADMIN_PASSWORD=... php tools/apply_reviewed_company.php AAA
MI_ADMIN_EMAIL=... MI_ADMIN_PASSWORD=... php tools/apply_reviewed_company.php AAA --apply
```

Company creation and dividend editing remain outside this tool.

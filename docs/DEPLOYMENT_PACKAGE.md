# Deployment package — review checklist

**Current live state:** bucket + SQL009/010/013 + three functions are installed
and verified disabled under the owner's scoped authorization. Read
[DISABLED_BACKEND_INSTALL_HANDOFF.md](DISABLED_BACKEND_INSTALL_HANDOFF.md) first.
The checklist below preserves earlier preparation; SQL011/012, enablement,
positive hosted acceptance, collection, schedules and cutover remain separate.

**Current reviewed revision:**
[DEPLOYMENT_REVIEW_FIXES.md](DEPLOYMENT_REVIEW_FIXES.md) records the five closed
findings, revision-2 bundle/pin and 347 passing cases. The first disabled
installation is limited to the bucket, SQL009/010/013 and three switched-off
functions. SQL011/012 require a separate owner-maintenance authorization; SQL012
has no global off switch. The complete order below describes the full package,
not permission to install every script in the first phase.

**October 29 measured review:** read
[DEPLOYMENT_REVIEW_HANDOFF.md](DEPLOYMENT_REVIEW_HANDOFF.md) for the concrete
41-file bundle, pinned hashes, 142 passing test cases and fresh hosted privacy /
capacity / timezone facts. The new tools only build/verify local artifacts and
measure read-only facts; they do not deploy or enable services.

**Nothing here is installed or enabled.** This consolidates the staged pieces for
the independent review and the scoped deployment authorization; it is not a
deployment authorization itself. Source-use approval is separate.

## What is being deployed

| Piece | Files | Purpose |
| --- | --- | --- |
| SQL009 | `migrations/supabase/009_private_object_archive.sql` | archive metadata, capacity reservations |
| SQL010 | `migrations/supabase/010_shadow_market_feed.sql` | shadow quote/index preview |
| SQL011 | `migrations/supabase/011_admin_market_maintenance.sql` | owner company writes |
| SQL012 | `migrations/supabase/012_portfolio_valuation.sql` | bounded daily valuation |
| SQL013 | `migrations/supabase/013_projection_publication.sql` | dividend/fundamental publication |
| Archive gateway | `automation/archive-gateway/*.ts` | write-only raw evidence |
| App publisher | `automation/app-publisher/*.ts` | shadow candidate publication |
| Projection publisher | `automation/projection-publisher/*.ts` | dividend/fundamental publication |
| Managed workers | `automation/managed/` | acquisition, derivation, outbox |

SQL002–006 and 008 were applied during recovery. SQL007 is superseded by SQL009
and is not installed. Apply the new SQL in the order above; SQL010 and SQL013
depend on SQL009, and SQL012 depends on SQL003.

## Preconditions

1. Independent review of the SQL, functions, tokens and control switches.
2. Explicit scoped deployment authorization and Supabase Management/CLI access.
3. Confirm the hosted project's timezone data. SQL010/012 use the database's
   `Africa/Casablanca` rules. October 29's actual hosted comparison passed all
   145 sampled instants. The earlier one-hour discrepancy involved an older
   local pg17 image; do not treat that as a current hosted failure. Repeat the
   read-only probe before later activation and after relevant timezone updates.
4. Measure current organization Storage and database usage; the guards
   (350 MB database, 750 MB objects, 350 MB projection guard) are ceilings, not
   free quota.
5. Confirm Actions/artifact headroom for the outbox fallback; artifacts count
   against the private repository's storage.
6. Keep the owner's **$0 additional-spend cap**.

Latest measured database size: 332,740,275 bytes; headroom before the staged
350 MB guard: 17,259,725 bytes. Existing project Storage has no objects/buckets.
Organization-wide available quota and long-term growth remain unverified.

## Storage

Create the private bucket `private-market-evidence` through the Storage API (not
SQL): private, no anonymous or app-user policies, 8 MiB per object. Verify an
anonymous read and an app-user read are both denied. The catalog rows are written
by SQL009 only; never insert or update `storage.objects` directly.

## Functions and secrets

Deploy each as its own function; merge `config.toml.example` into the bundle's
`supabase/config.toml`, leave `verify_jwt = false` and leave every `*_ENABLED`
variable unset until verification passes.

| Function | Bundle path | Secrets |
| --- | --- | --- |
| `private-market-archive` | `supabase/functions/private-market-archive/` | `SUPABASE_URL`, `SUPABASE_SECRET_KEYS`, `APP_ARCHIVE_WRITE_TOKEN_SHA256`, `APP_ARCHIVE_ENABLED` |
| `private-app-publisher` | `supabase/functions/private-app-publisher/` | `SUPABASE_URL`, `SUPABASE_SECRET_KEYS`, `APP_PUBLISHER_TOKEN_SHA256`, `APP_PUBLISHER_ENABLED` |
| `private-projection-publisher` | `supabase/functions/private-projection-publisher/` | `SUPABASE_URL`, `SUPABASE_SECRET_KEYS`, `APP_PROJECTION_TOKEN_SHA256`, `APP_PROJECTION_ENABLED` |

Three **distinct** 64-hex tokens; only their SHA-256 values reach the functions and
only the tokens reach the CI secrets. No project/admin key and no database URI in
CI.

Managed job variables: `APP_ARCHIVE_GATEWAY_URL`, `APP_ARCHIVE_WRITE_TOKEN`,
`APP_PUBLISHER_URL`, `APP_PUBLISHER_TOKEN`, `APP_PROJECTION_URL`,
`APP_PROJECTION_TOKEN`, `APP_PROJECTION_PROJECT_REFERENCE`, plus the encrypted
market/depth/dividend/fundamental configurations and publish profile. Every
credential is bound to `archive_project_reference` / the project hostname.

## Control rows (seed privately, switches off)

```
app_archive.control              enabled=false, max_storage_bytes, max_database_bytes
app_archive.providers            one row per feed_ namespace, enabled=false
app_feed.control                 enabled=false, provider_namespace, mapping_sha256, recipe_sha256
app_projection.control           enabled=false, provider_namespace,
                                 dividend_index_sha256, fundamental_index_sha256
market_admin.admins              the administrator's Auth UUID; must equal SUPABASE_ADMIN_USER_ID
```

Private artifacts: app mapping, dividend index, fundamental index, market/depth
configs, publish profile (mapping + approved pins). None of these belong in Git,
CI logs or public docs.

## Verification order

1. With everything disabled: every endpoint rejects, anon/app-user reads are
   denied, `market_admin.admins` access is denied.
2. Enable the archive path; store one synthetic archive; verify rejection paths
   (bad hash, replay, non-private bucket, quota).
3. Enable `app_feed`/`app_projection` pins; publish one reviewed synthetic
   projection and one shadow candidate; verify receipts, anti-older/equal-time
   behaviour, expiry and read denial for anonymous callers.
4. Verify SQL011/SQL012 with the administrator signed in: a denied write for
   another user, a bounded valuation, and a bounded status outside the window.
5. Only then a manual current-session trial. Recurring schedules, preview UI
   activation, email flows and APK/website cutover remain separate gates.

## Outbox fallback

Pending evidence on an ephemeral runner is lost when the runner is disposed.
`automation/managed/outbox_bundle.py` packs pending copies into one bounded
(≤ 64 entries, ≤ 64 MiB) private archive and restores them into a fresh 0700 spool
with exact hash checks:

```
python3 outbox_bundle.py unpack --bundle outbox.zip --spool "$APP_ARCHIVE_SPOOL_DIR"
python3 outbox_bundle.py pack   --spool "$APP_ARCHIVE_SPOOL_DIR" --output outbox.zip
```

Persist the bundle only in the private repository, with short retention, and
delete it once the entries are acknowledged. Confirm artifact quota before relying
on it; the tool refuses empty, oversized, non-private or conflicting spools and
never overwrites different bytes.

## Disable / rollback order

Set `APP_ARCHIVE_ENABLED`, `APP_PUBLISHER_ENABLED`, `APP_PROJECTION_ENABLED` unset,
then disable `app_archive.control`, `app_feed.control`, `app_projection.control`
and the provider rows. Do not delete evidence, archive metadata or published rows;
capacity guards stop writes without removing anything.

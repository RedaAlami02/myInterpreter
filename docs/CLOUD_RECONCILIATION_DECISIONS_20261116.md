# Cloud reconciliation — decisions, resources and runbook

Date: 2026-11-16
Branch: `feat/cloud-reconciliation`
Status: report-only cloud acceptance passed; share/annual writes enabled; the first
write attempt is blocked on a malformed `SUPABASE_SERVICE_ROLE_KEY`; the admin page
is deployed.

## Decisions

1. **Exchange is authoritative for current shares and corporate actions.** Its
   annual-row `nombreTitres` is a dated count and can be pre-split (MNG 10×,
   SOT 5×, T2S 2×). It is never copied into `company.na`.
2. **Current shares require two independent checks.** Accepted only from
   `shares_count`, capitalization ÷ price, and latest total capital ÷ current
   nominal. A conflict is quarantined; values are never rescaled.
3. **Share application is service-role only and touches only `na`.** The RPC
   re-validates the report hash, contract, freshness, evidence hash, company
   mapping and integer share count. It writes one audit row per report/company.
4. **Annual data is staged, not blindly published.** Only consolidated,
   non-financial, 2025, share-verified rows are staged. An administrator approves
   or rejects them on `reconciliation.php`. Annual approval never changes `na`;
   BPA is recomputed from the current share count.
5. **Anonymous reads were declined.** `20261116_public_market_anon_read.sql` is
   present but **not applied**. Market pages remain login-gated.
6. **Market health is read-only.** It reports stale/missing prices, stale or
   future fiscal years, missing shares, stale dividends and missing shareholders.
   It never writes the database.
7. **Recurring work is cloud-only.** GitHub Actions runs capture, reconciliation,
   health and PHP deployment. The Supabase SQL editor handles one-time schema
   changes; no local runtime is required.
8. **The private managed runner remains the live price writer.** The health audit
   observes its output; it does not replace it.

## Applied database change

`migrations/supabase/20261116_cloud_exchange_reconciliation.sql` was applied in the
Supabase SQL editor on 2026-11-16. Verification returned:

- `apply_exchange_share_reconciliation`
- `stage_exchange_annual_candidates`
- `read_exchange_annual_candidates`
- `apply_exchange_annual_candidates`
- `reject_exchange_annual_candidates`

Tables: `market_maintenance.share_reconciliations`,
`market_maintenance.annual_candidates`.

The anonymous-read migration was **not** applied.

## Cloud resources

| Resource | Name |
|---|---|
| Workflow | `.github/workflows/exchange-reconciliation.yml` |
| Workflow | `.github/workflows/market-health.yml` |
| Workflow | `.github/workflows/php-runtime-deploy.yml` |
| Branch | `feat/cloud-reconciliation` |
| Secrets | `SUPABASE_PROJECT_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_PUBLISHABLE_KEY`, `FTP_HOST`, `FTP_USER`, `FTP_PASS`, `FTP_REMOTE_PATH` |
| Variables | `EXCHANGE_RECONCILIATION_ENABLED`, `EXCHANGE_WRITES_ENABLED`, `EXCHANGE_APPLY_SHARES`, `EXCHANGE_STAGE_ANNUAL`, `MARKET_HEALTH_ENABLED` |
| Admin page | `reconciliation.php` |
| Report artifact | `exchange-reconciliation-<run_id>` |
| Health artifact | `market-health-<run_id>` |

### Cloud acceptance runs

| Run | Purpose | Result |
|---|---|---|
| `43963698404` | Full capture + reconcile, writes off | Success; 82 companies, 80 verified, 2 conflicts, 47 auto-candidates |
| `43965622668` | PHP deploy dry-run | Success; listed the five intended files |
| `43969311408` | Full capture + write | Cancelled; exchange capture stalled |
| `43971188197` | Apply existing report | Failed: `401 Invalid API key` |
| `43971466241` | Apply existing report after header fix | Failed: `INVALID_SERVICE_KEY_FORMAT` |
| `43971548526` | PHP deploy | Success; uploaded 5 files, remote backup created |

The apply-only workflow is `.github/workflows/apply-reconciliation.yml`; it
downloads the artifact from a prior report run and does not recapture.

### Service-key troubleshooting

The write RPC expects a **service-role** credential, not the publishable/anon key
and not the database password.

| Accepted form | How it is sent |
|---|---|
| New secret key `sb_secret_...` | `apikey` header only |
| Legacy `service_role` JWT `eyJ...` (three dot-separated parts, payload `"role":"service_role"`) | `apikey` and `Authorization: Bearer` |

The scripts reject with a precise code:

- `PUBLISHABLE_KEY_IS_NOT_A_SERVICE_KEY` — anon/publishable key was pasted.
- `SERVICE_KEY_ROLE_IS_NOT_SERVICE_ROLE` — a JWT for `anon`, not `service_role`.
- `INVALID_SERVICE_KEY_FORMAT` — truncated value, quotes/prefix, database password,
  or a different project's value.
- `401 Invalid API key` — value is malformed, revoked, or from another project.

Re-set it without printing it in chat:

```bash
gh secret set SUPABASE_SERVICE_ROLE_KEY \
  --repo RedaAlami02/myInterpreter
```

Paste only the key; no quotes, no `Bearer ` prefix, no trailing text. Then rerun:

```bash
gh workflow run apply-reconciliation.yml \
  --repo RedaAlami02/myInterpreter --ref feat/cloud-reconciliation \
  -f report_run_id=43963698404 -f apply_shares=true -f stage_annual=true
```

## Runbook

All commands use `--repo` so they work outside the git checkout.

```bash
# Report only (safe)
gh workflow run exchange-reconciliation.yml \
  --repo RedaAlami02/myInterpreter --ref feat/cloud-reconciliation

# Apply verified shares + stage annual candidates
gh workflow run exchange-reconciliation.yml \
  --repo RedaAlami02/myInterpreter --ref feat/cloud-reconciliation \
  -f apply_shares=true -f stage_annual=true

# Live freshness audit
gh workflow run market-health.yml \
  --repo RedaAlami02/myInterpreter --ref feat/cloud-reconciliation

# Publish the admin page and its core dependencies
gh workflow run php-runtime-deploy.yml \
  --repo RedaAlami02/myInterpreter --ref feat/cloud-reconciliation \
  -f apply=true
```

Inspect:

```bash
gh run list --repo RedaAlami02/myInterpreter --limit 10
gh run view <run-id> --repo RedaAlami02/myInterpreter
gh run download <run-id> --repo RedaAlami02/myInterpreter -D /tmp/evidence
```

Disable writes immediately:

```bash
gh variable set EXCHANGE_WRITES_ENABLED --body false \
  --repo RedaAlami02/myInterpreter
```

### Annual approval page

After `php-runtime-deploy.yml` publishes the page:

1. Sign in to the site as the administrator.
2. Open **Revue annuelle** in the sidebar, or `/reconciliation.php`.
3. Each group is one reconciliation report. Review the fields, warnings and
   evidence hash.
4. Select companies and click **Approve selected** to apply their annual fields,
   or **Reject selected** to dismiss them.
5. Approval never changes `na`; BPA is recomputed from the current share count.

If the page reports unavailable data, either the migration is not applied or the
signed-in account is not in `market_admin.admins`.

## Rollback and audit

- Every share application records `old_na`, `new_na`, `report_sha256`, `symbol`,
  `company_name`, `page_sha256` and `applied_at` in
  `market_maintenance.share_reconciliations`.
- To undo one row, set `company.na` back to `old_na` for that report/symbol.
- Annual candidates keep `status` (`PENDING`, `APPLIED`, `REJECTED`), `applied_at`
  and `applied_by`. A rejected candidate can be re-staged by a later report.
- `deploy.py` backs up every remote file it replaces to a private temporary
  directory before upload.
- Disabling `EXCHANGE_WRITES_ENABLED` stops all future writes without changing
  existing data.

## Open items

1. Re-set `SUPABASE_SERVICE_ROLE_KEY` with a valid service-role value, then rerun
   `apply-reconciliation.yml`.
2. Inspect the first share/annual RPC result and approve the annual batch.
3. Run market health and review stale-price/fiscal/dividend findings.
4. The admin page is deployed. Open it as administrator and confirm the staged
   candidates appear after item 1.
5. Merge the branch to `master` so the monthly schedule runs on the default
   branch. The local `master` is ahead of `origin/master`; merging the feature
   branch will also publish earlier local commits. Review that scope before
   merging, or ask for a clean feature-only branch.
6. Map the new NRJ listing before its shares/annual row can be applied.
7. Do not apply the anonymous-read migration unless public no-login pages become a
   deliberate product decision.

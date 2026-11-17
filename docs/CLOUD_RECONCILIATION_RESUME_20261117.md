# myInterpreter — resume state 2026-11-17

## Current state

- `master` includes PR #1 (`2a7ad1c`) and PR #2 (`02161a9`).
- Supabase reconciliation migration is applied. Functions verified:
  `apply_exchange_share_reconciliation`, `stage_exchange_annual_candidates`,
  `read_exchange_annual_candidates`, `apply_exchange_annual_candidates`,
  `reject_exchange_annual_candidates`.
- `SUPABASE_SERVICE_ROLE_KEY` is now valid. Apply run `43976007884` succeeded:
  - shares: 16 applied, 64 unchanged, 0 missing
  - annual: 47 candidates staged, 0 skipped
- `reconciliation.php` is deployed (run `43974269699`) and authorizes through
  `market_admin.admins`. The owner added their UID; the page shows the 47 candidates.
- Market health run `43976023261` succeeded and found:
  - 81 companies
  - **all 81 prices dated 2026-10-21** (26 days stale at run time)
  - fiscal years: 55×2024, 21 missing, 2×2021, 2×2023, 1×2025
  - dividends: 60 recent, 4 stale, 17 missing; 16 unconfirmed
  - shareholders missing: 7
  - `needs_attention`: 81
- Price migration `20261116_exchange_price_publication.sql` is **not applied**.
- DB URL validate-only run `44066487131` **failed**:
  `password authentication failed for user "postgres"`.
  The URL reaches `aws-0-eu-west-1.pooler.supabase.com` as user `postgres`; the
  Session-pooler username should be `postgres.<project-ref>`, or the password is
  wrong/not URL-encoded.
- `MIGRATIONS_ENABLED=true`; `SUPABASE_DB_URL` is set but invalid.
- `MARKET_HEALTH_ENABLED=false` (paused to avoid daily failures).
- Exchange schedule is enabled; `EXCHANGE_WRITES_ENABLED`,
  `EXCHANGE_APPLY_SHARES`, `EXCHANGE_STAGE_ANNUAL` are true.
- Anonymous-read migration is **not applied**; owner declined public access.

## Unfixed items

1. **Apply the price-publication migration.**
   - Preferred simple path: Supabase SQL Editor, paste
     `migrations/supabase/20261116_exchange_price_publication.sql` from `master`.
   - Or fix `SUPABASE_DB_URL`:
     - Supabase → Connect → **Session pooler** URI.
     - Username must be `postgres.<project-ref>`.
     - Password is the database password, URL-encoded (`@`→`%40`, `#`→`%23`,
       `%`→`%25`, `/`→`%2F`, `:`→`%3A`).
     - `gh secret set SUPABASE_DB_URL --repo RedaAlami02/myInterpreter`
     - Validate: `gh workflow run apply-supabase-migration.yml --repo
       RedaAlami02/myInterpreter --ref master -f apply=false`
     - Apply: same command with `-f apply=true`.
2. **Publish current prices** after the migration:
   ```bash
   gh workflow run apply-reconciliation.yml \
     --repo RedaAlami02/myInterpreter --ref master \
     -f report_run_id=43963698404 -f publish_prices=true
   ```
3. **Re-run market health** and confirm `price_stale` drops from 81:
   ```bash
   gh workflow run market-health.yml \
     --repo RedaAlami02/myInterpreter --ref master
   ```
4. **Re-enable the daily health schedule**:
   ```bash
   gh variable set MARKET_HEALTH_ENABLED --body true \
     --repo RedaAlami02/myInterpreter
   ```
5. **Annual approval** of the 47 staged candidates. See the guide below.
6. **Review the remaining 35 companies** not in the auto-candidate list:
   7 banks, 5 insurers, 16 standalone accounts, 5 stale, 2 conflicts (SNA, NRJ).
7. **Historical `data` and ratios are still frozen at 2026-10-21.**
   The price publisher updates only `latest_prices`. A separate `data`/ratio
   publisher or activation of the private managed runner is still needed.
8. **New NRJ listing** has no app company mapping; add it before applying its
   shares/annual row.
9. **Legacy admin pages** (`Update.php`, `results.php`) still compare the UID in
   `config/supabase.local.php` (`admin_user_id`). Update it only if those pages
   also return 403. `reconciliation.php` does not need it.
10. Do not apply `20261116_public_market_anon_read.sql`.

## Annual review page — what it means

Each row:

| Column | Meaning |
|---|---|
| Symbol / Company | Exchange ticker and company name |
| FY | Latest annual exercise; these are 2025 rows |
| Fields | Proposed annual values |
| Warnings | Validation notes; `DATED_BEFORE_LATER_CAPITAL_ACTION` is expected |
| Evidence | Prefix of the exchange page SHA-256; full hash is in the artifact/DB |
| Report | Hash of the whole reconciliation report; all rows in a group share it |

Field units:

- `cp` — group/reported equity, **MAD absolute**
- `bpa` — earnings per share, **MAD per share**
- `roe` — return on equity, **percent**
- `revenue` — revenue/PNB, **millions MAD**
- `net_profit` — net profit, **millions MAD**
- `profit_margin` — net profit / revenue, **percent**

Warnings to interpret:

- `DATED_BEFORE_LATER_CAPITAL_ACTION` — the annual row is from before a 2026
  capital action; the current share count is already stored and BPA is recomputed
  at approval. Usually safe to approve if the figures look sane.
- `BANK_PROFIT_GROUP_OVER_TOTAL_EQUITY`, `INSURER_SCOPE_REVIEW`,
  `STANDALONE_ACCOUNTS`, `SHARE_ROW_ANOMALY`, `CURRENT_SHARE_COUNT_CONFLICT` —
  these are not in the 47 auto-candidate list; they belong to the 35 review cases.

Decision checklist:

1. Revenue and net profit signs/magnitudes are plausible versus the prior year.
2. `bpa` roughly equals `net_profit × 1,000,000 / current shares`.
3. `roe` roughly equals `net_profit × 1,000,000 / cp × 100`.
4. Equity is positive unless the company is known to have negative equity.
5. If a figure contradicts a known issuer report, reject and check the issuer PDF.
6. If only `DATED_BEFORE_LATER_CAPITAL_ACTION` is present and figures are sane,
   approve.
7. Select rows and click **Approve selected**; this applies annual fields only,
   never the share count, and recomputes BPA from current shares.
8. **Reject selected** removes rows from the queue; a later report can re-stage them.

The page stages only **47** auto-candidates: consolidated, non-financial, 2025,
share-verified. It does not include banks, insurers, standalone-account companies,
stale years, or conflicts.

## Key run IDs

| Run | Purpose | Result |
|---|---|---|
| `43963698404` | Full exchange capture + report | success, 82 companies |
| `43976007884` | Apply shares + stage annual | success, 16 applied / 47 staged |
| `43976023261` | Market health | success, found all prices stale |
| `43974269699` | Admin page deploy | success |
| `44066487131` | DB URL validate-only | failed, password/user wrong |

## Short resume prompt

> Resume the myInterpreter cloud reconciliation. Read
> `/tmp/myinterpreter_resume_20261117.md`. First fix/validate the Supabase
> `SUPABASE_DB_URL`, apply the price-publication migration, publish current
> prices, rerun market health, then explain and process the 47 annual candidates.
> Do not apply anonymous reads.

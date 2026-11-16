# Exchange reconciliation — 2026-11-16 baseline

## What this adds

`automation/managed/exchange_reconciliation.py` and `tools/reconcile_exchange.py`
compare a snapshot of Bourse de Casablanca instrument pages with saved application
company rows. The tool is read-only: it writes a JSON, CSV and Markdown report and
never contacts the database.

The exchange is authoritative for identity, current shares, price and corporate
actions. Its annual-row `nombreTitres` is a **dated** count and can be pre-split;
it is never used as the current share count. Current shares are accepted only when
at least two independent checks agree:

1. exchange `shares_count`;
2. `capitalisation / price`;
3. latest total capital / current instrument nominal.

Annual-row share counts are adjusted by their implied nominal before comparison.
A pre-split row is a note, not an error. A row that still disagrees after
adjustment, with no later capital action, is quarantined.

## Live baseline (82 actions on 2026-11-16; 81 in the October comparison)

Snapshot: 82/82 pages parsed. The saved-baseline comparison below uses the
81-company October export; the live capture found one new listing, NRJ.

| Result | Count |
|---|---:|
| Current shares verified | 80 |
| Current shares conflict | 2 |
| Current shares insufficient | 0 |
| Latest annual row 2025 | 77 |
| Annual row stale (before 2025) | 5 |
| Unexplained annual-row share anomaly | 0 |
| Ready for annual review | 75 |
| Quarantine | 2 |
| Proposed share-count updates vs saved app rows | 6 |
| Companies with a newer annual row than the saved app row | 77 |
| Annual auto-candidates (consolidated, non-financial, 2025) | 47 |
| Bank review | 7 |
| Insurer review | 5 |
| Standalone-accounts review | 16 |
| Stale review | 5 |
| Conflict review | 2 |

The 47 auto-candidates are the path to a quiet annual cycle: their exchange rows
are consolidated, current (2025), non-financial and share-verified. The remaining
35 companies have a real reason to be looked at: bank/insurer scope, standalone
accounts, stale year, or a capital-history conflict. This is the “once a year”
review set, not a per-refresh correction queue.

### Six saved share counts that are stale

| Symbol | Saved | Current | Ratio |
|---|---:|---:|---:|
| ATH | 50,294,528 | 54,140,578 | 1.0765 |
| BOA | 215,786,000 | 225,404,715 | 1.0446 |
| CDM | 10,881,200 | 11,626,499 | 1.0685 |
| CIH | 31,497,300 | 38,641,338 | 1.2268 |
| SAH | 4,116,870 | 5,341,874 | 1.2976 |
| T2S | 21,785,174 | 22,584,118 | 1.0367 |

These are the first safe automatic updates: the share count is triangulated, and
the change is explained by a dated corporate action.

### Pre-split annual rows (do not treat as current shares)

| Symbol | Row count | Split factor | Adjusted | Current |
|---|---:|---:|---:|---:|
| MNG | 11,864,676 | 10× | 118,646,760 | 118,646,760 |
| SOT | 7,606,728 | 5× | 38,033,640 | 38,309,500 |
| T2S | 9,270,270 | 2× | 18,540,540 | 22,584,118 |
| DLM | 1,250,000 | 3.33× | 4,166,667 | 1,750,000 (stale 2021) |

MNG and SOT are internally coherent pre-split rows, not corrupt values. A pipeline
that copies `nombreTitres` into `company.na` would create a 10× or 5× error.

### Quarantine

**SNA (Stokvis Nord Afrique)** — the 2024 capital action records 353,903,000 MAD
at a nominal of 20, while the 2025 annual row records 176,951,500 MAD at the
current nominal of 10. The two bases do not reconcile. Current shares remain
verified by capitalisation / price, but the capital history needs a primary check.

**NRJ (JET ENERGY)** — new 2026 listing. Current shares 13,125,000 are verified by
capitalisation / price, but the capital/nominal check is 20% off and the 2025
annual row disagrees after split adjustment. The instrument needs a listing and
primary-document check before any annual auto-apply. It is not mapped in the
application yet, so the share RPC reports it missing rather than guessing.

### Stale companies

DIS (2011), DLM (2021), IBC (2021), INV (2023), SAM (2014). No newer annual row is
published in the exchange payload. Do not relabel their old figures as current.

### Scope warnings

- 7 banks: `capitalPropre` is used with group-attributable net profit; the exchange
  does not establish group versus total equity. Annual review required.
- 4 insurers: scope review required.
- 20 companies report standalone accounts (`compteConsolide = false`).

## How to run it

The cloud workflow is the primary path; the commands below are for optional local
inspection or reproduction.

```bash
python3 tools/reconcile_exchange.py \
  --snapshot /path/to/exchange-snapshot.json \
  --companies research/prediction_model/raw/company.json \
  --format research/prediction_model/raw/format.json \
  --pages-dir /path/to/exchange-pages \
  --out-dir /private/path/report-YYYYMMDD
```

Outputs: `reconciliation.json`, `reconciliation.csv`, `reconciliation.md`.
The output directory must be new; the tool refuses to overwrite evidence.

### Share-count applier (dry-run by default)

`tools/apply_reconciliation.php` reads the report and writes **only** `company.na`.
It refuses quarantined or unverified rows, backs up the current row, reads back the
result, and appends an audit event.

```bash
# Preview the six updates
php tools/apply_reconciliation.php \
  --report private/exchange-reconciliation-20261116/report/reconciliation.json \
  --symbols ATH,BOA,CDM,CIH,SAH,T2S

# Apply explicitly, with an administrator session
MI_ADMIN_EMAIL=... MI_ADMIN_PASSWORD=... \
php tools/apply_reconciliation.php \
  --report private/exchange-reconciliation-20261116/report/reconciliation.json \
  --symbols ATH,BOA,CDM,CIH,SAH,T2S --apply
```

Backups and `applied.jsonl` stay under the ignored
`private/exchange-reconciliation-20261116/` directory. The tool never updates
annual financial fields; those remain a review decision.

Run the focused tests:

```bash
cd automation/managed
python3 -m unittest discover -s tests -p 'test_exchange_reconciliation.py' -v
```

## Cloud operation (no local runtime required)

The workflow is `.github/workflows/exchange-reconciliation.yml`. It runs entirely on a
GitHub-hosted runner:

1. captures the live exchange universe and 81+ detail pages;
2. reconciles them and uploads the report artifact;
3. optionally applies verified shares through a service-role RPC;
4. optionally stages annual candidates for the admin review page.

Triggers:

- **Manual:** Actions → *Exchange reconciliation* → choose apply/stage and optional symbols.
- **Scheduled:** first of each month at 06:17 UTC, only when the repository variable
  `EXCHANGE_RECONCILIATION_ENABLED` is `true`.

Required repository configuration:

| Name | Kind | Purpose |
|---|---|---|
| `EXCHANGE_RECONCILIATION_ENABLED` | variable | Allows the monthly schedule |
| `EXCHANGE_WRITES_ENABLED` | variable | Master switch for any database write |
| `EXCHANGE_APPLY_SHARES` | variable | Scheduled runs may apply verified shares |
| `EXCHANGE_STAGE_ANNUAL` | variable | Scheduled runs may stage annual candidates |
| `SUPABASE_PROJECT_URL` | secret | Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | secret | Service-role key; used only by the two RPCs |

With no variables set, the workflow still produces a report and writes nothing. A manual
run can preview the result; applying or staging requires `EXCHANGE_WRITES_ENABLED=true`.

### One-time database deployment

Apply these migrations in the Supabase SQL editor (or your normal migration runner):

- `migrations/supabase/20261116_cloud_exchange_reconciliation.sql`
  — share audit table, service-role share RPC, annual candidate table, admin RPCs.
- `migrations/supabase/20261116_public_market_anon_read.sql`
  — **optional**, only if you want anonymous read-only market data.

The service-role RPC validates the report digest, contract, freshness, row status,
evidence hash, company mapping and integer share count before updating `na`. It never
touches annual fields.

### PHP publication

`.github/workflows/deploy-php.yml` is manual-only and dry-run by default. It uploads
only the selected runtime files over FTPS, using `FTP_HOST`/`FTP_USER`/`FTP_PASS`
secrets. The default selection is the reconciliation page and the four core files it
needs. Local execution remains possible but is not required.

### Annual approval page

`reconciliation.php` is an administrator-only page. It lists staged candidates grouped by
report, shows the proposed fields, warnings and evidence hash, and applies or rejects
selected companies through the admin RPC. No local SQL or CLI is required.

### Anonymous reads — decision

Anonymous reads are **not required for cloud automation**; the workflow uses the service
role. They matter only if the website should serve public market data without sign-in.
That is now an opt-in, not a default:

1. apply `20261116_public_market_anon_read.sql` (six public market tables only;
   portfolio/user tables are untouched);
2. set `allow_anonymous_market => true` in `config/supabase.local.php` or
   `SUPABASE_ALLOW_ANONYMOUS_MARKET=true` in the environment.

Leave it off if market pages are intentionally login-gated.

## Difficulties found and fixed

- **Incomplete TLS chain at the exchange.** The site served only its leaf certificate, so
  Python and curl rejected it. The capture tool now fetches the intermediate from the
  leaf's AIA URL, verifies it against the system roots with `openssl verify`, and builds a
  local bundle. Verification is never disabled. This was the main cloud blocker.
- **urllib ignored the custom SSL context.** The first capture attempt still failed after
  chain completion because `urlopen` used a default context. Fixed by binding an
  `HTTPSHandler(context=...)`; the full 82-instrument capture now runs without a custom
  bundle.
- **PL/pgSQL variable/column collisions.** The migration initially used `company` and
  `fields` as variable names, colliding with the table/column. Renamed to `v_company` and
  `v_fields`; the migration was exercised in a disposable PostgreSQL 14 container,
  including service-role apply, missing-company handling, quarantine skip, annual staging,
  admin apply and permission denial.
- **Anonymous reads are a product choice, not a cloud requirement.** The public tables are
  granted to `authenticated` only. The opt-in migration and reader flag above make public
  access possible; the default remains login-gated.
- **Scheduled runs are best-effort.** GitHub Actions cron can be delayed. The report carries
  its own generation time; the database rejects reports older than 30 days.
- **New listings appear automatically.** The live capture found 82 actions, including a
  new `NRJ JET ENERGY` instrument. The report quarantine/review classes handle unmapped
  companies instead of guessing a mapping.

## What this changes about credibility

- Share counts are no longer copied from a dated annual row or a provider field.
- Annual approval never changes `na`; BPA is recomputed from the current share count,
  so a later share update cannot be reverted by an older annual candidate.
- A share-only update changes `na` immediately; BPA follows the annual apply (or the
  next fundamentals refresh), and reviewed companies are not silently overwritten.
- Pre-split rows cannot silently become a 10× error.
- Every proposal carries its checks, warnings and page SHA-256.
- Annual figures are proposed with explicit units: `cp` in MAD, `net_profit` and
  `revenue` in millions, `bpa` in MAD per share.
- A stale or conflicting company is visible instead of being rendered as current.
- End-to-end cross-check: the T2S proposal matches the primary-reviewed disclosure
  already in `core/company_disclosures.php` — net profit 204.576m, equity
  1,410.404m, BPA 9.06, ROE 14.5.

## What is deliberately not done

- Writes are opt-in. The default workflow is report-only; applying shares or staging
  annual candidates requires `EXCHANGE_WRITES_ENABLED=true`, and the service-role secret.
- Annual exchange figures are not primary-document verified. They are a strong
  cross-check, not authority for group versus total equity or restatements.
- Annual candidates are staged for administrator approval; they are not auto-published
  without review. Automatic publication remains a policy decision.
- No claim that every instrument is current. The live run found 82 actions, 80 verified
  current counts, 5 stale annual rows and 2 quarantines (SNA and the new NRJ listing).

## Recommended rollout

1. Apply `20261116_cloud_exchange_reconciliation.sql` in Supabase.
2. Add the `SUPABASE_PROJECT_URL` and `SUPABASE_SERVICE_ROLE_KEY` repository secrets.
3. Run the workflow manually with both write inputs off; inspect the artifact.
4. Set `EXCHANGE_WRITES_ENABLED=true`, then run a manual share-apply. The RPC reports
   applied/unchanged/missing and writes one audit row per company.
5. Enable `EXCHANGE_RECONCILIATION_ENABLED=true` for the monthly report, and optionally
   `EXCHANGE_APPLY_SHARES=true` and `EXCHANGE_STAGE_ANNUAL=true` once the first runs pass.
6. Use `reconciliation.php` for the annual approval batch. Only the 34 exception
   companies should need a closer look.
7. Leave anonymous market reads off unless public no-login pages are a deliberate product
   choice.

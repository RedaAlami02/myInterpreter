# Backend deployment review — October 29

**Superseded by the completed review fixes:** read
[DEPLOYMENT_REVIEW_FIXES.md](DEPLOYMENT_REVIEW_FIXES.md) first. All five findings
from this initial bundle were fixed and independently re-reviewed in revision 2.
The current package pin, 347 passing test cases and narrowed first-installation
scope are recorded there. This document retains the original review baseline.

The staged backend now has a concrete review bundle and a combined installation
check. **No live schema, service, bucket, secret or schedule was created or enabled.**
The owner authorized a separate AI reviewer after this package was prepared;
that review subsequently found five issues, closed in the revision linked above.
Current website/app/backend migration estimate remains about **75% complete / 25%
remaining**, excluding prediction work. This checkpoint improves deployment
confidence; it does not turn local code into a completed hosted migration.

## New implementation

`tools/build_deployment_review.py` builds an immutable, generic runtime package
from a fixed allowlist. It copies original bytes, combines only the three explicit
function templates, and writes a per-file SHA-256/length/origin manifest last.

- **41 payload files** plus the manifest; **309,085 payload bytes**.
- Includes SQL009–013, three managed function implementations/tests, the selected
  Python worker modules and their pinned requirements.
- Excludes real credentials, project linking state, native recipes/mappings, raw
  captures, account records, the main worktree, Git metadata and all workflows.
- Refuses overwrite, public output paths, missing files, symlinks, special files,
  changed-during-read inputs, oversized content, unknown dependencies, unexpected
  function configuration and known private credential literals.
- Verification rejects changed bytes, extra/missing files/directories, duplicate
  manifest keys and a mismatched external manifest pin. Without a separately
  trusted pin, a self-contained hash manifest cannot establish origin.
- It has **no deploy, link, apply, secrets or activation operation**. An incomplete
  write leaves no completion manifest and fails verification; it is not silently
  deleted or accepted.

`tools/check_deployment_readiness.py` gathers bounded read-only database facts,
checks all ten staged RPC signatures, records current control states if installed,
and compares actual hosted market-local timestamps with the collector's Python
rules. It never treats a prerequisite measurement as approval or activation.

The privacy check uses the existing `tools/verify_database_privacy.py`; a rejected
publishable key cannot masquerade as a passing access-denial check.

## Fresh hosted facts

Both checks used the existing local credentials in memory, with TLS and explicit
read-only SQL. No credentials, user records, source names or native endpoints were
printed. Exact timestamped receipts remain private.

| Check | Actual result |
| --- | --- |
| Database size | **332,740,275 bytes**, unchanged from the previous recorded measurement |
| Headroom to staged 350 MB write guard | **17,259,725 bytes**; not a long-term growth forecast |
| Existing project Storage | Zero objects and zero buckets; no public buckets |
| Archive bucket | Absent |
| Staged archive/feed/admin/projection schemas | All absent; SQL009–013 not installed |
| Hosted timezone comparison | **145 sampled instants agree**, zero mismatches: historical replay dates, near-term day boundaries and monthly future samples |
| Anonymous API access | Denied for **all 15 existing application relations**, with a currently accepted API key |
| SQL privacy | No anonymous readable application relations, owner-only portfolio policies/RLS intact, no anonymously visible managed rows |
| Management tooling/access | No connected Management tool, no installed Supabase CLI and no SUPABASE_ACCESS_TOKEN in this process environment |
| Organization quota, private Actions/artifact headroom, SMTP delivery | Still not verified |

The earlier timezone discrepancy was observed with an older isolated PostgreSQL
image. It is **not evidence of a current hosted mismatch**: the actual hosted
comparison above passed. Samples do not certify all future timezone-rule changes;
repeat the probe before a later activation. Unknown source clock/timezone fields
remain unknown and were not changed by this infrastructure check.

Environment checks do not prove the owner lacks Management access elsewhere. API
project/database credentials are available but do not by themselves establish a
CLI Management session or authorize deployment.

## Actual tests

| Suite | Result |
| --- | --- |
| New bundle integrity/privacy tests | **14 passed** |
| New read-only readiness/clock tests | **9 passed** |
| Packaged function unit tests | **44 passed**: archive 19, app publisher 15, projection publisher 10 |
| All three packaged function entrypoints | Deno type-check passed |
| Existing isolated SQL regressions | **65 passed**, including archive concurrency |
| New combined packaged SQL acceptance | **10 passed** |
| Total checks executed as test cases in this checkpoint | **142 passed**, no SQL skips counted as passes |

The combined SQL tests load the existing application/recovery foundations and
then install the **exact packaged SQL009–013 in order**, on synthetic data only.
They verify original application values/timestamps, owner isolation, disabled
controls, unseeded administrator/provider rows, no anonymous table/RPC access,
disabled preview reads, refused unconfigured publication, refused non-admin
writes, stale-price valuation rejection and safe reapplication failure. A separate
fresh database demonstrates transaction rollback after an interruption following
all five scripts.

These are installation/regression checks, not an independent acceptance review
or hosted Storage/Edge execution. Packaged worker bytes are hash-verified; Python
worker parity tests remain in the main project and are intentionally not claimed
as tests included in this runtime bundle. The earlier 188-worker / 65-Flutter
results remain previous-checkpoint results; those unchanged suites were not
rerun here.

PostgreSQL 18.6 official Ubuntu packages were downloaded and unpacked only under
`/tmp/`, without system installation. The isolated server accepted private Unix
socket connections with TCP disabled and was stopped after all tests. The initial
initdb command required an absolute shared-data path; the corrected initialization
and final test/stop logs are preserved. There were no hosted SQL writes.

## Private artifact and review pin

Bundle: `private/deployment-review-20261029/bundle/`

Manifest SHA-256:
`179a0b68932f8713c0d65a4061ed41278fb4d259d22612480933599e65517e96`

Private receipts: `bundle-build-receipt.json`, `bundle-final-verification.json`,
`hosted-readiness-final.private.json`, `database-privacy.private.json`,
`sql-verification.json` and the focused test logs in the same checkpoint directory.
Do not publish the entire private directory; it also contains operational evidence.

Local integrity recheck, which does not deploy:

```
python3 tools/build_deployment_review.py \
  --verify private/deployment-review-20261029/bundle \
  --expected-manifest-sha256 179a0b68932f8713c0d65a4061ed41278fb4d259d22612480933599e65517e96
```

For a future read-only measurement use a **new** private report path. Existing
receipts and bundles are intentionally not overwritten.

## Ready for independent review; remaining installation scope

Use `docs/DEPLOYMENT_PACKAGE.md` alongside the pinned bundle. The concrete first
installation scope would be:

1. Create the private archive bucket through the Storage API, with an 8 MiB object
   limit and no anonymous/application-user access policy.
2. Apply reviewed SQL009–013 transactionally in order after confirming the actual
   baseline and measuring migration footprint/locking. Never replay a partial
   installation or raise capacity guards blindly.
3. Deploy the three functions with their environment switches **unset**, control
   rows disabled and no provider/admin seeding implicit in installation.
4. Verify hosted disabled/denial behaviour, actual server-secret availability,
   Storage response shapes, privacy and post-install database usage.

This scope still requires **independent review, explicit scoped deployment
permission and actual Management deployment access**. Earlier owner instructions
prohibited deploying cloud infrastructure; source-use authority and "continue"
do not independently clear that restriction. No deployment approval is inferred
from this document or its test counts.

After disabled installation, separate acceptance/enablement work remains: private
pins and scoped tokens, organization quota and durable outbox destination, real
current-session collection and timing, deliberate app preview integration,
SMTP/hosted redirect/Android device tests, then reviewed website/APK cutover.
Shadow quote candidates do not update legacy `latest_prices` or grant closing-price
authority. SQL012 continues to refuse stale recovered prices; a reviewed current
price path/contract remains necessary for automatic valuation. Source-use approval
does not invent source event times or promote a preview into model inputs.
Schedules and prediction production activation remain off. Both deferred portfolio
assignments and the owner-navigation request remain preserved.

Function template layout was checked against the official
[Supabase function configuration](https://supabase.com/docs/guides/functions/function-configuration)
documentation. Disabling platform JWT verification leaves authentication to the
implemented scoped-token handler; it does not grant anonymous publication rights.

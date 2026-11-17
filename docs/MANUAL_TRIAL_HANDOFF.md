# Controlled quote trial preparation — October 29

The existing hosted backend remains disabled. This continuation adds **local-only
manual-trial protection and a concrete private proposal**, not a hosted migration,
source capture, schedule, application cutover or production activation.

Read [DISABLED_BACKEND_INSTALL_HANDOFF.md](DISABLED_BACKEND_INSTALL_HANDOFF.md)
for the completed and separately authorized disabled installation. That approval
and the existing source-use authority remain valid; neither needs to be repeated.
Installing SQL014, provisioning scoped caller hashes and temporarily enabling the
archive/shadow path are outside that completed disabled-only scope.

Approximate website/mobile/backend completion remains **80% / 20% remaining**,
excluding prediction work. This is an engineering estimate, not a recovery metric.

## Implemented locally

- `migrations/supabase/014_manual_trial_leases.sql`: versioned
  `manual-activation/v1` owner-issued windows, at most 15 minutes. One trial binds
  an opaque namespace, approved plan hash, allowed capabilities/kinds and object /
  byte budget. Original global switches and existing validation remain required.
- Seven public RPC signatures/results retain their contracts. The reviewed
  implementations move to a private legacy schema with their OIDs/bodies intact;
  all application/service direct grants are revoked. New wrappers enforce the
  gate, including authenticated preview reads. SQL014 requires all controls off
  and must be installed atomically by the original function owner.
  The manual wrapper additionally requires the shadow control on for publication;
  disabling it now blocks trial writes as well as preview reads. The unchanged
  legacy publisher previously permitted staging while its reader was disabled.
- Each newly reserved digest binds permanently to its trial. Another window
  cannot adopt/finalize it, skip its slot or reactivate its preview. Orphan recovery
  requires a future explicit recovery procedure/approval; none is implemented.
- Failed post-call expiry checks **throw**, rolling back logical SQL changes.
  Original observation timestamps and raw bytes are never rewritten.
- Lease issue/revoke and gated calls serialize with a nonblocking transaction
  advisory lock. A busy revocation **fails and must be retried**; it is not an
  acknowledged stop. Read-committed isolation is required to avoid stale snapshots.
- Owner/API callers must configure an outer statement timeout of 1–20,000 ms
  before execution. Unbounded/longer configurations fail admission. An inner
  `SET` does not start the already-running statement's timer. The gate also uses
  a two-second lock timeout on its public wrappers.
- Preview row expiry is capped by its original trial deadline alongside existing
  freshness rules. Both archive and shadow capabilities must belong to that same
  trial. Early revocation blocks subsequent reads; an already cached response can
  remain usable until its returned expiry. No immediate offline-cache revocation
  is claimed.
- `tools/prepare_manual_trial.py`: offline, exclusive private proposal builder /
  external-pin verifier. It checks the original 41-file runtime pin and current
  runtime byte equality, exact mapping, bounded private inputs, file hashes,
  symlink denial and no extra files. It never reads credentials or makes requests.

These gates bound admission and roll back failed SQL postchecks; they do not
promise a transaction commits before its deadline. An admitted Storage upload can
finish after expiry. Its later finalization is refused, leaving private immutable
evidence and an unresolved outbox for explicit recovery rather than a false STORED
receipt. Endpoint flags still need explicit cleanup even after lease expiry.

Projection capability retains SQL013's application-table write behavior. It is
**excluded** from the proposed quote-only trial and needs its own acceptance scope.

## Verification and current hosted facts

The new isolated tests pass **27 SQL cases and 10 package cases**, using synthetic
data on a fresh `/tmp/` PostgreSQL socket database with TCP disabled. Coverage
includes expiry during mutation/full rollback, direct legacy denial, role grants,
retries/budgets, conflicting plans/namespaces, old evidence under new windows,
preview values/order/expiry, successful service-role archive/publish calls,
authenticated preview, revocation contention and both unchanged projection
receipt shapes. Positive projections ran only in the synthetic local database.

The existing user-authorized independent reviewer found **no blocking flaw** in
the final files, independently reran all 27 SQL and 10 package cases, checked the
final proposal pin/SQL equality and reverified its runtime pin. Acceptance is
conditional for **local manual-trial preparation only**, with hosted/permission/
quota gates still pending. Review evidence is preserved privately. The temporary
PostgreSQL server was stopped after both runs; the reviewer's fresh DB was dropped.

The unchanged runtime's previous 347 passing cases and two integration checks
remain the earlier baseline; they were not counted again as new execution.
No genuine ledger, frozen model, original recovery dataset or account was touched.

Fresh hosted read-only preflight confirms:

| Check | Result |
| --- | --- |
| Company / format identities | 81 / 81; exact private mapping matches both sets |
| Database size | 333,182,643 bytes; 16,817,357 below the 350 MB guard |
| Archive/feed/projection controls | All off |
| Providers, archive/slot/candidate/acceptance rows | All empty |
| Private bucket / object count | Private, 8 MiB object limit / zero objects |
| Existing three functions | Version 1; enable-variable names absent |
| SQL014 | Absent; no trial window exists remotely |
| Anonymous application relation access | Zero exposed relations found |

The service role has no explicit role-level statement timeout; authenticated and
API authenticator roles record eight seconds. This does **not** independently
prove the effective timer of a privileged REST request. Positive RPC timeout and
named-server-key availability remain acceptance checks; do not change role
configuration without scope approval. Organization Storage and private Actions /
artifact headroom remain unknown. No new remote mutations or source requests
occurred in this continuation.

## Concrete proposal and continuation

Private proposal directory: `private/manual-trial-20261029/proposal-v3/`.
External plan SHA-256:

`34432cfa4e40e64f5372663312776d6bb3ec98bdf259f3f34c2d7d43696434f7`

It pins the installed runtime manifest
`76425b6d9752926a913cff39c4065905782d0de6a35c3f662699f9eb1bfb4330`
and SQL014/config/mapping/profile bytes. Earlier versions are preserved but superseded:
its source-attempt wording did not account for the existing worker's retry.
Version 3 includes the explicit shadow write switch and correctly permits
**one logical genuine current capture, at most two
source HTTP attempts**, one archive object at most 8 MiB, and a **five-minute**
archive + shadow window for 81 stocks and MASI. Missing/stale source values remain
explicitly unavailable; shadow prices never become original historical values,
portfolio valuations or prediction inputs. No projections, accounts, email, app
readers, schedules, publication/pushes or model execution are included.

Next steps:

1. Independent review is complete for the final local preparation. Preserve its
   findings/evidence. Rebuild the proposal under a new directory/pin and re-review
   if any captured runtime/migration bytes change.
2. Obtain concrete approval for SQL014 installation and the bounded manual trial,
   plus confirmation of organization Storage room for the 8 MiB bound. Existing
   Management token access requested Secrets **Read**, not Write. Do not assume
   permission to provision function token hashes/enable variables; use a new
   approved permission scope or owner-configured secrets. Never paste keys in chat.
3. Before any approved trial, refresh all read-only prerequisites and original
   preservation fingerprints; keep a verified backup, transaction journal and
   exact plan pin. Verify the effective API timeout; stop on unsupported config.
4. Provision two distinct narrow callers privately, issue only the five-minute
   quote trial, capture/archive/read back exact bytes and publish shadow candidate.
   Preserve each failure and outbox; no source replay promotion or automatic new
   trial. Revoke (retry on busy), disable controls/provider and remove enable
   variables in cleanup; verify the final disabled state without deleting evidence.
5. Continue separately with durable cross-run outbox/quota/private publication,
   reviewed recurring automation, web/mobile preview, owner maintenance/valuation,
   real SMTP/redirect/device acceptance and cutover. Account assignment and the
   rarely used owner navigation change remain deferred as previously agreed.

Evidence: `private/manual-trial-20261029/` contains unique local SQL logs/receipts,
the bounded proposal copies and hosted read-only preflight receipt. The local
runner never reads hosted credentials. The preflight uses read-only TLS SQL and
Management GETs, prints only safe aggregates and never contacts market sources.

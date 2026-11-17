# Database snapshots

`database-snapshot-YYYYMM.sql.gz` is a data-only dump of the public market
tables, produced by `.github/workflows/database-snapshot.yml` (monthly on the
1st, or manually) and kept as a 90-day workflow artifact.

A copy from 2026-11 is stored in this directory for convenience. Dumps are
git-ignored; only the manifests (`manifest-YYYYMM.json`) are committed, with
row counts, size and SHA-256.

Restore procedure: see [docs/OPERATIONS_RUNBOOK.md](../../docs/OPERATIONS_RUNBOOK.md#restore).

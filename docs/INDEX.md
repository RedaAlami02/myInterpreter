# Documentation index

Start here:

| Document | What it answers |
|---|---|
| [CURRENT_STATE_20261117.md](CURRENT_STATE_20261117.md) | How data flows today, what runs automatically, what is open |
| [APIS_20261117.md](APIS_20261117.md) | Every external endpoint and Supabase RPC, with known failure modes |
| [BUGFIX_LOG_20261117.md](BUGFIX_LOG_20261117.md) | Bugs fixed on 2026-11-17 and the verified open ones |
| [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) | Deploy, migrate, run a feed by hand, restore a snapshot |

Data and publishing specifics:

| Document | Topic |
|---|---|
| [ORDERBOOKS_20261117.md](ORDERBOOKS_20261117.md) | Order-book sources, pipeline, retention, page contract |
| [DIVIDENDS_20261117.md](DIVIDENDS_20261117.md) | Dividend model, repairs and constraints |
| [ANNUAL_REVIEW_20261117.md](ANNUAL_REVIEW_20261117.md) | Annual-review queue and classes |
| [CLOUD_RECONCILIATION_RESUME_20261117.md](CLOUD_RECONCILIATION_RESUME_20261117.md) | Reconciliation resume state |

Migration history (read for context, not as current state):

| Document | Topic |
|---|---|
| [MIGRATION_HANDOFF.md](MIGRATION_HANDOFF.md) | Supabase cutover handoff |
| [AI_MIGRATION_HANDOFF.md](AI_MIGRATION_HANDOFF.md) | Agent-facing migration notes |
| [ALL_NONPERSONAL_DATA_RESTORE.md](ALL_NONPERSONAL_DATA_RESTORE.md) | Non-personal restore procedure |
| [AUTH_FLOWS.md](AUTH_FLOWS.md) | Authentication after the cutover |

Other design and audit notes live alongside these files; the index above lists
the ones that describe the running system.

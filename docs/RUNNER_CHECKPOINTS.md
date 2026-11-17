# Private retry checkpoints

November 1: cloud workflow integration and the private worker distribution have
now been implemented. Read [CLOUD_AUTOMATION_20261101.md](CLOUD_AUTOMATION_20261101.md)
for current implementation and hosted acceptance results. The local transport
contract below remains valid; the older "Cloud work still required" section is
the checklist used for that implementation, not a statement that no code exists.
Collection and recurring execution remain disabled.

`automation/managed/runner_checkpoint.py` carries the existing four retry queues
between isolated runners. This is a local transport tool, not an activated cloud
workflow. It makes no source request, database write, upload or deletion.

Use one private state root with this exact producer layout:

| Directory | Producer | Contents |
| --- | --- | --- |
| `archive/` | `APP_ARCHIVE_SPOOL_DIR` | unacknowledged raw archive transmission copies |
| `quotes/` | `--publication-spool` or `APP_PRICE_PUBLICATION_SPOOL_DIR` | exact prepared publication retry jobs |
| `quotes.accepted/` | automatic sibling created by `Publications` | durable publication receipts |
| `enrichment/` | `--enrichment-spool` | raw evidence and prepared enrichment retries |

Stop the worker before packing or restoring. Serialize all jobs using this state;
do not cancel a collector to start another collector over the same queues.
Unexpected root entries fail closed; the restored completion manifest and empty
enrichment lock file are the only additional allowed files. Do not place recipe
configuration, credentials, SQLite databases or other files under this root.

From `automation/managed/`, after the worker exits:

```sh
python3 runner_checkpoint.py pack --state /private/state --output /private/checkpoint-next
```

The output directory must not exist. The aggregate checkpoint is bounded at
64 MiB and has a last-written `CHECKPOINT.json` completion marker. The command
prints a manifest SHA-256; persist that pin separately alongside the private
checkpoint identity. A self-contained hash does not authenticate its own origin.
Even an entirely empty state has a checkpoint: restoring an older nonempty state
would otherwise resurrect already acknowledged work.

On a new runner, with the selected complete checkpoint and its verified pin:

```sh
python3 runner_checkpoint.py restore --checkpoint /private/checkpoint-downloaded \
  --state /private/state-restored --sha256 VERIFIED_MANIFEST_SHA256
```

Restore refuses an existing target, validates every channel's typed bundle,
counts, bounds, filenames and exact hashes into a disposable tree, then writes
the fresh target and its completion marker last. Consumer code still validates
inner gzip jobs, their source/profile pins, timestamps and receipts before any
send. The checkpoint tool does not rederive or certify market observations.
It preserves pending and accepted bytes and does not prune originals.

Nine isolated tests include a real `Publications` producer, successful synthetic
publication, checkpoint/restore and retained logical completion. Corrupt later
channels cannot leave an apparently complete partial restore. Independent local
review found no remaining blocker for serialized, quiescent use.

## Cloud work still required

The installed disabled backend and immutable review bundle v3 do not contain or
activate this new helper. The private worker distribution still needs updating.
Before recurring execution, a separately reviewed workflow must:

1. Restore the newest verified complete checkpoint before collection. Missing,
   expired or corrupt expected state must stop the run, not initialize it empty
   or silently use an older checkpoint. Initial empty bootstrap is explicit.
2. Persist a new complete checkpoint even after a collector fails. Keep the
   previous complete checkpoint until the new one is uploaded and read back.
   An empty new checkpoint also supersedes its predecessor.
3. Enforce private visibility, aggregate retention/quota limits and serialized
   execution. Delete only superseded operational checkpoint copies under the
   reviewed retention policy; never delete original historical evidence.
4. Treat abrupt runner loss before checkpoint upload as a remaining durability
   limit. Local fsync alone cannot protect a discarded cloud runner.
5. Verify shared artifact capacity and actual job runtime/compute headroom before
   schedules. Retaining every 64 MiB checkpoint would exhaust a small quota.

No workflow was published, no schedule was enabled and no live capture was made
for this tool's verification.

# ADR-020: Bounded D-Drive Paper Storage

- Status: accepted
- Date: 2026-08-24
- Scope: local public paper data only

## Context

All-KRW ticker monitoring plus rotating trade/orderbook detail was projected to consume roughly
20–70GB per 30 days. The original Docker named volume lived inside Docker Desktop's C-drive storage,
had no age or size retention, and could continue until the host filesystem was exhausted. The owner
provided `D:/Sentinel-Data`, which has substantially more free space. This local disk is still not a
backup or production database.

## Decision

Bind `/app/data/paper` to a host path supplied through the ignored
`compose.paper.local.env`. Keep the committed fallback at `./data/paper` and the public example free
of machine-specific paths. Never commit the local override or production credentials.

Keep raw events in atomic manifest-backed ZSTD Parquet. Every 15 minutes, compact at least four small
files from a completed creation-hour partition into a checksummed version-2 manifest. The compacted
manifest lists every superseded data file. It is committed after its data file; only then are source
manifests atomically renamed to durable retirement markers and source data removed. Replay resolves
supersession first, so an interruption can produce neither trusted data loss nor duplicate replay.

Apply two independent deletion bounds:

1. Retain raw data for no more than 30 days by trusted manifest creation time.
2. Retain no more than 50GiB of active raw Parquet; remove the oldest active files first when needed.

Retirement markers preserve deletion/compaction lineage. On startup and each maintenance pass,
validate active manifest sizes, resume interrupted retirements, recompute retained totals, and expose
the results through `paper-runtime-5` and the local monitor. Completed retirement markers move to
`data/paper/maintenance/retired`, outside the active raw scan tree. Check the actual paper-data filesystem
every heartbeat and after maintenance. If free space is below 20GiB, stop the public paper runtime
fail-closed instead of accepting more data.

Grant the Compose service a 300-second stop grace period so a normal recreate can close the public
socket, drain the bounded storage queue, complete the final full-store maintenance/index pass, and
persist a clean recovery checkpoint before termination. The original 60-second budget became
insufficient once retained storage reached 1.7GB and 362 active files: a 2026-08-27 planned stop
finished writing 14,518,628 checksum-valid rows but was killed before it could write the terminal
runtime and continuity records. The longer bound remains finite and lets Docker fail closed if the
shutdown path genuinely hangs.

Allow a 180-second health-check start period for the same full-store startup verification. At the
2026-08-27 retained size, initialization took about two minutes before the new public socket became
healthy; the prior 30-second period produced a false transient `unhealthy` state without a process
failure. Normal steady-state health cadence and failure thresholds remain unchanged.

## Migration

The running collector was stopped through `SIGTERM` with a `VERIFIED_CLEAN` recovery checkpoint.
Exactly 314,560 manifest-backed rows, 781 Parquet files, and 46,643,200 Parquet bytes were copied from
`quantforge_paper-data` to `D:/Sentinel-Data`. The original named volume was retained as a rollback
copy. The first D-drive startup preserved all 314,560 rows, compacted 659 source files, reduced active
files from 781 to 134, and reclaimed 6,749,864 bytes before reconnecting.

## Consequences

- The user's bulk paper data grows on D rather than Docker Desktop's C-drive volume.
- The 50GiB cap can shorten the effective 30-day window during high activity; both are upper bounds,
  not storage guarantees.
- Age/capacity pruning intentionally makes old raw replay unavailable. Retirement metadata remains,
  but deleted payloads cannot be reconstructed without an independent backup.
- Tombstones, recovery state, and small filesystem metadata sit outside the 50GiB raw-Parquet cap.
- Compaction runs off the market-event hot path but may temporarily use CPU and memory, especially on
  the first migration startup.
- D-drive failure, deletion, or host compromise remains a single-machine loss scenario. Encrypted
  off-host backup and measured restore are separate future work.
- This decision adds no credentials, private endpoint, model approval, paper-order permission, or
  real-order capability.

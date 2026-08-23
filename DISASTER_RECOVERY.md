# QuantForge Disaster Recovery

## Scope

Protect PostgreSQL, model artifacts, experiment/strategy registries, risk policy, release manifests, raw-data manifests, incident reports, configuration, and monitoring definitions. Full raw-tick retention has a separate capacity/retention policy.

## Recovery objectives

RPO and RTO are **not guaranteed in Phase 0**. Initial targets will be selected only after backup size, restore duration, and acceptable operational loss are measured. Report measured values rather than aspirational guarantees.

## Backup contract

- Backups are encrypted, access-controlled, versioned, checksummed, and stored separately from the primary host.
- A manifest records source versions, schema/migration level, creation time, object counts, hashes, and encryption/key reference without key material.
- Partial or checksum-failing backups are invalid.
- Credentials are restored through the external secret system, never bundled in project backups.

## Isolated restore test

Monthly scheduled testing uses a temporary directory and disposable database only:

1. Verify backup manifest and artifact checksums.
2. Restore database and run migrations.
3. Restore configuration, registries, and model artifacts.
4. Start without Secrets and confirm default paper mode.
5. Run deterministic golden replay and compare hashes/accounting.
6. Generate redacted runtime exports and check dashboard/API health.
7. Destroy the disposable environment after preserving the report.

Never point a restore test at production storage or an order-capable network path.

## Production recovery sequence

1. Declare incident and freeze order eligibility.
2. Preserve failed-system evidence.
3. Select the latest verified compatible backup.
4. Restore into isolation, verify manifests/migrations/artifacts, and replay invariants.
5. Deploy in paper/shadow only.
6. Reconcile exchange state, balances, orders, fills, and internal ledger.
7. Require explicit operator and release approval before any later canary review.

## Failure reporting

Record the failed step, affected recovery point, evidence, likely impact, workaround, code/config changes required, owner action, and next retest date. A failed restore test blocks live-readiness status.
Order recovery starts from the durable execution journal, never from a repeated create request.
Verify the journal hash chain and state transitions, reconcile every pending/unknown identifier, and
compare exact remote balances before rebuilding positions or allowing any new submission. A partial,
corrupt, missing, or contradictory journal is a fail-closed incident requiring human review.

Phase 6 validates order recovery with a file journal and fake exchange. Phase 7 adds an explicit-file
local backup manifest and empty-directory paper restore drill. It verifies canonical paths, object
counts, per-object and aggregate SHA-256, rejects Secret-shaped files/symlinks/extra objects, and
writes a paper-only marker after restore.

This local artifact is deliberately marked `encrypted_by_external_storage=false` and
`objectives_measured=false`. It is development evidence, not a production backup or RPO/RTO claim.
Phase 11.5 moves bounded public paper data to `D:/Sentinel-Data` and preserves the prior Docker named
volume after migration. Both remain on the same computer and therefore count as primary/rollback
storage only, never as the separately stored encrypted backup required by this contract. Automatic
30-day/50GiB pruning makes deleted raw payloads unrecoverable without such a backup.
PostgreSQL-native backup/restore, off-host encrypted raw retention, key management, private-stream
replay, credential restoration, and measured recovery objectives remain
unimplemented. No restore drill may receive an exchange credential or order-capable network path.

The Phase 8 monthly recovery prompt remains unregistered until a manual isolated run has a valid
`automation-report-1` manifest. A scheduled run must use a dedicated background worktree and a new
or empty temporary target. Missing production-grade backup evidence is `BLOCKED`, not permission to
reuse the local development proof or touch production storage.

The readiness backup gate requires a recent, checksummed, isolated, encrypted, off-host,
production-grade restore with measured objectives. Therefore the current local unencrypted proof is
deliberately `NOT_READY` evidence even when its checksum drill passes.

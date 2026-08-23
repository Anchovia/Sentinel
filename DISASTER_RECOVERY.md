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

Phase 6 validates this process with a file journal and fake exchange. Database recovery, backups,
private stream replay, credential restoration, and authenticated cancellation remain unimplemented.

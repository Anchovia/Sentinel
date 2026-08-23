# ADR-011: Read-oriented operations plane with proposal-only remote controls

- Status: Accepted
- Date: 2026-08-23

## Context

Phase 7 needs an authenticated operations view, incidents, audit evidence, emergency actions,
runtime exports, and restore proofs. The repository still has no private exchange transport or live
adapter. Adding a dashboard must not create a second route around the risk engine or turn a browser,
Work, or Codex into an order authority.

Operational views may contain balances, identifiers, and incident evidence. They must remain
separate from production Secrets and reject credential-shaped content before export. State-changing
HTTP requests need protection against credential guessing, cross-site requests, duplicate delivery,
ambiguous timeouts, and unaudited action.

## Decision

The initial dashboard is a dependency-free server-rendered HTML view backed by the same strict
Pydantic read model as the versioned `operations-dashboard-1` JSON export. The default is closed.
Operators must externally supply a strong bearer token and a separate server-side CSRF signing
Secret as a complete pair. Read APIs and the HTML view require bearer authentication; a short-lived,
actor-bound CSRF proof is additionally required for state-changing requests.

Runtime exports are atomic and contain only fixed read-model fields. A recursive guard rejects
credential/authorization field names, bearer/JWT-shaped text, and full account UUID fields before
writing. The operations plane does not read an Upbit Secret, private API, or production database.

Emergency actions pass through a confirmed and idempotent request service. The client supplies the
exact action-specific confirmation phrase and an idempotency key. A fsynced hash-chain journal
records `REQUESTED` before dispatch and the verified, blocked, failed, or unknown outcome afterward;
a separate audit chain stores only a hashed operator reference and hashed idempotency key. A crash
left at `REQUESTED` becomes `UNKNOWN` on recovery and is never executed again automatically.

Only the local `cancel_only` kill switch and incident acknowledgement have verified local effects.
A strategy pause is a recorded proposal with no direct strategy mutation. Cancel-all remains
`BLOCKED` because no authenticated cancellation transport exists. The GUI cannot release the kill
switch, flatten positions, change risk limits, change models, activate live mode, or send orders.

Backups in this phase are checksummed local restore-drill proofs over explicitly selected workspace
paths. They reject Secrets, repository metadata, symlinks, path traversal, unmanifested objects, and
checksum damage. Their manifest explicitly reports that objectives are unmeasured and external
encryption is absent. Production use requires encrypted off-host storage, database-native backup,
credential restoration outside the archive, and measured RPO/RTO evidence.

## Consequences

- The default API still exposes public health/safety/metrics only; operations endpoints return 503
  until dashboard authentication is configured.
- Dashboard authentication is independent from exchange credentials and cannot enable execution.
- Emergency requests remain safe under duplicate delivery and ambiguous interruption, but the
  single-writer file journals are not a transactional multi-process operations database.
- The local dashboard and Grafana health screen are suitable for paper operations and restore
  drills, not internet exposure without a hardened TLS reverse proxy, authorization policy, rate
  limiting, and external Secret delivery.
- A future real cancellation executor, durable database control plane, or kill-switch release API
  requires another reviewed ADR and explicit human approval.

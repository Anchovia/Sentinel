# ADR-025: Durable Paper Runtime Continuity Evidence

- Status: accepted
- Date: 2026-08-25

## Context

The runtime lifecycle snapshot is overwritten on each heartbeat and the Work baseline writer emits
only every 15 minutes. A missing baseline therefore cannot distinguish a stopped desktop, a clean
container restart, an application failure, or an unobserved interval. Treating sparse snapshots as
complete uptime evidence produced avoidable audit blocks; treating them as proof of an outage would
also be incorrect.

## Decision

Persist a small `paper-runtime-continuity-lease-1` beside the paper recovery state on every runtime
heartbeat and terminal transition. Append session starts, clean or failed stops, missing terminal
records, locally observed public-WebSocket/data-staleness gaps, and reconnect-counter changes to the
fsynced SHA-256 chain `paper-runtime-session-event-1` ledger.

At the next start, an active prior lease is classified as `UNEXPECTED_INTERRUPTION` with downtime
measured from its last heartbeat. A terminal lease is classified as a clean or failed stop. Invalid
lease or ledger evidence is preserved, marked `DEGRADED`, and no longer appended; public paper
observation may continue, but continuity readiness remains false.

Publish the compact `paper-runtime-continuity-1` snapshot and include its fields in `work-ops-2`.
The six-hour and twelve-hour results require an active session, sufficient elapsed time, a connected
public socket, fresh events, verified/non-degraded evidence, and no observed gap or reconnect in the
current session. The local monitor displays only uptime, the previous-session outcome, observed-gap
count, and these two results.

The contract always records `exchange_gap_completeness_claimed=false`. Heartbeats and local event
observations cannot prove that Upbit delivered every exchange event, and continuity before the
first recorded session remains unknown.

## Consequences

- Work can distinguish sparse 15-minute exports from durable process/session evidence without
  inventing continuous exchange coverage.
- Graceful container restarts leave an explicit terminal record; power loss, forced termination, or
  an application death is detected on the next start if the durable drive remains available.
- The ledger is low-volume because it records lifecycle and observed transitions, not market data.
- One reconnect or observed feed gap keeps the current session's strict six/twelve-hour result
  closed; later rolling-window recovery can be added only with a versioned contract.
- This is single-host paper evidence, not an external watchdog, operating-system audit trail,
  exchange sequence proof, production SLA, backup, or live-trading readiness claim.
- Model approval, paper-order simulation, risk settings, authentication, and live submission are
  unchanged.

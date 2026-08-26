# ADR-026: Live Clock Regression Stabilization

- Status: accepted
- Date: 2026-08-26

## Context

The public WebSocket client invokes its event callback sequentially and records both UTC wall time
and process-monotonic receive time. During laptop burn-in, the paper container restarted three times
because `received_at_utc` moved backwards and the causal real-time pipeline correctly rejected
decreasing availability. The process was not OOM-killed and the failure was not a transport
reconnect. Local wall clocks may step backwards after Windows/NTP correction even though the
process-monotonic clock and actual callback order continue forward.

Accepting decreasing availability would corrupt rolling windows and causal feature order. Crashing
on a wall-clock-only correction loses public observation, while silently clamping it would erase
data-quality evidence.

## Decision

For the supervised public client, sample the UTC wall clock and monotonic clock together for every
raw message. When the wall clock is at least the prior accepted availability, retain it. When it is
earlier, advance availability from the prior accepted value by the elapsed monotonic interval and add
`local_clock_regression` to the event quality flags.

Identify these supervised receive semantics as `upbit-public-live-v2`; existing direct mapper events
remain `upbit-public-v1`. Preserve the exact raw payload bytes and hash in both versions. The causal
pipeline marks a flagged frame `LOCAL_CLOCK_REGRESSION` and keeps it `HOLD`. It continues to reject
any decreasing envelope that bypasses stabilization, and a regression in the monotonic clock itself
remains fatal.

## Consequences

- Windows/NTP wall-clock correction no longer restarts credential-free public collection when
  process-monotonic receipt order remains valid.
- Availability, rolling windows, persisted raw ordering, and deterministic replay remain
  nondecreasing while the anomaly stays visible in lineage and quality flags.
- A flagged event cannot become inference-ready, approve risk, or reach a paper or real order path.
- Historical `upbit-public-v1` rows remain readable and unchanged; new supervised rows are
  distinguishable without a schema migration.
- The derived availability is local process evidence, not proof of exchange completeness or clock
  accuracy. Authentication, risk limits, model approval, paper-order policy, and live submission are
  unchanged and closed.

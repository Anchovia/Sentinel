# ADR-016: Low-Latency HOLD-Only Real-Time Pipeline

- Status: accepted
- Date: 2026-08-24

## Context

The supervised public burn-in previously normalized and persisted events before any real-time paper
decision composition. Short-horizon paper research needs causal features immediately after arrival,
but storage work must not determine decision latency and an unfinished model path must never emit an
actionable proposal.

## Decision

Process each validated immutable event through an incremental in-memory feature pipeline. Require a
fresh orderbook and trade state; treat ticker state as optional enrichment. Maintain bounded 1s, 5s,
and 15s trade windows and emit a strict atomic snapshot with measured p50/p95/p99/max latency and a
5ms feature-processing budget.

Enqueue the same event into a bounded 65,536-item storage queue before feature processing. A single
worker persists batches of up to 512 events and performs periodic flushes even under continuous
traffic. Queue overflow or worker failure stops the paper supervisor; raw events are never silently
dropped to preserve speed.

Keep the decision fixed at `HOLD` with reason `NO_APPROVED_REALTIME_MODEL`. The pipeline exposes no
private network, account, strategy order, order submission, or live submission capability. Verified
retained Parquet may be replayed by `benchmark-realtime`; its result measures validation and feature
calculation only.

## Consequences

- Feature work no longer waits on compression, filesystem commits, or manifest writes.
- Causal state and overload behavior are deterministic and directly testable.
- Ticker sparsity does not block a book/trade feature frame, while stale required state still fails
  readiness closed.
- The bounded queue consumes memory during storage stalls and deliberately terminates on exhaustion.
- No paper trade or performance result exists until reviewed inference, proposal routing, risk,
  broker, and ledger stages are composed and measured separately.

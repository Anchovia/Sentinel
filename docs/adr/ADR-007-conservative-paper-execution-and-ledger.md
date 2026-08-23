# ADR-007: Conservative paper execution and append-only accounting

- Status: Accepted
- Date: 2026-08-23

## Context

Historical public orderbook snapshots do not reveal individual order identity, exact queue position,
or whether a depth decrease was a fill or cancellation. Treating every order as fully filled at the
midpoint would therefore create materially optimistic backtests. Paper execution must also remain
incapable of reaching an authenticated exchange path.

## Decision

QuantForge provides three explicitly named paper fill models:

- `naive` fills eligible quantity at the midpoint and exists only as a unit-test/research comparator;
- `conservative_l2` is the default and applies configured latency, visible-depth haircut, spread,
  slippage, adverse-selection buffer, partial/non-fill, time-in-force, and cancellation latency;
- `calibrated_l2` cannot be selected without a calibration artifact identifier.

All rates are versioned simulation assumptions. The default `0.0005` maker/taker fee is not a claim
about the current Upbit fee schedule. A zero fee is rejected unless a research-only override is set.
Production-like evaluations must refresh fee and order capabilities from official documentation.

Passive queue approximation starts behind existing same-side depth multiplied by a configurable
queue factor. Matching aggressive trade volume consumes that queue first. Snapshot depth decreases
are ambiguous and only a configured fraction may count as executable volume. Price priority is
enforced at the selected limit. A data gap invalidates the book and cancels resting paper orders; a
fresh orderbook is required before new paper submission. Future or stale events are rejected.

Paper orders, fills, replay runs, and ledger records use deterministic identifiers and hashes.
Accounting uses exact `Decimal`, spot-only FIFO lots, cash/position reservations, duplicate-fill
rejection, non-negative cash/position invariants, and an append-only hash chain. PnL exposes gross,
realized, unrealized, fee, spread, slippage, adverse-selection, net, and equity fields. Spread,
slippage, and taker adverse-selection buffers are already reflected in execution prices and are
reported as attribution rather than subtracted a second time.

No private endpoint, credential source, or real-order transport is part of the paper broker.

## Consequences

- Same dataset hash, replay/execution configuration, code version, intent/risk identifiers, and seed
  produce identical fills, ledger hashes, PnL, and report hashes.
- The conservative result will often have less filled quantity and worse PnL than the naive result;
  this is intentional evidence rather than an error.
- L2 queue position remains an approximation until a reviewed calibration dataset exists. Snapshot
  depth changes cannot distinguish cancellations from executions.
- Phase 3 does not claim exact exchange tick, minimum-order, or fee capability parity. Those values
  remain capability-driven and must be refreshed before private execution work.
- The ledger is intentionally single-market, long-only KRW spot. Multi-asset netting, tax lots,
  transfers, and private-balance reconciliation remain later work.

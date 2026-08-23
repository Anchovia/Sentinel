# ADR-018: Fail-Closed Paper State Recovery

- Status: accepted
- Date: 2026-08-24

## Context

The real-time paper composition could account exactly inside one process, but a restart discarded
broker orders, reservations, fills, FIFO lots, balances, and counters. Automatically resuming an
uncertain resting order from stale L2 state would corrupt paper evidence and could teach unsafe
recovery behavior before any authenticated execution work exists.

## Decision

Persist `realtime-paper-recovery-1` in the durable paper-data volume. Bind the complete economic
state to the decision policy, execution policy, market universe, per-ledger state hashes, verified
ledger chains, and one outer SHA-256. Persist consequential order/accounting mutations synchronously
and include that cost in decision latency; refresh neutral state on the existing heartbeat.

Never checkpoint or restore an orderbook. On clean shutdown, cancel every non-terminal paper order,
release every reservation, and mark the checkpoint clean. Restore such a checkpoint only after every
hash, fill sequence, lot, balance, reservation, ledger tail, policy, and market invariant validates.

Treat any checkpoint left active by an unclean shutdown as uncertain evidence. Restore it only to
cancel non-terminal paper orders and release locks, then persist a recovery block. The block survives
later clean restarts and keeps simulated-order permission false. Do not add an automatic reset or
operator acknowledgement in this checkpoint. The sole automatic exception is a disabled simulation
whose checkpoint proves there is no order, fill, lock, lot, ledger record, cost, turnover, or balance
change; it may recover as `EMPTY_UNCLEAN_RECOVERED`. Translate container termination signals into the
normal supervisor shutdown path and close the active public socket so ordinary replacement writes a
clean checkpoint even when network receive is stalled.

## Consequences

- Graceful supervisor restarts preserve exact positions, costs, counters, and audit history.
- Stale public books and ambiguous resting queue position are never resumed.
- Corruption, policy drift, market drift, or accounting mismatch prevents startup restoration.
- An interrupted paper session is excluded from performance claims and requires future human review
  before the simulation block can be cleared.
- Full-ledger checkpoint size grows with simulated trades and needs later production persistence and
  compaction work; it does not grow on every neutral public event.
- No private transport, credential, exchange order, live capability, or automatic approval is added.

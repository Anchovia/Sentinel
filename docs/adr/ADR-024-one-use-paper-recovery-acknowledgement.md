# ADR-024: One-Use Human Acknowledgement for Blocked Paper Recovery

- Status: accepted
- Date: 2026-08-25

## Context

ADR-018 intentionally left economically active, unclean paper recovery permanently blocked. The
runtime already cancels every non-terminal paper order, releases reservations, verifies the broker
and Decimal ledger, and can then stop cleanly. A reviewed way to resume paper simulation is needed,
but a generic reset flag or editable checkpoint would erase the incident boundary and permit stale
or replayed approval.

## Decision

Add `paper-recovery-acknowledgement-1` as a short-lived, Secret-free human approval bound to the
exact blocked checkpoint hash, policy hash, KRW market universe, pseudonymous reviewer reference,
review reference, and clearance facts. Creating it requires the exact confirmation phrase and a
checkpoint that is both cleanly stopped and still blocked. Creation never edits the checkpoint,
changes a gate, accesses a network, or submits an order.

Only the paper runtime may consume the acknowledgement. At its next start it re-reads the same
checkpoint and independently verifies that every broker order is terminal, UNKNOWN/RECONCILING
orders are absent, reservation count and locked cash are zero, and every portfolio ledger restores
and round-trips exactly. It then writes an active checkpoint with only the recovery block cleared
and records `paper-recovery-acknowledgement-receipt-1`. The receipt makes the approval one-use even
if an old checkpoint and pending file are restored together. Missing, expired, changed, malformed,
or previously consumed approvals fail closed.

This workflow does not approve a model, enable the separately reviewed paper-order policy, change
risk limits or runtime settings, validate interrupted performance, create private connectivity, or
add a real-order path.

A rejected sidecar leaves simulation blocked and records a rejection reason in the decision state;
credential-free public collection may continue. Corruption of the authoritative recovery checkpoint
itself still prevents restoration.

## Consequences

- Human approval alone is insufficient; runtime-time reconciliation must also pass.
- The acknowledgement and receipt form immutable, hash-bound audit evidence outside raw data.
- A running checkpoint is ineligible, so the operator must stop the paper service cleanly first.
- Existing clean unblocked recovery and the narrowly proven empty-state exception are unchanged.
- Paper positions may be restored after exact ledger verification, but the interrupted session
  remains excluded from performance claims and requires separate performance segmentation.
- Production recovery, authenticated order reconciliation, multi-operator authorization, and
  cryptographic identity remain future work.

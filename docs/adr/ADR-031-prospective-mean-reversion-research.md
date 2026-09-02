# ADR-031: Prospective Mean-Reversion Research Input

- Status: accepted
- Date: 2026-09-02
- Scope: offline public-data research and paper simulation only

## Context

The closed v4 experiment rejected all three continuation rules. Every successful market work unit
was non-positive after costs, and aggregate gross PnL was already negative. Threshold tuning on the
same inspected interval would increase adaptive-overfitting risk and would not constitute a new
hypothesis.

V4 also retained nine raw-integrity failures caused by a long research scan racing the active
store's compaction lifecycle, plus five accounting failures where a delayed market-buy fill could
cost more than its fail-closed reservation. Retrying those consumed IDs is prohibited. Future
research needs a stable input view and conservative partial filling under the original reservation.

## Decision

Introduce the backward-readable `scalping-experiment-plan-2` contract for H-SCALP-004 through
H-SCALP-006. It represents sell-shock exhaustion, visible bid-replenishment reversal, and their
conjunction. Version 2 requires an exact sorted KRW market set, prospective minimum and fixed maximum
local receive times, an exact active-manifest hash, and exactly one trial per declared
hypothesis/cost/fold/market cell. Historical version-1 plan hashes and evidence remain unchanged.

Before a version-2 row scan, freeze the active immutable raw objects in a new same-volume directory.
Data files are checksum-verified and hard-linked; manifests are copied, reloaded, compared, and
hashed before an atomic directory rename. The collector is neither paused nor mutated. If any
manifest, file, checksum, path, timestamp, or hard-link operation is unsafe, creation fails and the
temporary view is removed. The snapshot is retained through experiment closure so later active-store
compaction cannot invalidate a registered input.

Commit the hypothesis and plan before reading selected rows. The subsequent bounded inventory binds
the exact prospective interval, fixed markets, clean-row filters, snapshot manifest hash, row counts,
and dataset hash. A registration-only ledger can then be generated only when all fixed markets meet
the declared requirements, the source revision exactly matches the plan, and all metrics, costs,
folds, markets, and holdout intent are closed. Trial planning and execution reject revision,
selection, or snapshot drift.

For paper market buys, fill quantity is additionally capped by the order's remaining reserved cash,
including taker fee. A price jump therefore yields a conservative partial fill and terminal
remainder rather than spending unreserved cash. This changes no real-order path and does not alter
production risk limits.

## Consequences

- V5 uses only post-v4-decision availability evidence and cannot tune on v4's inspected interval.
- Research reads a stable manifest/data view even while active collection and compaction continue.
- Snapshot creation consumes directory entries but not a second copy of Parquet payload bytes on the
  same NTFS volume; the snapshot must not be moved across volumes while trials remain open.
- The exact snapshot and registration add explicit lifecycle steps before the 270 bounded units.
- A failed snapshot, insufficient market, checksum mismatch, timeout, or source drift is a retained
  blocked/no-result condition, not permission to relax the plan.
- Final holdout access, authentication, private/order networking, real orders, automatic retry,
  model promotion, risk changes, and live activation remain unavailable.

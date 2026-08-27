# ADR-030: Market-Partitioned Scalping Trial Work Units

- Status: accepted
- Date: 2026-08-28
- Scope: offline public-data research and paper simulation only

## Context

The immutable v3 execution plan treated one hypothesis/cost/fold cell across all fifteen eligible
markets as one atomic work unit. Its second unit consumed 900.640 seconds and failed while reading a
later market with only 13.8194 seconds left. This is operational evidence that the global unit does
not fit its preregistered wall-time budget; it is not positive, negative, or null strategy evidence.
Changing the v3 limit or retrying either consumed v3 identifier would violate preregistration and
failure-retention rules.

## Decision

Add the backward-readable `scalping-trial-execution-plan-2` contract. A version-2 trial names exactly
one preregistered KRW market, and its ledger hyperparameters include that market. The unchanged three
hypotheses, two cost scenarios, and three chronological folds therefore form 270 deterministic
atomic units across the fixed fifteen-market scope. Trial order is hypothesis, cost, fold, then
sorted market. Every unit keeps the same fold partition, candidate rule, always-neutral comparison,
cost model, event cutoff, clean-row filters, sealed holdout boundary, and source/data lineage.

Each market unit is bounded to 500,000 input events total and 900 wall-clock seconds. Success or
failure is checkpointed before the next market. The fifteen market units belonging to a registered
hypothesis/cost/fold cell are later aggregated as a predetermined group; the runner provides no
performance-based market selection, retry, hidden-trial deletion, final-holdout access, champion
selection, order capability, or automatic promotion.

Version-1 plans remain byte-hash compatible and continue to represent their historical global
units. V3 and its two failed records remain immutable. V4 is separately preregistered against the
committed version-2 runner; its execution plan must be sealed before any trial is produced.

## Consequences

- The maximum durable loss from interruption is one market cell instead of a fifteen-market cell.
- The registered trial count grows from 18 global cells to 270 market cells without increasing the
  total intended market/fold/hypothesis/cost computation.
- Partial cross-market evidence cannot be mistaken for a completed aggregate cell; aggregation and
  multiplicity review remain separate downstream work.
- The final holdout remains sealed, and no v4 trial is authorized until its registration-only ledger
  and immutable execution plan bind the exact committed runner revision.

## Execution-plan evidence

The registration-only v4 ledger has chain hash
`8a1827182eecb96abd9306773ad5cc3c39fc28c3582090895c459ae53ba6678f`. A bounded rescan of 283
current detailed files reproduced the registered 9,157,974 rows and dataset hash. Execution-plan
digest `b4d60606d0ac6234c97f847fd0311322c857d0eb5d05ff77e9fa2a3db2564446` seals 180 validation and
90 test units with matching 500,000 per-market/total-event limits and a 900-second wall limit. No
trial or final-holdout access occurred while producing this evidence.

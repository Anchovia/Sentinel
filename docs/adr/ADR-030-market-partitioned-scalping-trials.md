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

## First-unit evidence

The first fixed-order unit (`f8be3a4c-8643-5713-8cf7-d83435735202`) executed once in dedicated
worktree `codex/scalping-v4-trial-1`. H-SCALP-001/base/fold-1/validation on KRW-BTC consumed 185,798
events and completed in 581.188 seconds, within both registered limits. The candidate closed 13
trades with Decimal net PnL `-195.319631205956800`; the identical-input always-neutral baseline was
`0`. The result is negative evidence for this one market cell and cannot stand in for the planned
fifteen-market aggregate or an experiment decision.

The append-only working ledger contains the registration plus this one succeeded trial and has chain
hash `e1c8a9cbee678f5d75fc804b207f86248d88523d1787bab3fb5bb5fb29d09b22`. The immutable artifact's
semantic digest is `837835a5cacd5f6c8601f12580d8f4a6b630e242dcac9d40bb29c50c8e67de3b`. No champion existed,
and no final-holdout access, authentication, private or order network, real order, promotion, or live
submission occurred. The runner did not start a second unit automatically.

## Final decision evidence

All 270 fixed-order v4 units were eventually consumed without retry: 253 succeeded with validated
artifacts and 17 retained bounded failures. Successful units contained 0 positive, 135 negative,
and 118 zero net-PnL results. The overlapping independent-trial net sum was
`-213726.256677355918048200` across 8,249 closed trades; it is not a portfolio equity curve.

Every predetermined base, stress, validation, and test aggregate was non-positive for each of
H-SCALP-001 through H-SCALP-003. The preregistered rejection condition therefore fired before a
positive-evidence Holm gate, champion comparison, or final-holdout review. The experiment decision
is `REJECT` for all three rules. Do not retry, tune, promote, or reinterpret v4 as investment
performance; new research requires a materially new hypothesis and preregistration.

Final report digest is
`0794f2e6bf9d68a49f506501eca774d0f0f91f3556f207fcb985096fce7c2a12`; the ledger's post-decision
chain hash is `009263444403a07487616db6698f5d26e9ce02e5041bc3572522e16ba3cb7c45` over 272 records. It
contains zero final-holdout records. Authentication, private/order network access, real orders,
promotion, risk changes, and live activation remained absent.

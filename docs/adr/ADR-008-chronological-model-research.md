# ADR-008: Chronological model research and sealed final holdout

- Status: Accepted
- Date: 2026-08-23

## Context

Model accuracy can look impressive when preprocessing sees future data, label windows overlap later
splits, costs are omitted, failed trials disappear, or a final holdout is reused for tuning. Phase 4
must establish reproducible research controls before adding complex models or strategy logic.

## Decision

Feature datasets retain source snapshot hashes, event time, actual availability time, a stable
feature schema, reference price, code version, and a dataset hash. Forward alpha labels become
available only when the future reference observation is itself available. The threshold includes a
configured round-trip cost and safety margin.

Datasets are partitioned in strict time order as train, validation, test, and final holdout. Random
shuffle is not exposed. Boundary labels are purged and later partitions may receive an embargo. A
normal evaluator rejects the final-holdout role. The final holdout has a separate one-shot vault;
access requires a review identifier and must also be persisted in the experiment ledger.

Every trial requires an immutable preregistration containing hypothesis, code/data/feature/label
lineage, model family, full parameter search space, planned metrics/splits, and the conservative cost
model. Undeclared parameters, metrics, or splits are rejected. Failed and negative trials remain in
an append-only hash-chain ledger. Final-holdout use must be preregistered and is accepted once only.

Initial baselines are deliberately small and inspectable:

- always-neutral and deterministic rule baselines;
- a rule-based regime classifier and deterministic diagonal Gaussian mixture comparator;
- standardized multinomial logistic alpha baseline;
- a small boosted-decision-stump candidate;
- a rule-based execution fill/cost baseline.

Transforms fit train data only. Probability temperature is selected from validation data only.
Test reports include multiclass Brier score, class scores, ECE, reliability bins, negative log
likelihood, uncertainty, abstention, sample warnings, trades, gross return, non-zero costs, and net
return. Accuracy alone cannot select a model.

Artifacts are immutable files with SHA-256 metadata and manifest verification. The registry has no
automatic promotion method. Unapproved models may enter only `EXPERIMENTAL` or `REJECTED`; later
states require a recorded human approver.

## Consequences

- Same ordered data, code, configuration, and seed reproduce dataset/split/artifact/report hashes in
  the validated runtime. Numerical artifacts remain tied to their Python/runtime version.
- The dependency-light baselines are comparison floors, not production recommendations and not
  evidence of profitability.
- The final holdout stays separated during ordinary validation. The in-process vault is not enough
  by itself; operators must persist its access record in the experiment ledger.
- Phase 4 does not train on the small local smoke sample, promote any model, or enable strategy/live
  behavior. HMMs, richer boosting, survival analysis, drift, and advanced multiple-testing controls
  remain candidates only after adequate data and preregistration.

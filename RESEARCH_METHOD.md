# QuantForge Research Method

## Principle

Research must test an economic or microstructure hypothesis under observable Upbit data constraints. It does not search indiscriminately for attractive equity curves. A result can be `REJECT`, `MORE_DATA`, `CONTINUE_RESEARCH`, `PAPER_CANDIDATE`, or `SHADOW_CANDIDATE`; automated work cannot declare a champion.

## Evidence hierarchy

Use original papers, official journal/conference pages, author preprints, official datasets, textbooks, and high-quality surveys in that order. Blogs and social media may suggest ideas but are not evidence. Record peer-review status, retrieval date, data period, costs, limitations, and reproduction assets.

## Preregistration

Before computation, create an immutable experiment/trial entry containing:

- hypothesis and economic rationale;
- available data and availability timestamps;
- features, label, horizon, target universe, and applicable regimes;
- train/validation/test/final-holdout plan;
- cost, latency, fill, and risk assumptions;
- parameter search space and planned trial count;
- primary/secondary metrics and falsification criteria;
- code commit, dataset ID, schema versions, and random seed.

Negative, failed, and null trials remain recorded.

The first short-horizon challenger additionally requires 24 hours and at least 20,000 trade plus
20,000 orderbook observations in each of three markets before any trial. It fixes three rule
hypotheses, two conservative cost scenarios, three chronological folds, profit/stop/time exits, and
a sealed 20-percent final holdout in the committed plan. Missing data produces a retained blocked
ledger with zero trials. Public book flow is named `snapshot_derived_ofi` and is never treated as
individual-order or exact queue evidence.

Every new growing-feed registration fixes both the maximum exchange timestamp and maximum local
receive timestamp. Inventory selection applies both bounds before identity checks, so an old
exchange event that arrives after registration cannot silently enter a later reconstruction. Older
plans without the additive receive bound remain readable and immutable; they are not retrofitted or
used as authority for a new dataset.

The eligible short-horizon selection also excludes rows already marked duplicate and rows carrying
any nonempty ingestion quality flag. The experiment plan, inventory, and event reader must bind and
apply the same filters. Excluded rows remain retained in raw storage as audit evidence; they are not
deleted or rewritten.

Large inventory fingerprints use bounded batches, ephemeral fixed-width sorted runs, and a k-way
merge. The merged bytes reproduce the original availability-tuple ordering and dataset SHA-256,
while a separate external event-ID merge retains exact duplicate detection. Every operator run has
an explicit wall-time budget and coarse progress evidence. Timeout removes scratch runs, writes no
research result, and executes no trial.

Eligible short-horizon computation is split again before execution. A committed
`scalping-trial-execution-plan-1` binds the exact runner revision, registration record, dataset,
eligible markets, chronological partition hashes, all 18 trial UUIDs, and event/time limits. One
command may execute only the next unrecorded validation/test trial. It loads one market window at a
time, compares the candidate and always-neutral baseline on identical events/costs, and atomically
retains success, null, or failure before advancing. Completed trials must remain a prefix of the
registered order. The runner has no final-holdout role.

If a registered global work unit cannot finish within its immutable wall-time budget, it is retained
as failed evidence and is not retried or enlarged. A new registration may instead use
`scalping-trial-execution-plan-2`, where market is an explicit preregistered hyperparameter. The
three hypotheses, two costs, three folds, and fixed fifteen markets then close 270 one-market work
units. They preserve the global market scope for predetermined aggregation and cannot select or
discard markets from observed performance. Each version-2 unit has one 500,000-event total cap and
the final holdout remains unavailable.

The execution preflight requires the ledger metric set to cover the plan, including median closed-
trade net return, closed-trade count, and non-fill count. An incomplete registration is blocked
before inventory scanning and is superseded by a new immutable registration rather than edited.

## Validation

- Use chronological rolling or expanding walk-forward validation.
- Use purging/embargo when feature and label windows overlap.
- Never fit transforms on future data or reconstruct historic universes with later information.
- Keep a final holdout sealed; using it retires that holdout version.
- Include fees, spread, slippage, latency, partial/non-fill, adverse selection, and signal decay.
- Compare to no-skill, always-hold/neutral, and simple linear/rule baselines.
- Report calibration, uncertainty, tail risk, turnover, capacity, and regime/market stability—not accuracy alone.

The implemented ordinary evaluator accepts validation or test partitions and raises on
`final_holdout`. Temperature calibration is selected from validation only. Test reports require a
positive per-trade cost and separate gross return, transaction cost, and net return. A one-shot final
holdout vault requires a review identifier; its access record must also be appended to the durable
experiment ledger.

## Multiple testing and overfitting

Track every trial and use appropriate controls such as PBO, Deflated Sharpe Ratio, White's Reality Check, Hansen's SPA, block/stationary bootstrap, and multiple-testing correction. Report IS-to-OOS degradation, sensitivity surfaces, subperiods, regimes, markets, and sample sufficiency.

## L2 limitation

Public Upbit orderbook observations are not assumed to contain individual order-level events or exact queue position. Derived order-flow imbalance must be named `snapshot_derived_ofi`; fill models use conservative queue approximations and sensitivity analysis.

## Promotion path

```text
EXPERIMENTAL -> VALIDATED -> PAPER -> SHADOW -> CANARY -> CHAMPION
```

Every step requires evidence; CANARY and CHAMPION require explicit human approval. Drift may trigger monitoring, reduced exposure, shadow-only, pause, retraining experiment, or incident—but never automatic replacement.

The current registry exposes immutable register/load operations only. It has no automatic promotion,
deployment, or live-inference activation method.

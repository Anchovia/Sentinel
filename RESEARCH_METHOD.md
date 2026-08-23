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

## Validation

- Use chronological rolling or expanding walk-forward validation.
- Use purging/embargo when feature and label windows overlap.
- Never fit transforms on future data or reconstruct historic universes with later information.
- Keep a final holdout sealed; using it retires that holdout version.
- Include fees, spread, slippage, latency, partial/non-fill, adverse selection, and signal decay.
- Compare to no-skill, always-hold/neutral, and simple linear/rule baselines.
- Report calibration, uncertainty, tail risk, turnover, capacity, and regime/market stability—not accuracy alone.

## Multiple testing and overfitting

Track every trial and use appropriate controls such as PBO, Deflated Sharpe Ratio, White's Reality Check, Hansen's SPA, block/stationary bootstrap, and multiple-testing correction. Report IS-to-OOS degradation, sensitivity surfaces, subperiods, regimes, markets, and sample sufficiency.

## L2 limitation

Public Upbit orderbook observations are not assumed to contain individual order-level events or exact queue position. Derived order-flow imbalance must be named `snapshot_derived_ofi`; fill models use conservative queue approximations and sensitivity analysis.

## Promotion path

```text
EXPERIMENTAL -> VALIDATED -> PAPER -> SHADOW -> CANARY -> CHAMPION
```

Every step requires evidence; CANARY and CHAMPION require explicit human approval. Drift may trigger monitoring, reduced exposure, shadow-only, pause, retraining experiment, or incident—but never automatic replacement.

# QuantForge Progress

## Current checkpoint

- Phase: 4 — Baseline Models
- Status: `COMPLETE`
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; no live adapter or real order endpoint implemented
- Actual orders executed: no
- Secrets accessed: no
- Data schema version: raw-event-envelope-1 / trade-bar-1 / feature-snapshot-1 / paper-ledger-1 / research-dataset-1
- Model schema version: model-artifact-1 / prediction-1

## Completed in Phase 4

- Added versioned causal feature-row and cost-aware forward-label builders retaining event time,
  availability time, source snapshot, code, feature, label, and dataset hashes.
- Added strict chronological train/validation/test/final-holdout splits. Boundary label windows are
  purged, later splits support embargo, random shuffle is absent, and ordinary evaluation rejects the
  final holdout.
- Added a one-shot reviewed final-holdout vault and an append-only experiment ledger. Trials require
  preregistration of parameter space, metrics, splits, cost model, code/data lineage, and holdout
  intent; failed/null results remain in the hash chain.
- Added dependency-light regime rule and diagonal Gaussian mixture baselines, always-neutral and
  standardized multinomial-logistic alpha baselines, a boosted-stump candidate, and a conservative
  execution-rule baseline.
- Added validation-only temperature scaling, multiclass/class Brier scores, ECE, reliability bins,
  negative log likelihood, entropy/margin uncertainty, OOD abstention, and low-sample warnings.
- Added non-zero-cost OOS evaluation and baseline comparison with atomic JSON reports.
- Added immutable model artifact metadata and a local registry that verifies artifact, metadata, and
  manifest SHA-256 hashes. No automatic promotion or deployment API exists.

## Validation evidence

```text
uv sync: PASS — Python 3.13.15, 78 locked packages; no Phase 4 dependency added
ruff: PASS — all checks passed
format check: PASS — 126 files formatted
mypy: PASS — 66 source files, no issues
pytest: PASS — 202 tests, 88.60% branch coverage
secret scan: PASS — 195 text files checked
dependency audit: PASS — no known vulnerabilities
chronological split: PASS — purge/embargo boundaries and four non-overlapping roles
final holdout: PASS — ordinary evaluator denied; reviewed vault access limited to one
preregistration: PASS — undeclared parameter/split/metric and post-close trials rejected
negative trials: PASS — failure retained and summary counts reconciled
baseline determinism: PASS — repeated logistic and mixture artifacts/predictions identical
calibration/cost report: PASS — Brier/ECE/NLL/reliability plus gross/cost/net reconciliation
model registry: PASS — immutable roundtrip and tamper detection
container build: PASS — quantforge:phase4 image sha256:cd6314d9...e2b76
container safety smoke: PASS — paper, live=false, all 6 live gates failed closed
```

The keyless smoke artifacts remain under ignored local `data/phase1-smoke/raw`; no exchange Secret
was read, no private endpoint was called, and no order capability exists.

## Known constraints

- Local `uv` is not globally installed; validation used a project-isolated bootstrap environment.
- Docker Compose configuration and the application container were validated; the full PostgreSQL/Prometheus/Grafana stack was not left running.
- GitHub CLI is not installed, so PR creation automation is not configured.
- Documentation refresh is currently a reviewed manual operation rather than an automated semantic
  diff.
- Public collection is a bounded CLI path; a supervised long-running service is not configured yet.
- The bounded collector does not persist positive coverage windows automatically. Bar consumers
  must provide reviewed collector-health coverage; absent coverage safely becomes a data gap.
- Snapshot-derived order-flow imbalance is not individual order flow or queue position.
- Conservative queue position is an explicit approximation; public L2 depth decreases cannot
  identify cancellations versus fills. `calibrated_l2` remains unavailable without lineage.
- The Phase 3 ledger is single-market, long-only KRW spot. Multi-asset accounting and private
  balance reconciliation are intentionally deferred.
- Phase 3 fee values are simulation assumptions, not a claim about Upbit's current fee schedule.
- Phase 4 baselines were validated on synthetic fixtures only. They are comparison floors, not
  production models, profitability evidence, or promotion candidates.
- The Gaussian mixture is diagonal and dependency-light; HMMs, richer boosting/survival models,
  drift monitoring, and advanced multiple-testing statistics remain unimplemented.
- Final-holdout protection is enforced by evaluator, vault, and trial-ledger contracts; durable
  operational access control will require the later database/audit service.
- Remote `origin/main` has not been pushed; external publication requires explicit owner approval.

## Next milestone

Begin Phase 5 with shared strategy inputs/decisions, deterministic strategy router, independent
pre-trade risk engine and sizing, portfolio/exposure controls, kill switch, attribution, and tests
proving strategy code cannot bypass risk or unsafe/stale state.

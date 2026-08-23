# QuantForge Handoff

## Restore context

Read, in order: `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, then this file. Do not infer implementation from the master prompt alone; inspect code and validation evidence.

## Current state

- Date: 2026-08-23 KST
- Completed phase: 4 — Baseline Models
- Current phase: 5 — Strategy and Risk (`IN_PROGRESS`)
- Git branch: `main` by explicit owner instruction
- Remote: `origin` -> `https://github.com/Anchovia/Sentinel.git`
- Product/package: QuantForge / `quantforge`
- Runtime target: Python 3.13.15, uv 0.12.5
- Default mode: paper
- Live order code: not implemented
- Actual orders: none
- Production Secrets: not requested or accessed
- Phase 0 checkpoint: `dafd09c feat: establish QuantForge safety-first foundation`
- Phase 1 checkpoint: `3bc2fd0 feat: add keyless Upbit public data pipeline`
- Phase 2 checkpoint: `2e48e6c feat: add deterministic replay bars and causal features`
- Phase 3 checkpoint: `32370e4 feat: add conservative paper execution and backtesting`

## Implemented

- Root product/safety/architecture/research/data/security/operations contracts and ADRs.
- Python package metadata, typed settings, Decimal boundary, order intent/state machine, risk decision contract, six-gate guard, Secret redaction, CLI, and minimal API.
- Unit tests, CI skeleton, Docker/Compose infrastructure skeleton, and developer scripts.
- Official Upbit public capability snapshot, isolated direct public transport, reviewed wire schemas,
  dynamic subscriptions, heartbeat, throttling, reconnect/backoff, duplicate detection, and
  malformed-message isolation.
- Exact raw event lineage, append-only ZSTD Parquet writer, row/time/checksum manifests,
  keyless finite collector, and public market-data metrics.
- Verified Parquet reader, availability-ordered virtual clock/replay, deterministic hash-chain
  checkpoints, and fixed golden replay hashes.
- Explicit positive coverage/data-gap semantics, Decimal 1s/5s/15s/1m bars, causal L2/trade-flow/
  volatility features, versioned feature registry, leakage tests, and data-quality runtime exports.
- Deterministic paper execution contracts and a public-data-only broker supporting market, best,
  limit, post-only, IOC, FOK, latency, partial/non-fill, cancel windows, conservative L2 queue
  evidence, depth haircuts, spread, slippage, adverse selection, and non-zero fees.
- Independent Decimal FIFO portfolio ledger with cash/position locks, duplicate-fill protection,
  gross/realized/unrealized/net PnL, cost attribution, exact invariants, and an append-only hash chain.
- Event-driven strategy-intent/risk-decision/backtest orchestration, atomic JSON reports,
  naive-versus-conservative comparison, and frozen deterministic Phase 3 hashes.
- Versioned feature datasets and cost-aware forward labels with exact availability lineage;
  chronological purge/embargo splits and a separated one-shot final holdout.
- Preregistered append-only experiment/trial ledger retaining failed results and restricting search
  space, metrics, split roles, summaries, and final-holdout access.
- Rule/Gaussian-mixture regime, neutral/logistic/boosted-stump alpha, and execution-rule baselines;
  validation-only temperature calibration, uncertainty/OOD abstention, and positive-cost OOS
  comparison reports.
- Immutable model artifact metadata and hash-verified registry with no automatic promotion or
  deployment operation.

## Validation

```text
Python: 3.13.15
uv lock/sync: PASS (78 packages)
Ruff + format: PASS
mypy: PASS (66 source files)
pytest: PASS (202 tests, 88.60% branch coverage)
Secret scan: PASS (195 text files)
pip-audit: PASS (no known vulnerabilities)
Compose config: PASS
keyless Upbit smoke: PASS (12 events; ticker/trade/orderbook; 3 valid manifests)
golden replay + checkpoint resume: PASS (fixed dataset/config/output hashes)
real Parquet replay twice: PASS (identical dataset/output hashes, 12 events)
container build and paper safety smoke: PASS (`quantforge:phase2`)
Phase 3 container: PASS (`quantforge:phase3`, sha256:a645f0a1...85c0b, all gates closed)
Phase 3 golden comparison: PASS (naive quantity 5; conservative quantity 0.5)
Phase 3 determinism: PASS (run, replay, ledger, fill, PnL, output hashes stable)
Phase 3 accounting: PASS (FIFO, locks, cash/position/PnL/equity/hash-chain invariants)
Phase 4 split/holdout: PASS (chronological, purged/embargoed, ordinary access denied)
Phase 4 experiments: PASS (preregistered search, failures retained, ledger verified)
Phase 4 baselines/evaluation: PASS (deterministic artifacts, calibration, abstention, positive costs)
Phase 4 registry: PASS (roundtrip immutable, tamper detected, auto-promotion absent)
Phase 4 container: PASS (`quantforge:phase4`, sha256:cd6314d9...e2b76, all gates closed)
```

## Important constraints

- Work/Codex are outside the real-time path.
- Any missing live gate blocks submission.
- `configs/risk.default.yaml` contains zero live limits intentionally.
- No private Upbit adapter or production credential source exists.
- The official Upbit SDK `0.9.0` is intentionally not installed under its verified incompatible
  WebSocket constraint; see ADR-005.
- Local Phase 1 smoke data is ignored at `data/phase1-smoke/raw` and may be deleted after inspection.
- `runtime_exports/data_quality/latest.json` is a generated, ignored, Secret-free local snapshot.
- Positive collection coverage is not yet emitted automatically by the bounded collector; do not
  infer no-trade bars from silence.
- The L2 queue model is conservative but uncalibrated. Public snapshots do not expose exact queue
  identity or distinguish fills from cancellations; do not promote `calibrated_l2` without an
  artifact ID and reviewed evidence.
- Paper fees and latency are explicit simulation values, not current Upbit capability claims.
- The Phase 3 ledger is single-market, long-only KRW spot and has no private balance source.
- Phase 4 models use synthetic fixtures only and are not promoted or connected to a strategy.
- The dependency-light diagonal mixture and boosted stumps are baselines/candidates, not substitutes
  for a preregistered, adequately sampled production study.
- Final-holdout one-shot state is in-process plus append-only record; durable authorization arrives
  with the later database/audit service.
- Local `main` is ahead of `origin/main`; publishing source to GitHub awaits explicit owner approval.
- Scheduled tasks must not be registered until their skills, inputs, schemas, and manual dry runs exist.

## Next actions

1. Commit the validated Phase 4 checkpoint on local `main`.
2. Define shared strategy input/decision contracts and deterministic routing without exchange access.
3. Implement an independent pre-trade risk engine, sizing, exposure/concentration, cooldown, stale
   data, uncertainty, and portfolio constraints.
4. Add kill-switch state/reason/audit contracts and tests that block every downstream submission.
5. Add strategy/model/market/regime PnL attribution; keep all outputs paper-only.

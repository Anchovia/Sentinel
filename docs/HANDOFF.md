# QuantForge Handoff

## Restore context

Read, in order: `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, then this file. Do not infer implementation from the master prompt alone; inspect code and validation evidence.

## Current state

- Date: 2026-08-23 KST
- Completed phase: 2 — Replay, Bars, and Features
- Current phase: 3 — Backtest and Paper Broker (`IN_PROGRESS`)
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

## Validation

```text
Python: 3.13.15
uv lock/sync: PASS (78 packages)
Ruff + format: PASS
mypy: PASS (49 source files)
pytest: PASS (159 tests, 94.61% branch coverage)
Secret scan: PASS (166 text files)
pip-audit: PASS (no known vulnerabilities)
Compose config: PASS
keyless Upbit smoke: PASS (12 events; ticker/trade/orderbook; 3 valid manifests)
golden replay + checkpoint resume: PASS (fixed dataset/config/output hashes)
real Parquet replay twice: PASS (identical dataset/output hashes, 12 events)
container build and paper safety smoke: PASS (`quantforge:phase2`)
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
- Local `main` is ahead of `origin/main`; publishing source to GitHub awaits explicit owner approval.
- Scheduled tasks must not be registered until their skills, inputs, schemas, and manual dry runs exist.

## Next actions

1. Commit the validated Phase 2 checkpoint on local `main`.
2. Define backtest event lifecycle and conservative execution assumptions before strategy code.
3. Implement a paper order book walker with fees, spread, latency, partial/non-fill, cancellation,
   adverse-selection hooks, and deterministic identifiers.
4. Add immutable order/fill/cash/position/PnL ledger events and accounting invariants.
5. Compare naive and conservative fills in a reproducible report; retain null/failed cases.

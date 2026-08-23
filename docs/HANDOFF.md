# QuantForge Handoff

## Restore context

Read, in order: `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, then this file. Do not infer implementation from the master prompt alone; inspect code and validation evidence.

## Current state

- Date: 2026-08-23 KST
- Completed phase: 1 — Public Market Data
- Current phase: 2 — Replay, Bars, and Features (`IN_PROGRESS`)
- Git branch: `main` by explicit owner instruction
- Remote: `origin` -> `https://github.com/Anchovia/Sentinel.git`
- Product/package: QuantForge / `quantforge`
- Runtime target: Python 3.13.15, uv 0.12.5
- Default mode: paper
- Live order code: not implemented
- Actual orders: none
- Production Secrets: not requested or accessed
- Phase 0 checkpoint: `dafd09c feat: establish QuantForge safety-first foundation`

## Implemented

- Root product/safety/architecture/research/data/security/operations contracts and ADRs.
- Python package metadata, typed settings, Decimal boundary, order intent/state machine, risk decision contract, six-gate guard, Secret redaction, CLI, and minimal API.
- Unit tests, CI skeleton, Docker/Compose infrastructure skeleton, and developer scripts.
- Official Upbit public capability snapshot, isolated direct public transport, reviewed wire schemas,
  dynamic subscriptions, heartbeat, throttling, reconnect/backoff, duplicate detection, and
  malformed-message isolation.
- Exact raw event lineage, append-only ZSTD Parquet writer, row/time/checksum manifests,
  keyless finite collector, and public market-data metrics.

## Validation

```text
Python: 3.13.15
uv lock/sync: PASS (78 packages)
Ruff + format: PASS
mypy: PASS (34 source files)
pytest: PASS (119 tests, 95.45% branch coverage)
Secret scan: PASS (140 text files)
pip-audit: PASS (no known vulnerabilities)
Compose config: PASS
keyless Upbit smoke: PASS (12 events; ticker/trade/orderbook; 3 valid manifests)
container build and paper safety smoke: PASS (`quantforge:phase1`)
```

## Important constraints

- Work/Codex are outside the real-time path.
- Any missing live gate blocks submission.
- `configs/risk.default.yaml` contains zero live limits intentionally.
- No private Upbit adapter or production credential source exists.
- The official Upbit SDK `0.9.0` is intentionally not installed under its verified incompatible
  WebSocket constraint; see ADR-005.
- Local Phase 1 smoke data is ignored at `data/phase1-smoke/raw` and may be deleted after inspection.
- Scheduled tasks must not be registered until their skills, inputs, schemas, and manual dry runs exist.

## Next actions

1. Commit the validated Phase 1 checkpoint on `main`.
2. Implement a deterministic virtual clock and stable replay ordering/cursor contracts.
3. Add replay checkpoint hashing and a golden sequence covering duplicates, out-of-order input,
   reconnect boundaries, and explicit gaps.
4. Build 1s/5s/15s/1m bars without silently treating missing intervals as zero volume.
5. Add versioned L2/trade/volatility features only after golden replay determinism passes.

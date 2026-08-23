# QuantForge Handoff

## Restore context

Read, in order: `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, then this file. Do not infer implementation from the master prompt alone; inspect code and validation evidence.

## Current state

- Date: 2026-08-23 KST
- Completed phase: 0 — Foundation
- Current phase: 1 — Public Market Data (`IN_PROGRESS`)
- Git branch: `main` by explicit owner instruction
- Remote: `origin` -> `https://github.com/Anchovia/Sentinel.git`
- Product/package: QuantForge / `quantforge`
- Runtime target: Python 3.13.15, uv 0.12.5
- Default mode: paper
- Live order code: not implemented
- Actual orders: none
- Production Secrets: not requested or accessed

## Implemented

- Root product/safety/architecture/research/data/security/operations contracts and ADRs.
- Python package metadata, typed settings, Decimal boundary, order intent/state machine, risk decision contract, six-gate guard, Secret redaction, CLI, and minimal API.
- Unit tests, CI skeleton, Docker/Compose infrastructure skeleton, and developer scripts.

## Validation

```text
Python: 3.13.15
uv lock/sync: PASS (76 packages)
Ruff + format: PASS
mypy: PASS (18 source files)
pytest: PASS (65 tests, 99.45% branch coverage)
Secret scan: PASS (107 text files)
pip-audit: PASS (no known vulnerabilities after pytest security update)
Compose config: PASS
container build and paper safety/API smoke: PASS
```

## Important constraints

- Work/Codex are outside the real-time path.
- Any missing live gate blocks submission.
- `configs/risk.default.yaml` contains zero live limits intentionally.
- No private Upbit adapter or production credential source exists.
- Scheduled tasks must not be registered until their skills, inputs, schemas, and manual dry runs exist.

## Next actions

1. Commit the validated Phase 0 checkpoint on `main`.
2. Retrieve current official Upbit `llms.txt`, SDK, WebSocket, rate-limit, and market-data documentation.
3. Create `docs/upbit_document_snapshot.json` and `docs/upbit_capability_manifest.yaml` with retrieval timestamps and source URLs.
4. Implement capability-aware public transport/domain mappings with recorded official fixtures.
5. Add keyless public-stream collection and reconnect tests before any private adapter work.

# QuantForge Handoff

## Restore context

Read, in order: `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, then this file. Do not infer implementation from the master prompt alone; inspect code and validation evidence.

## Current state

- Date: 2026-08-23 KST
- Completed phase: 6 — Private Exchange and Execution Safety
- Current phase: 7 — Dashboard and Operations (`IN_PROGRESS`)
- Git branch: `main` by explicit owner instruction
- Remote: `origin` -> `https://github.com/Anchovia/Sentinel.git`
- Product/package: QuantForge / `quantforge`
- Runtime target: Python 3.13.15, uv 0.12.5
- Default mode: paper
- Live order code: not implemented
- Actual orders: none
- Production Secrets: not requested or accessed
- Phase 0 checkpoint: `cfc1617 feat: QuantForge 안전 기반 구축`
- Phase 1 checkpoint: `136295c feat: 업비트 공개 데이터 파이프라인 구축`
- Phase 2 checkpoint: `41b64d1 feat: 결정적 재생과 인과 특징 구축`
- Phase 3 checkpoint: `0f7e3a1 feat: 보수적 모의 체결과 백테스트 구축`
- Phase 4 checkpoint: `b1a6b03 feat: 재현 가능한 기준 모델 연구 구축`
- Phase 5 checkpoint: `91962b9 feat: 전략 라우팅과 위험 게이트 구축`

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
- Causal strategy/market/model/portfolio/risk contracts and two transparent proposal-only strategy
  candidates with no exchange or order capability.
- Edge/priority/correlation-aware deterministic router, explicit lifecycle states, cooldown/loss/
  capacity gates, and liquidity/coverage-aware paper universe selection.
- Independent intent/risk gateway with snapshot binding, fail-closed hard checks, exact conservative
  sizing, daily-loss/drawdown/stale-data rejection, and no live mode acceptance.
- Reconciliation-gated hash-chain kill switch and exact strategy/model/market/regime attribution.
- Reviewed 2026-08-23 Upbit authentication, order/private-stream, order-test, lookup/cancel/chance,
  and current pocket-scoped rate-limit documentation without authenticated calls.
- Secret-isolated authentication/query-hash interfaces with no signer or Secret provider;
  Decimal-preserving MyOrder/MyAsset schemas and pure private subscription builders.
- Exact authenticated-order request/preflight contracts, deterministic burned identifiers, durable
  hash-chain state journal, fake/disabled private ports, and fake-only test-order adapter.
- Identifier-first timeout/restart reconciliation with no create retry; exact order/balance mismatch
  reporting; live adapter with no network capability even when all six gates are satisfied.

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
Phase 5 strategy/risk: PASS (proposal isolation, correlated dedup, cooldown, hard-limit resize/reject)
Phase 5 emergency tests: PASS (kill switch, daily loss, stale data, manual reconciled release)
Phase 5 validation: PASS (220 tests, 88.50% coverage, Ruff, format, mypy 75 files)
Phase 5 security: PASS (210-file Secret scan, no known dependency vulnerabilities)
Phase 5 container: PASS (`quantforge:phase5`, sha256:e006c71f...a202c, all gates closed)
Phase 6 private fixtures: PASS (MyOrder/MyAsset Decimal mapping and malformed isolation)
Phase 6 journal: PASS (fsync/reopen/hash/state/identity verification and tamper detection)
Phase 6 uncertain order: PASS (timeout/restart identifier lookup; zero duplicate create calls)
Phase 6 reconciliation: PASS (unknown/missing/state/balance mismatches block resume)
Phase 6 validation: PASS (237 tests, 87.20% coverage, Ruff/format, mypy 87 files)
Phase 6 security: PASS (228-file Secret scan, no dependency vulnerabilities, no private network client)
Phase 6 container: PASS (`quantforge:phase6`, sha256:55d48899...8e105, all gates closed, live network false)
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
- The owner requires each completed phase to be committed on `main` with a concise Korean
  Conventional Commit title and pushed to `origin/main`.
- Phase 5 strategies are synthetic-fixture, long-only entry candidates and not profitability
  evidence. Additional exit/cross-sectional/maker-taker work requires preregistered experiments.
- The kill-switch ledger is in-process; durable storage and authenticated cancellation controls are
  deferred. `cancel_and_flatten` remains approval- and liquidity-gated.
- Phase 6 authentication is a protocol only. There is no credential provider, JWT signer,
  authenticated HTTP/WebSocket client, real REST response parser, or private stream runtime.
- Test-order and private exchange behavior can run only through the in-memory fake. No private,
  test-order, or real-order endpoint was called.
- The execution journal is a single-writer file proof without database transaction/locking/backup.
  Durable multi-process operations and authenticated cancellations remain later work.
- Scheduled tasks must not be registered until their skills, inputs, schemas, and manual dry runs exist.

## Next actions

1. Commit and push the validated Phase 6 checkpoint on `main`.
2. Define redacted runtime-export, incident, audit, reconciliation, and performance schemas.
3. Add an authenticated read-oriented dashboard/API with no Secret or order endpoint access.
4. Add confirmed/idempotent emergency-control contracts backed only by local fakes and audit records.
5. Add backup/restore verification and operator runbooks; keep private/live network capability absent.

# Changelog

All notable changes are recorded here. The project follows semantic versioning once a public API is declared stable.

## [Unreleased]

### Added

- Phase 0 product, architecture, risk, research, data, security, threat, runbook, and recovery contracts.
- Python 3.13 uv project and developer/CI/container skeleton.
- Fail-closed typed settings and six-gate live submission guard.
- Decimal monetary boundary, initial order intent/state machine, risk decision contract, Secret redaction, CLI, health/safety API, and unit tests.
- Upbit official-document snapshot and public capability manifest.
- Credential-free ticker, trade, and orderbook WebSocket schemas, dynamic subscriptions, heartbeat,
  message throttling, reconnect/backoff, malformed-message isolation, and duplicate marking.
- Versioned raw event envelope with exact payload lineage, latency/clock-skew flags, Prometheus
  market-data metrics, and bounded public collection CLI.
- Atomic append-only ZSTD Parquet partitions with row/time statistics, JSON manifests, and SHA-256
  verification.
- Verified Parquet-to-EventEnvelope reader and offline `replay-raw` command.
- Availability-ordered virtual clock, deterministic replay sorting, duplicate/out-of-order and
  reconnect accounting, resumable checksummed checkpoints, and frozen golden hashes.
- Explicit `CoverageWindow`/`DataGap` contracts and deterministic Decimal 1s/5s/15s/1m trade bars
  that never encode missing data as zero volume.
- Versioned causal orderbook, trade-flow, and volatility feature calculators, stable feature
  registry, leakage guards, and atomic Secret-free data-quality runtime snapshots.
- Deterministic paper order/fill contracts covering market, best, limit, post-only, IOC, and FOK
  behavior with explicit non-zero fees and latency assumptions.
- Conservative L2 execution with depth haircuts, partial/non-fill behavior, passive queue
  approximation, cancellation latency, stale/gap fail-closed handling, spread, slippage, and
  adverse-selection attribution; retained a naive midpoint model only for comparison.
- Event-driven backtest orchestration over the availability-ordered replay clock with strategy/risk
  separation, stable input/configuration/code/seed lineage, frozen golden hashes, and atomic JSON
  comparison reports.
- Append-only Decimal portfolio ledger with reservations, duplicate-fill prevention, FIFO lots,
  realized/unrealized PnL, exact balance invariants, cost attribution, and a verified hash chain.

### Security

- Paper mode and all live approvals default to disabled.
- No live exchange adapter or real order endpoint exists.
- Repository-local Secret guard and structured redaction added.
- Updated pytest from the vulnerable 8.4.2 resolution to 9.1.1 after `PYSEC-2026-1845`; the repeated audit reported no known vulnerabilities.
- Pinned container images and CI actions to immutable digests/commits.
- Kept the incompatible official Upbit SDK out of the runtime instead of bypassing its declared
  dependency constraint; authenticated/private capabilities remain disabled.

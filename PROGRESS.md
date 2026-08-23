# QuantForge Progress

## Current checkpoint

- Phase: 2 — Replay, Bars, and Features
- Status: `COMPLETE`
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; no live adapter or real order endpoint implemented
- Actual orders executed: no
- Secrets accessed: no
- Data schema version: raw-event-envelope-1 / trade-bar-1 / feature-snapshot-1
- Model schema version: not created

## Completed in Phase 2

- Added a verifying Parquet reader that checks manifest path, SHA-256, schema, row count, raw-payload
  digest, event contract, and stored latency before replay.
- Implemented an availability-ordered virtual clock and replay engine with deterministic tie-breaks,
  duplicate suppression, out-of-order annotation, reconnect counters, dataset/config hashes, and a
  resumable output hash chain.
- Added checksummed atomic replay checkpoints and a frozen golden sequence covering a duplicate,
  out-of-order event, connection change, and explicit data gap.
- Implemented positive collection coverage and explicit data-gap contracts plus deterministic
  Decimal 1s/5s/15s/1m bars. Healthy no-trade bars use zero volume with null prices; gaps use null
  volume/count and cannot masquerade as no-trade.
- Implemented causal L2, trade-flow, and volatility baselines, a stable versioned feature registry,
  future-availability guards, and atomic Secret-free data-quality snapshots.
- Replayed the real Phase 1 twelve-event sample twice from Parquet with identical hashes and no
  network, authentication, or order capability.

## Validation evidence

```text
uv sync: PASS — Python 3.13.15, 78 locked packages
ruff: PASS — all checks passed
format check: PASS — 100 files formatted
mypy: PASS — 49 source files, no issues
pytest: PASS — 159 tests, 94.61% branch coverage
secret scan: PASS — 166 text files checked
dependency audit: PASS — no known vulnerabilities
compose validation: PASS — paper override renders successfully
public WebSocket smoke: PASS — keyless, 12 accepted, 3 event types, 3 Parquet files
Parquet verification: PASS — 12 rows, all 3 SHA-256 manifests valid
golden replay: PASS — fixed dataset/config/output hashes; checkpoint resume equals full replay
real raw replay: PASS — dataset 431b85c9...ecaa, output 6dfc929c...1603 on both runs
runtime snapshot: PASS — runtime_exports/data_quality/latest.json, network/auth/order false
container build: PASS — quantforge:phase2 image sha256:26752a965be7e2c97c77bb97a0c1f6b0e6cb8fd6ab44b71aeb5c126902e5c5e1
container safety smoke: PASS — paper, live=false, 6 failed gates
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
- Remote `origin/main` has not been pushed; external publication requires explicit owner approval.

## Next milestone

Begin Phase 3 with event-driven backtest lifecycle contracts, a conservative L2 paper broker,
explicit fees/spread/latency/slippage, partial/non-fill behavior, and an immutable Decimal ledger.

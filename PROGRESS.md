# QuantForge Progress

## Current checkpoint

- Phase: 1 — Public Market Data
- Status: `COMPLETE`
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; no live adapter or real order endpoint implemented
- Actual orders executed: no
- Secrets accessed: no
- Data schema version: raw-event-envelope-1 / upbit-public-v1
- Model schema version: not created

## Completed in Phase 1

- Retrieved the official Upbit documentation index, WebSocket guide/best practice, rate limits,
  ticker/trade/orderbook contracts, Python SDK guide, and official SDK package metadata.
- Recorded the source snapshot and reviewed public-only capability manifest. ADR-005 documents why
  the current official SDK was not installed under its declared `websockets <16` constraint.
- Implemented Decimal-preserving public wire schemas, DEFAULT-format dynamic subscriptions,
  per-connection message limiting, ping/pong policy, reconnect/backoff with jitter, and malformed
  message isolation.
- Implemented immutable raw event envelopes with exact payload text/hash, UTC/monotonic timestamps,
  latency and clock-skew quality flags, and bounded duplicate detection.
- Implemented atomic ZSTD Parquet partitions, adjacent JSON manifests, SHA-256 verification, orphan
  temporary-file cleanup, market-data metrics, and a bounded API-key-free collection CLI.
- Collected a real keyless twelve-message KRW-BTC sample spanning ticker, trade, and orderbook. The
  three local Parquet files contain twelve rows and all manifest checksums verify.

## Validation evidence

```text
uv sync: PASS — Python 3.13.15, 78 locked packages
ruff: PASS — all checks passed
format check: PASS — 77 files formatted
mypy: PASS — 34 source files, no issues
pytest: PASS — 119 tests, 95.45% branch coverage
secret scan: PASS — 140 text files checked
dependency audit: PASS — no known vulnerabilities
compose validation: PASS — paper override renders successfully
public WebSocket smoke: PASS — keyless, 12 accepted, 3 event types, 3 Parquet files
Parquet verification: PASS — 12 rows, all 3 SHA-256 manifests valid
container build: PASS — quantforge:phase1 image sha256:c4d3c3cf6254d6d7751ef9db020948b86c2ef7b28cd32e4dd48b95c158585e0f
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

## Next milestone

Begin Phase 2 with a deterministic virtual clock, immutable replay cursor/checkpoints, golden raw
event sequence, explicit gap semantics, and 1s/5s/15s/1m bar contracts before feature work.

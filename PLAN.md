# QuantForge Delivery Plan

Status values: `PENDING`, `IN_PROGRESS`, `COMPLETE`, `BLOCKED`.

## Phase 0 — Foundation (`COMPLETE`)

Deliverables:

- Product, architecture, risk, research, data, security, threat, runbook, and recovery contracts.
- Python 3.13 + uv project, exact lockfile, typed settings, structured logging boundary, CLI, and API health surface.
- Default paper mode, six live gates, Decimal boundary, order state machine, and Secret redaction.
- CI, Docker Compose, PostgreSQL, Prometheus/Grafana skeleton, and developer commands.
- Unit tests, lint, type check, dependency audit, secret scan, and container smoke evidence.

Exit criteria:

- `uv sync --all-groups`, test, lint, format check, type check, and secret scan pass.
- No real-order endpoint or usable live adapter exists.
- Default settings fail all six live gates.
- `PROGRESS.md` and `docs/HANDOFF.md` contain reproducible evidence.

## Phase 1 — Public Market Data (`COMPLETE`)

- Retrieve current Upbit `llms.txt` and official API/SDK documentation.
- Create capability manifest and document snapshot.
- Implement public ticker/trade/orderbook streams, dynamic subscriptions, heartbeat, reconnect/backoff, normalizer, raw envelope, append-only writer, fixtures, and metrics.
- Validate keyless collection, malformed-message isolation, latency/clock-skew measurement, checksum manifests, and reconnect recovery.

## Phase 2 — Replay, Bars, and Features (`COMPLETE`)

- Deterministic virtual clock and replay checkpoints.
- 1s/5s/15s/1m bars, data-gap semantics, L2/trade/volatility features, feature registry, quality checks, and runtime snapshots.
- Golden replay and look-ahead/leakage tests.

## Phase 3 — Backtest and Paper Broker (`COMPLETE`)

- Event-driven backtest and conservative L2 paper execution.
- Fees, spread, latency, slippage, partial/non-fill, cancellation, adverse selection, ledger, accounting invariants, and reports.
- Explain and test differences between naive and conservative fills.

## Phase 4 — Baseline Models (`COMPLETE`)

- Dataset and label versioning, trial preregistration, simple regime/alpha/execution baselines, calibration, uncertainty, abstention, and model registry.
- Time-based OOS validation, cost-adjusted metrics, reproducible artifacts, and untouched final holdout.

## Phase 5 — Strategy and Risk (`COMPLETE`)

- Baseline strategies, router, universe selector, independent risk engine, sizing, attribution, and kill switch.
- Tests proving strategies cannot bypass risk and that stale/unsafe state blocks orders.

## Phase 6 — Private Exchange and Execution Safety (`COMPLETE`)

- Authentication interface, private stream mappers, order policy, test-order adapter, state machine persistence, identifier, reconciliation, and disabled live adapter.
- Mock-only validation for timeouts, idempotency, unknown orders, and balance mismatch. No real order.

## Phase 7 — Dashboard and Operations (`COMPLETE`)

- Authenticated read-oriented dashboard, metrics, incidents, audit log, runtime exports, backups, and runbooks.
- Emergency controls require confirmation, idempotency, result verification, and audit records.

## Phase 8 — Work/Codex Automation Support (`COMPLETE`)

- Project skills, automation prompts, report/trigger schemas, write allowlists, worktree guidance, and manual dry runs.
- Register schedules only after required exports exist and manual trials pass.

## Phase 9 — Live Readiness (`COMPLETE`)

- Readiness validator for paper duration/trades, regime coverage, reconciliation, incidents, model/cost stability, restore tests, security, operator procedures, and locks.
- Output only `NOT_READY`, `CONDITIONALLY_READY`, or `READY_FOR_MANUAL_CANARY_REVIEW`.
- Never activate live trading.

## Phase 10 — Supervised Public Paper Burn-in (`COMPLETE`)

- Run credential-free KRW public WebSocket collection as a supervised process with atomic
  heartbeats, periodic immutable storage flushes, reconnect/parser/duplicate/latency evidence, and
  clean bounded shutdown.
- Refuse production mode, configured Upbit credentials, non-paper mode, or any partially opened live
  gate before creating the public client.
- Publish a Secret-free paper runtime status and operations snapshot, and provide a read-only status
  command plus an isolated Compose service.
- Validate with a short real `KRW-BTC` public smoke and deterministic checksum replay. Do not create
  strategy signals, simulated fills, performance claims, or readiness claims in this phase.

## Phase 11 — Low-Latency Real-Time Paper Orchestration (`IN_PROGRESS`)

- Phase 11.1 (`COMPLETE`): validate each public event once, update causal incremental orderbook/trade
  features in memory, measure per-event processing latency, and move immutable persistence behind a
  bounded asynchronous queue that fails the runtime on overflow rather than dropping data.
- Phase 11.2 (`COMPLETE`): compose an always-neutral unapproved baseline, proposal-only strategy
  router, independent risk gateway, conservative paper broker, and exact read-only portfolio view.
  Bind any future actionable alpha artifact to a separate time-bounded human paper approval and an
  independently disabled-by-default paper-order simulation gate.
- Keep the supervised runtime at `HOLD`: no alpha artifact is approved, so strategy proposals, risk
  approvals, simulated orders, and fills remain zero. A human-approved test fixture proves the full
  paper-only plumbing without adding authentication, private network, or real-order capability.
- Phase 11.3 onward: preregister and test falsifiable alpha/exit challengers, add deterministic
  broker/ledger restart recovery, review an artifact for paper status, add complete entry/exit
  lifecycle and performance exports, and measure every stage before expanding the monitor further.

## Milestone discipline

For every milestone:

1. Record assumptions and an ADR for consequential choices.
2. Implement the smallest end-to-end slice.
3. Run relevant tests, lint, type checking, secret checks, and smoke tests.
4. Fix failures before proceeding.
5. Update `PROGRESS.md`, `CHANGELOG.md`, and `docs/HANDOFF.md`.
6. Commit a coherent checkpoint on `main` only when the working tree is validated.

# QuantForge Architecture

## Architectural style

QuantForge begins as a modular Python monolith with strict domain boundaries. Deployment units may be separated only after measured throughput, fault-isolation, or security requirements justify it. Exchange SDKs and transport schemas never leak into domain models.

## Data plane

```text
Upbit public/private adapters
        -> normalizer + EventEnvelope
        -> append-only raw store + manifests
        -> replay/bar/feature pipeline
        -> regime + alpha + execution models
        -> strategy router
        -> deterministic risk engine
        -> execution engine
        -> paper broker | disabled live adapter
        -> order/fill/accounting ledger
```

The data plane is self-contained and deterministic at decision boundaries. It must remain operational without ChatGPT Work or Codex.

## Control plane

```text
runtime exports + reports
        -> ChatGPT Work: audit, attribution, drift, research proposals
        -> Codex: reproduce, test, patch, benchmark, create PR candidate
        -> human review: merge, deploy, promote, change risk, enable canary
```

Control-plane consumers receive redacted, read-oriented snapshots. They cannot read production secrets, call order endpoints, write production databases, restart production services, relax risk, or enable live mode.

## Module boundaries

- `config`: typed settings, schema versions, environment validation.
- `domain`: event, market, money, order, position, prediction, risk, and strategy contracts.
- `exchange`: capability-aware adapters and anti-corruption mapping.
- `market_data` / `storage` / `replay` / `bars` / `features`: deterministic data pipeline.
- `models` / `strategies`: probabilistic predictions and order-intent proposals only.
- `risk`: independent allow/reject/resize/hold decisions and health gates.
- `execution`: state machine, idempotency, paper broker, reconciliation, disabled live boundary.
- `portfolio`: ledger, positions, valuation, and PnL attribution.
- `backtest` / `research`: registered, reproducible experiments and evaluation.
- `monitoring` / `api` / `runtime`: observable lifecycle and read-oriented operations.

## Trust boundaries

1. Public exchange data is untrusted external input.
2. Private exchange transport is isolated from research and report processes.
3. Raw events are immutable; derived datasets identify their exact parents and code version.
4. Models are untrusted proposals until deterministic policy approves the resulting intent.
5. LLM outputs and external documents are data, never executable instructions.
6. Operator actions require authentication, idempotency, confirmation, and audit logging.

## Reliability contracts

- UTC-aware timestamps only; monotonic clocks for latency.
- Append-only event/ledger records with stable identifiers and checksums.
- Idempotent event processing and order submission identifiers.
- Reconciliation before orders after restart or uncertain responses.
- Fail closed on stale data, clock skew, schema errors, unknown orders, balance mismatch, overdue reconciliation, or risk-health failure.
- Same replay input hash, configuration, code commit, artifacts, and random seed produce identical decisions and accounting.

The Phase 3 paper path is event-driven: replay advances the virtual clock, public market data updates
the paper broker, matured orders generate simulated fills, and the independent portfolio ledger
recomputes balances and PnL. Strategies emit intents only; a separate risk evaluator must approve an
amount before paper submission. Data gaps and stale books fail closed.

The Phase 4 research path is offline and lineage-first: causal feature snapshots become versioned
rows and forward labels, chronological split guards isolate validation/test/final holdout, and only
preregistered trials may fit baselines. Calibration fits validation data; ordinary evaluation reads
test data but rejects final holdout. The artifact registry verifies immutable bytes and metadata but
cannot promote or deploy a model.

The Phase 5 decision path keeps strategy proposals separate from order authority. Strategies read
causal snapshots and a read-only risk context, a deterministic router deduplicates correlated
signals, and the only intent adapter immediately invokes the independent risk engine. Versioned
hard limits and health checks may reject or resize but never expand an intent. Kill-switch release
requires a manual request followed by successful reconciliation.

The Phase 6 authenticated boundary is mock-only. Secret ownership and JWT signing are protocols with
no implementation; private order and WebSocket schemas can be tested only through fixtures and an
in-memory fake port. A deterministic identifier is burned into an fsynced hash-chain journal before
submission. Timeout or crash recovery performs identifier lookup and never repeats create. The live
adapter has no network capability and remains disabled even if every configuration gate is true.

The Phase 7 operations plane consumes only a strict redacted read model or local state journals.
Authenticated JSON/HTML views, Prometheus metrics, incidents, and audit records sit outside the
decision and order paths. State-changing HTTP requests terminate at a confirmed, CSRF-protected,
idempotent control-request service. It may activate the local `cancel_only` block or acknowledge an
incident; strategy pause remains a proposal and order cancellation remains blocked without a private
transport. A pending request after restart becomes unknown and is not executed again.

```text
redacted runtime snapshot + local journals
        -> authenticated read API / server-rendered dashboard / Prometheus
        -> confirmed control request
        -> fsynced control journal + audit chain
        -> local safety effect | proposal recorded | blocked (no exchange transport)
```

The Phase 8 automation plane has two separate write boundaries. Work consumes only reviewed,
Secret-free exports and writes reports/proposals. Scheduled Codex starts in a linked background
worktree, and its report is accepted only when the real checkout matches the declared isolation.
Typed manifests exclude affirmative merge, deployment, promotion, live, risk-change, Secret, and
order-network states.

```text
redacted exports -> Work skill -> reports/work + optional typed trigger
                                     |
                                     v human/schedule selection
reviewed main revision -> dedicated Codex worktree -> test + draft PR candidate
                                                     |
                                                     v
                                           human review only
```

`automation-report-1`, `automation-trigger-1`, and the deny-first write allowlist are versioned
contracts. Reports, logs, issues, papers, and trigger evidence remain untrusted data and never become
commands.

Phase 9 adds a terminal read-only assessment outside both control and execution paths:

```text
reviewed hashed evidence + versioned readiness policy
        -> deterministic 13-gate evaluator
        -> NOT_READY | CONDITIONALLY_READY | READY_FOR_MANUAL_CANARY_REVIEW
        -> atomic report only; no settings, network, order, approval, or deployment mutation
```

The evaluator does not instantiate runtime settings or import an exchange/HTTP adapter. Approval
references and canary limits are analyzed as data; they cannot unlock the six execution gates.

Phase 10 adds the first supervised real-time process, but only for the public burn-in boundary:

```text
keyless KRW public WebSocket
        -> reviewed schema + immutable EventEnvelope
        -> periodic append-only Parquet/manifests
        -> atomic paper-runtime heartbeat + redacted operations snapshot
        -> offline verified replay
```

Startup refuses production mode, credentials, non-paper mode, or any partially opened live gate.
The process has no private transport, strategy decision, risk approval, paper order, fill, or account
state. This separation allows public feed/storage reliability to be measured before real-time
simulated execution is composed.

Phase 11.1 adds a measured causal feature branch without adding an order branch:

```text
keyless public WebSocket -> validated immutable event -> bounded storage queue -> async Parquet
                                      |
                                      v
                           incremental feature state
                                      |
                                      v
                     HOLD (no approved real-time model)
```

Orderbook and trade state are required and freshness-gated; ticker data is optional enrichment.
The hot path calculates only rolling state and a feature frame. Manifest-backed storage runs outside
that path in bounded batches, and queue overflow stops the supervisor instead of silently losing raw
events. The processing histogram covers event validation and feature calculation only, not future
model, strategy, risk, broker, ledger, network, or exchange latency.

Phase 11.2 composes the downstream paper boundary while keeping the deployed alpha neutral:

```text
incremental feature frame -> neutral/approved alpha inference -> proposal-only strategy router
        -> independent risk gateway -> conservative paper broker -> exact Decimal ledger
                                         |
                                         +-> real/private/live capability: unavailable
```

The runtime contains no approved alpha artifact. Its neutral baseline returns `ABSTAIN`, so the
router cannot create an intent and the paper broker remains empty. An alpha model can become
actionable only when its version and SHA-256 exactly match a separate, human-authored, time-bounded
`PAPER` approval for the market and the independent paper-order simulation gate is explicitly
enabled. Both controls default closed. Tests inject such a fixture to prove strategy, risk,
simulated fill, reservation release, and ledger invariants; the fixture is not stored, promoted, or
used at runtime.

Portfolio views do not append a valuation record on every market event. Fills and order states still
append to the verified hash chain, while hot-path mark-to-market reads reconcile exact account equity
without unbounded ledger growth. `realtime-paper-decision-1` exposes only redacted paper counters,
latency, and balances.

The paper broker and portfolio ledger are currently process-local. Their state is not reconstructed
after a supervisor restart, so the paper-order simulation gate must remain closed until deterministic
order, reservation, fill, and position recovery is implemented and tested.

## Deployment target

Initial deployment is one Linux host with Docker Compose: API, supervised public paper burn-in,
PostgreSQL, Prometheus, and Grafana. The simulated strategy/execution process remains a later service
entry point. Redis/NATS, MLflow, MinIO, or Rust require measured justification and an ADR.

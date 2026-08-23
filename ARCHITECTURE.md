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

## Deployment target

Initial deployment is one Linux host with Docker Compose: API/runtime, PostgreSQL, Prometheus, and Grafana. Market data and trading processes will gain separate service entry points in later phases. Redis/NATS, MLflow, MinIO, or Rust require measured justification and an ADR.

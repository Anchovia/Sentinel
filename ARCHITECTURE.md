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

- UTC-aware timestamps only; monotonic clocks for latency and live receive-order continuity. A local
  wall-clock regression advances availability from the prior accepted sample by monotonic elapsed
  time, records a quality flag and versioned normalization lineage, and keeps the affected feature
  frame `HOLD`; a monotonic-clock regression remains fatal.
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

Phase 11.3 adds `realtime-paper-recovery-1` under the durable paper-data volume. The checkpoint binds
the exact policy, market universe, orders, fills, reservations, FIFO lots, Decimal balances, ledger
hash chains, counters, and event cursor to one outer SHA-256. It never restores an orderbook: every
restart requires a new public snapshot before execution can be considered.

A clean shutdown first cancels every non-terminal paper order and releases its reservation, then
writes a clean checkpoint. Container `SIGTERM`/`SIGINT` is translated into that supervisor path and
closes the active public socket so a stalled receive cannot prevent cleanup. Only verified state is
automatically restored. An unclean marker with any economic activity cannot resume
an order: all recovered non-terminal orders are canceled, locks are released, and the independent
simulation gate remains blocked across later restarts. A checkpoint with no order, fill, lock, lot,
ledger record, cost, or balance change may recover as `EMPTY_UNCLEAN_RECOVERED` only while simulation
configuration is disabled. The public collector continues in neutral mode. Consequential
order/accounting changes are synchronously checkpointed and their durability cost is included in
decision latency; neutral heartbeats refresh the checkpoint off the market-event hot path.

Phase 11.9 adds a separate one-use operator review sidecar without adding a reset field to the
checkpoint. A stopped, clean, still-blocked checkpoint can receive a short-lived acknowledgement
bound to its exact checkpoint/policy/market hashes and reviewed clearance facts. On the next start,
the runtime—not the CLI—revalidates terminal broker state, absence of unknown orders and locks, and
exact ledger round trips before clearing only the recovery block. It then persists a hash-bound
consumption receipt. Replayed, expired, changed, malformed, or already consumed approval remains
fail-closed. Model approval, the paper-order policy gate, risk limits, runtime settings, and every
private/live boundary are unaffected.

Phase 11.10 adds a durable operations-evidence branch outside the market-event hot path:

```text
runtime heartbeat/terminal transition -> atomic continuity lease on D drive
                                      -> low-volume fsynced session/gap hash chain
                                      -> compact continuity + Work ops v2 exports
```

The next start classifies the prior lease as clean stop, failed stop, or missing-terminal
interruption. Public-WebSocket disconnects, stale-event intervals, and reconnect changes are local
observations only. The export explicitly refuses an exchange-completeness claim, and evidence before
the first recorded session remains unknown. Corrupt continuity evidence is preserved and marked
degraded; it does not open any model, paper-order, private, or live path.

Phase 11.4 widens observation without applying dense processing to every listing:

```text
credential-free market catalog + KRW quote snapshot
                 -> all KRW ticker monitoring -> 60-second opportunity ranking
                                                   |
                                                   v
                                  20-market trade + five-level orderbook focus
                                                   |
                                                   v
                         causal feature -> neutral paper decision composition
```

Catalog failure stops startup. Official warning markets remain observable but are never focused;
inactive, suspended, stale, and low-turnover pairs are excluded by the scanner. Focus replacement
is rate-limited and held for at least one minute. The complete market set remains in the raw and
feature boundaries, while neutral inference/risk/paper accounting runs only for the current focus.
The market-set hash namespaces recovery evidence so a listing change cannot restore state from a
different universe. BTC/USDT quote accounting remains outside this KRW-only boundary.

Phase 11.5 bounds local raw persistence without entering the real-time decision path:

```text
validated events -> bounded queue -> atomic ZSTD Parquet + v1 manifest
                                           |
                              completed creation hour
                                           v
                         verified compact Parquet + v2 supersession manifest
                                           |
                         30-day age / 50GiB oldest-first retention
                                           |
                   heartbeat free-space check (<20GiB -> fail-closed stop)
```

The host path may be injected through an ignored local Compose environment file and is mounted only
at `/app/data/paper`; without that override Compose uses the repository-local `./data/paper`
fallback. Compaction commits replacement data and lineage before retiring sources, and startup
resumes interrupted retirement markers. Active manifest totals, not host-drive guesses, drive the
monitor. Maintenance runs in the storage worker, outside the event/feature/decision hot path. Any
same-host path or preserved Docker volume is rollback convenience, not an off-host backup.

Phase 11.6 adds an offline research branch that never enters the supervised order path:

```text
checksummed detailed public rows -> registered cutoff and sufficiency gate
  -> causal feature replay -> fixed entry/exit rule -> conservative L2 paper broker
  -> exact Decimal ledger -> blocked/negative/candidate research evidence
```

The first plan fixes three rules, two cost scenarios, and three chronological folds before
execution. Fewer than 24 hours and 20,000 trade plus 20,000 orderbook events in each of three
markets stops before any trial. The final 20 percent remains sealed. Synthetic tests may exercise a
complete paper round trip but cannot create a runtime approval, enable the paper-order gate, access
an exchange credential, or become a performance claim.

Phase 11.8 adds an incremental evidence branch in the storage worker, still outside the feature and
decision hot path:

```text
active immutable manifests -> verify new/changed/expired Parquet files
  -> cache file fingerprint + integrity/anomaly/market summary
  -> reconcile bounded active-manifest aggregate -> atomic quality index
  -> version-3 Work quality export + compact local monitor totals
```

The aggregate may report that current data is sufficient to preregister a new experiment, but that
state has no edge to the experiment runner, model approval, paper-order gate, private transport, or
live submission. A failed verification aborts the refresh and leaves the prior valid index intact.
Cross-file duplicate identities and exact exchange completeness remain replay concerns.

## Deployment target

Initial deployment is one Linux host with Docker Compose: API, supervised public paper burn-in,
PostgreSQL, Prometheus, and Grafana. The simulated strategy/execution process remains a later service
entry point. Redis/NATS, MLflow, MinIO, or Rust require measured justification and an ADR.

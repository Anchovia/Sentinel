# QuantForge Progress

## Current checkpoint

- Phase: 11.1 — Low-Latency Real-Time Feature Path
- Status: checkpoint `COMPLETE`; Phase 11 `IN_PROGRESS`
- Planned implementation phases: 0–10 complete; Phase 11.1 feature-path checkpoint complete
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; the live adapter has no network capability
- Readiness result: `NOT_READY`
- Actual orders executed: no
- Private/authenticated Upbit calls: no
- Production Secrets accessed: no
- Scheduled task registration: none
- Automatic merge/deploy/model promotion/live activation: unavailable

## Completed in Phase 11.1

- Added a strict causal incremental pipeline for microprice, spread, top/total orderbook imbalance,
  depth, book flow, rolling 1s/5s/15s trade flow/returns, realized volatility, and optional ticker
  enrichment without recomputing retained history on each event.
- Added required-state freshness/warmup gates, p50/p95/p99/max feature-processing evidence, a 5ms
  budget counter, deterministic verified replay, and an atomic Secret-free real-time snapshot.
- Moved raw Parquet writes behind a bounded 65,536-event queue and 512-event batch worker. Periodic
  commits continue under uninterrupted traffic; overflow or worker failure stops the runtime instead
  of dropping events.
- Extended the local monitor with only the processing latency and current decision. The decision is
  fixed at `HOLD` because no reviewed real-time model is composed, and every private/order/live
  capability remains false.
- Replayed 10,000 retained events inside the final container: 5,912.84 events/s, 0.169ms p50,
  0.285ms p95, 0.332ms p99, 0.750ms max, and zero 5ms budget breaches. These are feature-core
  measurements, not end-to-end strategy, order, network, or exchange latency.
- Confirmed the final restarted live public collector periodically committed 436 new rows while
  receiving continuous traffic, with storage queue depth 0 and overflow count 0.

## Completed in Phase 10.1

- Added a self-contained Korean `runtime_exports/ops/paper-monitor.html` view that requires no web
  server or dashboard token, reloads every five seconds, and shows public price, collection health,
  last-event freshness, parser/reconnect/duplicate counts, retained rows/files/bytes, and disk space.
- Added strict manifest-backed retained storage totals that are reconstructed on collector startup
  and increased only after immutable Parquet/manifests commit. Missing, duplicate, escaping,
  malformed, or size-damaged retained storage fails closed instead of displaying a false total.
- Versioned new snapshots as `paper-runtime-2` while retaining read compatibility with version 1.
  The monitor excludes raw paths, run identifiers, policy hashes, payloads, credentials, account
  data, control actions, and all order capability.
- Kept the authenticated operations dashboard unchanged and fail-closed. This new local file is a
  public-data observer only, not a trading interface or production GUI.
- Added ADR-015, runbook instructions, storage/runtime/HTML tests, and retained the minimal public
  README without changes.

## Completed in Phase 10

- Re-fetched the official Upbit `llms.txt`, WebSocket best-practice, and rate-limit pages. The
  unauthenticated public endpoint, 120-second idle timeout, ping/pong, reconnect, and WebSocket
  connection/message policies remain compatible with the direct public adapter.
- Added a supervised public burn-in runtime that refuses production, credentials, non-paper mode,
  or even a partially opened set of the six live gates before creating a client.
- Added atomic `paper-runtime-1` heartbeats, periodic immutable Parquet/manifests, parser/reconnect/
  duplicate/latency counters, a live public-market operations snapshot, graceful bounded shutdown,
  and offline status health checks.
- Added `run-paper` and `paper-status`, plus a separate non-root, read-only Compose service with a
  persistent paper-data volume and only the runtime export bind it needs.
- A host smoke accepted and checksummed 30 real public `KRW-BTC` messages, then replayed the exact
  dataset offline. A final read-only container smoke accepted 10 more public messages.
- No strategy/model/risk decision, paper order, fill, account state, private endpoint, credential,
  or order path was used. This phase is public feed/storage burn-in only.
- Added ADR-014 and updated architecture, data, security, limitations, runbook, capability, progress,
  and handoff records. The public README remained unchanged and minimal.

## Completed in Phase 9

- Added closed `readiness-evidence-1`, `readiness-policy-1`, and `readiness-report-1` contracts. Every
  input component binds a UTC observation and source hash; paper/performance counts and approved
  code/model hashes must agree, and four approval references must be distinct.
- Added a deterministic 13-gate evaluator covering paper days/trades/regimes, reconciliation, data
  availability, incident rate, model stability, cost-inclusive drawdown/expectancy, cost calibration,
  order-test, production backup/restore, security, operator runbooks, closed live locks, and release
  approvals plus a small manually monitored canary plan.
- Added hard and preferred threshold tiers. Any missing, malformed, stale, future, contradictory,
  UNKNOWN-order, critical-incident, uncalibrated-cost, local-only-backup, unreviewed-live-adapter, or
  oversized-canary evidence fails closed.
- Added `validate-live-readiness`, which loads only reviewed evidence/policy and writes an atomic
  Secret-rejected report. It does not instantiate runtime settings or import exchange/HTTP transport.
- The highest status is `READY_FOR_MANUAL_CANARY_REVIEW`, still with human approval required and all
  real-order/network/Secret/settings/live/risk/model/deployment effects fixed false. There is no
  activation method.
- Added conservative default policy configuration, protected it from scheduled Codex changes, and
  copied reviewed configs into the runtime image so the validator is usable there.
- Added ADR-013 and readiness evidence, architecture, risk, security, data, recovery, runbook, and
  handoff documentation. The public README remained unchanged and minimal.

## Validation evidence

```text
Python: PASS — 3.13.15; no Phase 11.1 dependency added
ruff: PASS — all checks passed
format check: PASS — 210 files formatted
mypy: PASS — 108 source files, no issues
pytest: PASS — 322 tests, 86.83% branch coverage
secret scan: PASS — 311 text files checked
dependency audit: PASS — no known vulnerabilities
Compose config: PASS — base + paper overlays including healthy paper-runtime
container build: PASS — quantforge-paper-runtime sha256:326bfe81...bae663a
verified 10,000-event feature replay: PASS — 5,912.84 events/s; p50 0.169ms;
  p95 0.285ms; p99 0.332ms; max 0.750ms; 0/10,000 over 5ms
sustained public runtime: PASS — 437 accepted, 436 periodic committed, retained rows 27,493;
  queue depth 0/65,536; overflows/parser errors/reconnects 0; HOLD; order capability false
live feature snapshot: PASS — p50 0.331ms; p95 0.509ms; p99 0.582ms; max 0.711ms;
  0 budget breaches; no approved model/private/order/live capability
actual/private/test orders: NONE
schedule registration: NONE
```

## Known constraints

- `NOT_READY` is the correct operational result. There is no sustained representative paper history,
  authenticated order-test evidence, calibrated production costs, production-grade encrypted off-
  host restore, reviewed live adapter/order network, multi-operator drills, or bound release/risk/
  model/operator approvals.
- The complete synthetic fixture proves classifier behavior only. It is not market, profitability,
  recovery, security, approval, or live evidence.
- The conservative numeric thresholds are governance defaults, not profit/safety guarantees. They
  must not be automatically relaxed and require human review plus a new consequential record.
- The validator does not assemble evidence from production systems. Producers and human reviewers
  must create a Secret-free bundle with reproducible hashes; absent evidence stays absent.
- Phase 8 tasks remain unregistered and representative performance/model/incident exports are not
  populated. Local schedules require the computer and desktop app.
- The Windows host lacks `uv` and `make` on PATH, so exact Make targets were not run in this phase;
  their equivalent locked project-venv commands passed. Container builds use the pinned uv image.
- The public collector and incremental feature path are supervised, but sustained coverage has not
  accumulated and real-time inference/strategy/risk/paper-broker/ledger/performance orchestration is
  not yet composed.
- The Korean public-data monitor shows the supervised feed and retained storage only. The
  authenticated dashboard and Grafana remain developer/operations skeletons, and strategy/risk/
  broker/ledger results do not exist yet.
- Dashboard, local journals, backup proof, public-L2 fill approximation, missing authenticated
  transport, and synthetic research limitations remain documented.

## Next milestone

Do not enable live trading. Keep the public burn-in and Korean monitor running; measure coverage,
restarts, parser failures, gaps, disk growth, and retention. The next implementation composes
versioned baseline inference with proposal-only strategies, independent paper risk, the conservative
paper broker, exact ledger, and representative performance/model/data exports on the measured
causal feature path.
Extend the monitor into a polished paper-performance GUI only after those contracts produce stable
data. Production storage/backup/TLS/RBAC/network design and any authenticated dry-run work remain
separately reviewed.

# QuantForge Progress

## Current checkpoint

- Phase: 10.1 — Korean Public Data Monitor
- Status: `COMPLETE`
- Planned implementation phases: 0–10 complete; 10.1 visibility checkpoint complete
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; the live adapter has no network capability
- Readiness result: `NOT_READY`
- Actual orders executed: no
- Private/authenticated Upbit calls: no
- Production Secrets accessed: no
- Scheduled task registration: none
- Automatic merge/deploy/model promotion/live activation: unavailable

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
Python: PASS — 3.13.15; no Phase 10 dependency added
ruff: PASS — all checks passed
format check: PASS — 207 files formatted
mypy: PASS — 107 source files, no issues
pytest: PASS — 307 tests, 86.60% branch coverage
host public smoke: PASS — 30 accepted/committed, 0 parser errors, 0 reconnects, no auth/private/order
host verified replay: PASS — 30 inputs, dataset ed2124cb...f4ea, output e3cf7e53...4c29
secret scan: PASS — 307 text files checked
dependency audit: PASS — no known vulnerabilities
Compose config: PASS — base + paper overlays including paper-runtime
container build: PASS — quantforge:phase10 sha256:9fade54b...0522
monitor container rebuild: PASS — quantforge-paper-runtime sha256:37e8961e...1e087
container safety: PASS — paper, live=false, all six gates failed closed, credentials=false
container public smoke: PASS — 10 accepted/committed, 0 parser errors/reconnects, all safety flags false
Korean monitor image: PASS — self-contained HTML emitted and refreshed from `paper-runtime-2`
retained storage restore: PASS — 7,671 rows, 48 files, 1,568,641 bytes recovered before reconnect
restarted sustained runtime: PASS — healthy public WebSocket; retained totals increased to 8,109 rows,
  51 files, 1,656,597 bytes; 0 parser errors/reconnects; no auth/private/order/live capability
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
- The public collector is supervised, but sustained coverage has not accumulated and real-time
  strategy/risk/paper-broker/ledger/performance orchestration is not yet composed.
- The Korean public-data monitor shows the supervised feed and retained storage only. The
  authenticated dashboard and Grafana remain developer/operations skeletons, and strategy/risk/
  broker/ledger results do not exist yet.
- Dashboard, local journals, backup proof, public-L2 fill approximation, missing authenticated
  transport, and synthetic research limitations remain documented.

## Next milestone

Do not enable live trading. Keep the public burn-in and Korean monitor running; measure coverage,
restarts, parser failures, gaps, disk growth, and retention. The next implementation composes causal
real-time bars/features with versioned baseline inference, proposal-only strategies, independent paper risk,
the conservative paper broker, exact ledger, and representative performance/model/data exports.
Extend the monitor into a polished paper-performance GUI only after those contracts produce stable
data. Production storage/backup/TLS/RBAC/network design and any authenticated dry-run work remain
separately reviewed.

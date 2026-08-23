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
- Versioned feature-dataset and cost-aware forward-label contracts with event/availability lineage,
  chronological train/validation/test/final-holdout partitioning, boundary purge, embargo, and a
  one-shot reviewed holdout guard.
- Append-only preregistered experiment/trial ledger that rejects undeclared parameters, metrics, and
  splits; preserves failures; reconciles summaries; and limits final-holdout use.
- Dependency-light rule regime, diagonal Gaussian mixture, always-neutral, standardized
  multinomial logistic, boosted-stump, and execution-cost baselines.
- Validation-only temperature scaling, Brier/ECE/reliability calibration reports, uncertainty,
  out-of-distribution abstention, sample warnings, and non-zero-cost OOS baseline comparison.
- Immutable local model registry with artifact/metadata/manifest SHA-256 verification and no
  automatic promotion path.
- Causal shared strategy/risk inputs, transparent order-flow momentum and liquidity-shock reversal
  proposals, deterministic correlation-aware routing, and liquidity-aware universe selection.
- Independent fail-closed paper risk gateway with intent/snapshot binding, hard health/exposure/loss/
  turnover/rate limits, exact conservative sizing, and no strategy-side order capability.
- Manual-release hash-chained kill switch and exact strategy/model/market/regime attribution ledger.
- Refreshed official Upbit authentication, private-stream, order, test-order, lookup, cancellation,
  order-chance, and rate-limit capability observations without using an authenticated endpoint.
- Secret-isolated authentication/query-hash contracts and Decimal-preserving MyOrder/MyAsset
  schemas, fixture mappers, and private subscription builders.
- Strict authenticated-order shapes, deterministic account-wide identifiers, dynamic preflight,
  fsynced hash-chain order journal, and exact order/balance reconciliation.
- Mock-only test-order/private ports, identifier-first no-retry timeout/crash recovery, and a live
  adapter that remains disabled even when all six configuration gates pass.
- Versioned Decimal-preserving operations read models, atomic Secret-rejecting runtime exports, an
  authenticated server-rendered dashboard/API, and a provisioned Grafana paper-health dashboard.
- Separate bearer/CSRF dashboard authentication, append-only incident/audit/control journals,
  confirmed idempotent emergency requests, and fail-closed interrupted-result recovery.
- Local-only cancel-only activation and incident acknowledgement; strategy pause stays a proposal
  and cancel-all stays blocked because no exchange cancellation transport exists.
- Explicit-source checksummed local backups and empty-target paper restore drills that reject
  Secrets, symlinks, path traversal, unmanifested files, and checksum damage.
- Secret-free `export-operations` CLI output and expanded Prometheus incident, control, exposure,
  reconciliation, backup, disk, kill-switch, and authentication metrics.
- Nine repository-local Work/Codex skills and ten standalone scheduled-task prompts with an explicit
  unregistered Asia/Seoul schedule catalog, narrow network defaults, and first-run review policy.
- Closed `automation-report-1` and `automation-trigger-1` contracts, deny-first write allowlists,
  credential-shaped content rejection, path/symlink guards, and non-ordering validation commands.
- Actual linked-worktree inspection that rejects Codex scheduled reports from the primary checkout
  and requires a non-main candidate branch plus evidence/validation before a source-change result.
- Official scheduled-task setup and worktree cleanup guidance with report-only Work, draft-PR-only
  Codex, valid no-op/blocked outcomes, and no automatic merge, deployment, model promotion, risk
  change, live activation, Secret access, or order path.
- Versioned `readiness-evidence-1`, two-tier `readiness-policy-1`, and immutable
  `readiness-report-1` contracts covering 13 evidence gates and exact input/policy hashes.
- A deterministic live-readiness evaluator whose highest output is manual-canary review eligibility;
  every order/network/Secret/settings/live/risk/model/deployment effect is false-only.
- Conservative policy defaults for paper duration/trades/regimes, reconciliation, data/incidents,
  model/drawdown/net expectancy, cost calibration, dry-run order-test, production recovery,
  security/runbooks, closed live locks, independent approvals, and a small canary plan.
- Secret-rejecting atomic readiness exports and a non-ordering `validate-live-readiness` CLI that
  does not load runtime settings or import exchange/HTTP transport.
- A fail-closed `run-paper` public burn-in supervisor with duration/message bounds, periodic raw
  Parquet flushes, lifecycle heartbeats, reconnect/parser/duplicate/latency evidence, graceful
  shutdown, and no authentication, private endpoint, or order capability.
- A read-only `paper-status` health command, live public-market operations snapshots, and a separate
  read-only Compose service for sustained `KRW-BTC` public observation.
- A self-contained Korean public-data monitor that refreshes every five seconds without a web
  server, token, account access, or order control, plus manifest-backed retained row/file/byte
  totals that survive supervised collector restarts.
- A causal incremental real-time feature pipeline for orderbook microprice/imbalance/depth/flow,
  rolling 1s/5s/15s trade flow/returns/volatility, optional ticker enrichment, freshness gates, and
  per-event p50/p95/p99 processing evidence.
- A bounded asynchronous storage queue and batched worker that keep Parquet persistence off the
  feature hot path, periodically commit under continuous traffic, and fail the supervisor on queue
  overflow rather than silently dropping an event.
- A verified `benchmark-realtime` command, `paper-runtime-3` queue-health fields, an atomic
  `realtime-pipeline-1` HOLD-only snapshot, and a minimal millisecond-processing panel in the local
  Korean monitor. No approved model, strategy order, private network, account, or live capability
  was added.
- A fail-closed real-time paper orchestrator that composes causal features, an unapproved
  always-neutral baseline, proposal-only strategies, independent risk, conservative simulated
  execution, and exact Decimal portfolio accounting while keeping the deployed state at `HOLD`.
- A strict time-bounded human paper-approval contract bound to alpha model version, artifact SHA-256,
  and market scope. No approval artifact is shipped; a test-only approved fixture exercises the full
  strategy-to-risk-to-paper-fill-to-ledger path.
- A separate disabled-by-default paper-order simulation gate, so a matching model approval alone
  cannot create even a simulated order.
- A strategy-level invariant requiring the alpha decision to be explicitly `TRADE`; both `HOLD` and
  `ABSTAIN` now block every baseline strategy before an order intent can exist.
- Atomic `realtime-paper-decision-1` exports, a verified `benchmark-paper-decision` command, and a
  compact monitor panel for model review, proposals, simulated orders/fills, and paper PnL.
- Read-only portfolio valuation that avoids one ledger append per market event and reconciles rare
  Decimal associativity remainders to authoritative cash and position balances while preserving
  prior frozen replay hashes.
- A hash-bound `realtime-paper-recovery-1` checkpoint containing policy-bound paper orders, fills,
  reservations, FIFO lots, Decimal balances, verified ledger chains, counters, and event cursor.
- Clean-restart restoration that discards stale books, plus fail-closed unclean recovery that cancels
  non-terminal paper orders, releases locks, preserves evidence, and keeps simulation blocked.
- Graceful container signal handling and a narrowly bounded empty-state recovery: only a disabled
  simulation with no economic or ledger activity can clear an unclean marker automatically.
- Active public WebSocket closure during a stop request so stalled network receive cannot prevent
  storage flush, paper-order cancellation, reservation release, or clean checkpoint persistence.
- Credential-free dynamic discovery of every current Upbit KRW pair, with strict public catalog and
  quote-ticker schema validation, warning-market exclusion, and market-set-hashed recovery state.
- A tiered all-KRW paper universe: ticker monitoring across the full listing set and rotating dense
  trade/five-level-orderbook processing for 20 liquid, fresh, active short-horizon candidates.
- Atomic `realtime-universe-1` evidence, `paper-runtime-4` scope/focus counters, bounded focus dwell,
  and a compact Korean monitor view showing total coverage, focused markets, exclusions, and
  rotations. All model, paper-order, private, and real-order controls remain closed.
- Incremental exact portfolio aggregates that keep focused risk decisions from rescanning every
  monitored market on each event.
- Configurable host bind storage for bulk paper data, with the current local runtime isolated on
  `D:/Sentinel-Data` and the machine-specific override excluded from Git.
- Checked ZSTD compaction with version-2 supersession manifests and interruption-resumable retirement
  markers that preserve replay rows while reducing completed-hour small files.
- A 30-day raw retention ceiling, 50GiB active-data cap, 20GiB free-space fail-closed stop, and
  `paper-runtime-5`/Korean-monitor lifecycle evidence for compaction, pruning, reclaimed space, and
  actual filesystem capacity.
- A 60-second Compose stop grace period for bounded queue flush and clean paper checkpoint closure.

### Security

- Paper mode and all live approvals default to disabled.
- No live exchange adapter or real order endpoint exists.
- Repository-local Secret guard and structured redaction added.
- Updated pytest from the vulnerable 8.4.2 resolution to 9.1.1 after `PYSEC-2026-1845`; the repeated audit reported no known vulnerabilities.
- Pinned container images and CI actions to immutable digests/commits.
- Kept the incompatible official Upbit SDK out of the runtime instead of bypassing its declared
  dependency constraint; authenticated/private capabilities remain disabled.

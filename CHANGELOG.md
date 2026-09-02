# Changelog

All notable changes are recorded here. The project follows semantic versioning once a public API is declared stable.

## [Unreleased]

### Added

- A prospective v5 sell-shock mean-reversion contract with three new fixed hypotheses, exact
  market partitions, post-v4 receive-time bounds, immutable hard-link raw snapshots, content-bound
  inventories, and registration-only ledger generation before bounded trials.
- Conservative paper market-buy fill capping against the exact remaining cash reservation,
  including taker fees, so price jumps produce partial fills instead of accounting-invariant
  failures.
- The retained v5 data-readiness result: 8,508,661 post-v4 clean events fingerprinted without an
  integrity race, eight of fifteen fixed markets eligible, decision `BLOCKED`, and zero trials or
  final-holdout access.
- A separate availability-only v6 replacement that preserves every reversal hypothesis and
  assumption while fixing the eight markets that passed v5's unchanged readiness criteria and
  mechanically closes 144 work units before its own row scan.
- A deterministic scalping-experiment finalizer that validates the complete fixed-order ledger and
  every successful artifact hash, rejects incomplete or holdout-accessed runs, retains failures,
  writes immutable JSON/Markdown evidence, and appends exactly one reconciled decision record.
- The closed v4 research result: 270/270 units retained, 253 validated artifacts, 17 bounded
  failures, no positive market trial, and all three hypotheses rejected without holdout access,
  authentication, order-network use, real orders, promotion, or live-state changes.
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
- Short-lived `paper-recovery-acknowledgement-1` human review bound to the exact clean blocked
  checkpoint, policy, KRW universe, reviewer reference, and revalidated terminal-order/lock/ledger
  facts. Creating it does not clear the block or change any runtime gate.
- Runtime-only one-use acknowledgement consumption with `OPERATOR_ACKNOWLEDGED` status and a
  hash-bound receipt. Expired, tampered, mismatched, changed, or previously consumed approval fails
  closed; model approval, paper-order policy, risk, settings, network, and live paths are unchanged.
- Credential-free dynamic discovery of every current Upbit KRW pair, with strict public catalog and
  quote-ticker schema validation, warning-market exclusion, and market-set-hashed recovery state.
- A tiered all-KRW paper universe: ticker monitoring across the full listing set and rotating dense
  trade/five-level-orderbook processing for 20 liquid, fresh, active short-horizon candidates.
- Atomic `realtime-universe-1` evidence, `paper-runtime-4` scope/focus counters, bounded focus dwell,
  and a compact Korean monitor view showing total coverage, focused markets, exclusions, and
  rotations. All model, paper-order, private, and real-order controls remain closed.
- Incremental exact portfolio aggregates that keep focused risk decisions from rescanning every
  monitored market on each event.
- Configurable host bind storage for bulk paper data, with an optional machine-specific override
  excluded from Git and a portable repository-local fallback.
- Checked ZSTD compaction with version-2 supersession manifests and interruption-resumable retirement
  markers that preserve replay rows while reducing completed-hour small files.
- A 30-day raw retention ceiling, 50GiB active-data cap, 20GiB free-space fail-closed stop, and
  `paper-runtime-5`/Korean-monitor lifecycle evidence for compaction, pruning, reclaimed space, and
  actual filesystem capacity.
- A finite 300-second Compose stop grace period for bounded queue flush, final full-store
  maintenance, and clean paper checkpoint closure, plus a 180-second health-check start period for
  retained-manifest verification.
- A committed short-horizon experiment plan fixing three public-microstructure hypotheses, causal
  availability, entry/exit thresholds, base/stress costs, data minimums, chronological folds,
  multiplicity control, and a sealed final holdout before trial execution.
- A backward-readable dual-cutoff research selection contract that binds both exchange and local
  receive time, preventing later-arriving old events from changing a growing-feed preregistration.
- Explicit duplicate-mark and quality-flag exclusion shared by research inventory and raw-event
  loading, matching the clean-row basis of the 24-hour eligibility evidence without deleting data.
- Bounded-memory external research fingerprinting with exact legacy-hash equivalence, cross-run
  duplicate detection, coarse progress, scratch cleanup, and a fail-closed wall-time budget.
- A new hash-chained `qf-scalp-20260827-v2` preregistration binding 9,157,974 clean fixed-cutoff
  detailed rows, 15 eligible markets, the exact committed source and manifest lineage, and the
  closed 18-trial search space before execution; its ledger contains no trial or holdout access.
- A bounded, resumable scalping trial runner with deterministic three-fold execution plans, exact
  18-trial ordering, Arrow-filtered event/time limits, identical-input neutral baselines, atomic
  artifacts, hash-chain ledger resume, permanent failed/null retention, and no final-holdout role.
- Fail-fast registration validation that blocks v2 before rescanning because its ledger omitted
  required primary/trade/non-fill metrics; v2 remains immutable with zero executed trials.
- A metric-complete `qf-scalp-20260827-v3` replacement registration bound to the committed bounded
  runner, unchanged fixed-cutoff dataset, all thirteen emitted metrics, and a registration-only
  hash chain with no trial or holdout access.
- An immutable v3 execution plan sealing 15 eligible markets, three chronological non-holdout
  windows, all 18 validation/test work-unit UUIDs, and the fixed event/time limits before execution.
- A backward-compatible market-partitioned scalping execution contract that turns the fixed
  15-market scope into 270 one-market checkpoint units, retains exact v3 plan hashes, and keeps
  retries, performance-based market selection, final-holdout access, orders, and promotion absent.
- A registration-only `qf-scalp-20260828-v4` ledger binding all 270 market-partitioned units to the
  exact committed runner, unchanged fixed-cutoff dataset, complete metrics, and sealed holdout
  before any v4 computation.
- An immutable v4 execution plan revalidating all 9,157,974 fixed-cutoff rows and sealing 180
  validation plus 90 test market units, 500,000-event/900-second bounds, and false-only safety state.
- The first v4 market unit retained as reproducible negative validation evidence: H-SCALP-001 base
  fold 1 on KRW-BTC processed 185,798 events in 581.188 seconds, closed 13 candidate trades, and
  produced Decimal net PnL `-195.319631205956800` versus an identical-input neutral baseline of
  zero. Its hash-chained ledger and immutable artifact preserve the result without holdout access,
  champion selection, authentication, orders, promotion, or any automatic next-trial execution.
- The first v3 work-unit ID retained as an infrastructure `FAILED` result after the isolated
  worktree report path was denied; no performance artifact or metric was inferred, the ID will not
  be retried, and final-holdout/order access remained absent.
- The second v3 work-unit ID retained as `FAILED` after its fixed 900-second budget expired during
  bounded raw-event loading; it produced no metric or artifact and leaves the remaining work units
  untouched pending an execution-budget review.
- A checksummed detailed-event inventory plus deterministic long-only research engine that routes
  entries, profit/stop/time exits, latency, partial/non-fills, and all cost attribution through the
  conservative L2 paper broker and exact Decimal ledger.
- Atomic blocked research reports and hash-chained experiment-ledger evidence when the registered
  24-hour/three-market minimum is absent, with zero trials, no favorable-interval search, and no
  final-holdout, authentication, order-network, real-order, model-promotion, or runtime-gate action.
- Fixed-path Secret-free Work audit exports for operations, live data quality, incidents,
  performance, and models, with explicit unavailable/partial/insufficient states instead of
  fabricated healthy values.
- Atomic 15-minute Work audit baselines with 30-day and 100MiB bounds, direct-filesystem discovery
  guidance for ignored runtime JSON, and an empty versioned research paper registry.
- An atomic `raw-data-quality-index-1` that verifies active manifest checksums, Parquet contracts,
  row counts, ordering/anomaly counters, and per-market availability once, then reuses unchanged
  file fingerprints and drops compacted or retired cache entries.
- A non-ordering `index-raw-quality` bootstrap command, `paper-runtime-6`, version-3 Work data-quality
  evidence, and compact Korean monitor totals for verified storage and future preregistration
  availability. None can authorize the current experiment, approve a model, open a paper-order
  gate, or submit an order.
- The actual D-drive bootstrap verified 1,938,743 rows in 222 files in 31.27 seconds. A second pass
  reused those files, scanned five new files in 2.16 seconds, and covered 1,944,965 rows across 286
  markets with no checksum failure or duplicate event identity.
- An atomic D-drive continuity lease and low-volume fsynced SHA-256 session ledger that distinguish
  clean/failed stops, missing-terminal interruptions, locally observed public-WebSocket/stale-data
  gaps, and reconnect changes without claiming exchange-delivery completeness.
- `paper-runtime-continuity-1`, backward-readable `work-ops-2`, strict 6-hour/12-hour continuity
  results, compact Korean monitor rows, and Work audit guidance that no longer treats a sparse
  15-minute baseline alone as proof of an outage.
- `paper-runtime-7`, `work-ops-3`, and `operations-dashboard-2` timing evidence separating session
  maximum positive ingress latency, newest signed ingress latency, and the newest exchange-ahead
  proxy without claiming an independent host NTP measurement.
- Validated 24-hour collection evidence with 14,475,141 retained rows and fifteen independently
  scanned clean markets meeting the preregistered duration/trade/orderbook minimums; the report does
  not authorize an experiment, model, paper order, or live action.
- Actual Compose restart evidence with verified clean terminal transitions and one retained prior
  missing-terminal interruption: an earlier image exited code 1 without a Docker kill event and was
  automatically restarted after 40.046 seconds. The final session has prior `CLEAN_STOP`, healthy
  public observation, and every paper, private, authenticated, and real-order capability closed.
- Post-rollout maintenance evidence that the version-7 runtime compacted 207 source files, reclaimed
  2,929,931 bytes, retained 14,705,609 checksum-verified rows, and drained the bounded queue while
  remaining healthy with zero restart, OOM, parser, reconnect, or overflow events.

### Fixed

- Record paper runtime acceptance immediately after bounded storage-queue admission so a later
  processing failure cannot persist more rows than the terminal snapshot reports as accepted or
  mask the original exception with a snapshot validation error.
- Stabilize public receive availability when the local wall clock moves backwards by advancing from
  the last accepted time with monotonic elapsed time, retaining a `local_clock_regression` quality
  flag, and forcing the affected feature frame to remain `HOLD` instead of restarting the runtime.
- Version the stabilized live receive semantics as `upbit-public-live-v2` and record ADR-026.
- Stop reporting a stale or duplicate ticker's positive ingress-latency high-water mark as host
  clock skew; retain it as staleness evidence and use only the fresh negative-latency magnitude for
  the backward-compatible dashboard clock proxy.
- Require the six-hour scheduled operations prompt to use the complete `automation-report-1`
  fixture shape, validate its same-stem JSON manifest, avoid fixed-drive assumptions, and treat
  denied optional host/Docker access as unknown rather than an incident by itself.
- Prevent planned replacement from being killed during full-store shutdown maintenance by extending
  the bounded Compose stop budget from 60 to 300 seconds. The reproduced version-7 stop completed in
  about 67 seconds with equal accepted/committed counts and a clean recovery checkpoint.
- Prevent a false transient Docker `unhealthy` state while a large retained store is verified at
  startup by extending only the health-check start period from 30 to 180 seconds.

### Security

- Paper mode and all live approvals default to disabled.
- No live exchange adapter or real order endpoint exists.
- Repository-local Secret guard and structured redaction added.
- Updated pytest from the vulnerable 8.4.2 resolution to 9.1.1 after `PYSEC-2026-1845`; the repeated audit reported no known vulnerabilities.
- Pinned container images and CI actions to immutable digests/commits.
- Kept the incompatible official Upbit SDK out of the runtime instead of bypassing its declared
  dependency constraint; authenticated/private capabilities remain disabled.

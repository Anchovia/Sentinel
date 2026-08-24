# QuantForge Progress

## Current checkpoint

- Phase: 11.9 — One-Use Paper Recovery Acknowledgement
- Status: checkpoint `COMPLETE`; Phase 11 `IN_PROGRESS`
- Planned implementation phases: 0–10 complete; Phase 11.1–11.9 checkpoints complete
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; the live adapter has no network capability
- Readiness result: `NOT_READY`
- Actual orders executed: no
- Private/authenticated Upbit calls: no
- Production Secrets accessed: no
- Active recurring scheduled tasks: none; one-time unattended Work filesystem test completed
- Automatic merge/deploy/model promotion/live activation: unavailable

## Completed in Phase 11.9

- Added versioned `paper-recovery-clearance-evidence-1`, `paper-recovery-acknowledgement-1`, and
  `paper-recovery-acknowledgement-receipt-1` contracts. A short-lived human review binds the exact
  blocked checkpoint, policy, ordered KRW universe, pseudonymous reviewer, review reference, and
  reproducible clearance facts; every artifact is Secret-rejected and hash-bound.
- Added read-only `paper-recovery-status` and explicit-confirmation `approve-paper-recovery` CLI
  commands. Approval creation requires a cleanly stopped, still-blocked checkpoint, writes only the
  canonical pending sidecar, and never clears the block, changes runtime/risk/model gates, calls a
  network, or submits an order.
- Made the next paper runtime start independently revalidate terminal and unknown order state,
  reservations, locked Decimal cash, checkpoint/policy/market bindings, and every ledger restore/
  round trip before clearing only the recovery block as `OPERATOR_ACKNOWLEDGED`.
- Added an immutable consumed receipt and prior-receipt check so the approval cannot be reused even
  if an older checkpoint and pending file are restored together. Missing, expired, tampered,
  mismatched, changed, or already consumed approval remains fail-closed.
- Kept interrupted sessions invalid for performance evidence and left model approval, the separate
  paper-order policy gate, risk limits, runtime settings, private connectivity, and live submission
  unchanged. Added ADR-024 and operator/data/architecture documentation; README remains unchanged.
- Verified the current D-drive checkpoint read-only while running: it correctly reported
  `clean_shutdown=false`, `recovery_blocked=false`, and not eligible for acknowledgement. No pending
  approval was created against actual runtime data.
- Rebuilt and recreated the paper service. It returned `healthy`, `RUNNING`, public WebSocket
  connected, `VERIFIED_CLEAN`, paper-order gate false, paper/real orders 0, and parser/reconnect/
  queue-overflow counters 0.

## Completed in Phase 11.8

- Added atomic `raw-data-quality-index-1` beside the public raw store. The first pass verifies every
  active manifest checksum, byte size, Parquet contract, row count, constant source/event/schema
  fields, payload-hash shape, exchange-time bounds, within-file identities, ordering, and market
  availability. Later passes reuse unchanged manifest fingerprints and inspect only new, changed,
  or verification-expired files.
- Added bounded cache retirement for compacted/pruned manifests, a non-ordering
  `index-raw-quality` command, and fail-closed behavior that preserves the last valid index if any
  current file is damaged.
- Added `paper-runtime-6` and version-3 live data-quality exports with verified files/rows/bytes,
  anomaly counters, per-market detailed coverage, and readiness for a *new* preregistration. The
  existing fixed-cutoff experiment remains immutable and unauthorized; model and paper-order gates
  remain closed.
- Kept the Korean monitor compact by showing only storage verification totals and research-data
  accumulation state. No raw payload, credential, account, control, or order action was added.
- Verified actual D-drive storage twice: the initial 222-file, 1,938,743-row, 230,947,947-byte pass
  took 31.27 seconds; the next pass reused all 222 entries and scanned only five newly committed
  files in 2.16 seconds. The resulting 227-file index covered 1,944,965 rows and 286 markets with
  zero duplicate event identities or checksum failures.
- The current future-experiment gate remains not ready: no market yet satisfies all 24-hour,
  20,000-trade, and 20,000-orderbook requirements. This is not a profitability conclusion.
- Recorded the one-time Work unattended local read/write test as an access success. Its stale
  `STOPPED` runtime observation was an operational-input result, not an access failure; scheduled
  timing still depends on the computer and desktop app being available. No recurring task is active.
- Added ADR-023 and left the public README unchanged.

## Completed in Phase 11.7

- Corrected the first Work audit's ignore-aware discovery failure: generated runtime JSON remains
  uncommitted, but Work is instructed to open exact local filesystem paths.
- Added atomic `work-ops-1`, `work-incidents-1`, `work-performance-1`, and `work-models-1` snapshots
  at the fixed paths consumed by the Work prompts. Live data quality now uses a backward-readable
  version-2 contract with explicit source, measurement support, coverage, freshness, and queue data.
- Missing private streams, reconciliation, incidents, database, backup, representative performance,
  and drift evidence is explicit as `NOT_CONFIGURED`, `PARTIAL`, or `INSUFFICIENT_SAMPLE`; it is not
  presented as a healthy zero.
- Added one combined immutable baseline every 15 minutes with 30-day and 100MiB limits. The baseline
  contains only small redacted audit models and cannot read raw D-drive payloads or call a network.
- Added the empty versioned `research/papers.yaml` registry and updated Work prompts for exact-path
  reads and current scheduled-local-file capability verification. No schedule was registered.
- Added ADR-022. Authentication, private/order network, paper-order simulation, model approval,
  real orders, live submission, and the public README remain unchanged.

## Completed in Phase 11.6

- Registered three falsifiable public-microstructure hypotheses before computation: five-second
  trade continuation, snapshot-derived book pressure, and their intersection. Fixed entry, profit,
  stop, time-stop, cooldown, base/stress cost, three-fold, sample, multiplicity, and sealed-holdout
  rules were committed before implementation or trial execution.
- Added a checksummed row-identity inventory for trade/orderbook data at the registered cutoff. It
  reports per-market duration and event counts without decoding payloads or touching a credential,
  private endpoint, order network, or final holdout.
- Added a deterministic long-only research engine that consumes the causal real-time feature
  contract and routes entries/exits through the existing latency-aware conservative L2 paper broker
  and exact Decimal ledger. It attributes fees, spread, slippage, adverse selection, partial/non-
  fills, turnover, drawdown, win rate, holding time, and round-trip PnL.
- Added the always-neutral no-order baseline, fixed profit/stop/time/boundary exits, deterministic
  hashes, strict base/stress plan validation, blocked experiment-ledger retention, atomic Markdown/
  JSON reports, and the offline `assess-scalping-research` command.
- The registered gate requires 24 hours and at least 20,000 trade plus 20,000 orderbook events in
  each of three markets. Short data writes `BLOCKED` with zero trials and no final-holdout access;
  it is never searched for a favorable interval.
- The first fixed-cutoff assessment verified 430,655 detailed events across 123 observed markets.
  No market qualified: the longest was `KRW-BTC` at 4.70 hours with 18,637 trades and 108,102
  orderbooks, still below both the 24-hour and 20,000-trade minimums. The retained result is
  `BLOCKED`, with zero trials, zero holdout accesses, and no profitability claim.
- Added ADR-021. The runtime model approval and independent paper-order gate remain closed, and the
  public README remains unchanged.

## Completed in Phase 11.5

- Moved the local paper-data bind to the owner-provided `D:/Sentinel-Data` through an ignored,
  non-secret Compose override. The committed Compose fallback remains portable and the original
  `quantforge_paper-data` volume remains intact as a rollback copy.
- Added `RawStoragePolicy`: 30-day retention, 50GiB active raw-data cap, 20GiB free-space safety
  floor, 15-minute maintenance, four-file minimum compaction, and 250,000-row compact targets.
- Existing raw files already use ZSTD. Completed creation-hour partitions now receive checked,
  lineage-preserving compaction into version-2 manifests. Supersession is resolved before replay;
  interrupted source retirement resumes from durable tombstones.
- Age and size pruning rename manifests before payload deletion and retain the deletion reason.
  Active manifest totals are rebuilt after every pass. Capacity checks run on every heartbeat and
  after maintenance; crossing the free-space floor fails the collector closed.
- Compose now grants 60 seconds for signal-driven queue flush and clean checkpoint persistence;
  the final restart recovered `VERIFIED_CLEAN` with the new grace period applied.
- Added `paper-runtime-5` storage location, policy, compaction, deletion, reclaimed-space, and actual
  free-space evidence. The compact Korean monitor now shows the D-drive location and storage bounds.
- The clean migration copied exactly 314,560 rows, 781 Parquet files, and 46,643,200 Parquet bytes.
  First startup preserved all rows while compacting 659 source files into 134 active files and
  reclaiming 6,749,864 bytes. Recovery remained `VERIFIED_CLEAN` and the service returned healthy.
- Added ADR-020 and kept the public README unchanged.

## Completed in Phase 11.4

- Replaced the fixed runtime market argument with credential-free startup discovery from Upbit's
  official detailed pair catalog and KRW quote-ticker snapshot. The runtime fails closed on network,
  size, JSON, schema, or empty-universe failure and never falls back to a stale committed list.
- The current official response contained 285 KRW pairs. All 285 receive broad ticker monitoring;
  the six official warning pairs remain observable but cannot enter dense processing.
- Added a two-tier WebSocket request: every KRW pair is watched by ticker while only 20 focused
  pairs receive trade and five-level orderbook streams. This avoids applying full L2 storage and
  inference cost to every illiquid listing.
- Added deterministic 60-second activity/move/liquidity ranking, inactive/suspended/warning/stale/
  low-turnover exclusion, a one-minute minimum focus dwell, and rate-limited dynamic subscription
  replacement. Rotation is disabled if paper-order simulation is ever enabled.
- Replaced per-decision full-universe portfolio recomputation with exact incremental aggregate
  exposure/equity totals. Dense decision cost therefore remains bounded by the focused event instead
  of growing linearly with every monitored listing.
- Added atomic `realtime-universe-1` evidence and `paper-runtime-4` scope/focus/exclusion fields. The
  compact Korean monitor shows total KRW coverage, detailed focus, ticker coverage, warning
  exclusions, rotations, and at most five leading market cards.
- Namespaced paper recovery by the full discovered market-set hash, preventing an accounting
  checkpoint from a different listing universe from being restored. Existing fixed-market recovery
  behavior and evidence remain compatible.
- The final paper process remained keyless and healthy with model approval, paper-order permission,
  authentication, private network, real-order submission, and live submission all false.
- Added ADR-019 and kept the public README unchanged.

## Completed in Phase 11.3

- Added a versioned outer-SHA-256 paper recovery checkpoint bound to exact decision/execution policy,
  market universe, broker orders/fills, reservations, FIFO lots, Decimal balances, complete verified
  ledger chains, counters, latest marks, risk-rate windows, and last event cursor.
- Clean shutdown now cancels every non-terminal paper order, releases its reservation, atomically
  writes a clean checkpoint, and restores it only when its policy, markets, hashes, accounting, fill
  sequences, and ledger tail all reconcile.
- Restart never trusts a stale orderbook. A recovered broker requires a new public L2 snapshot before
  any future execution can be considered.
- An unclean checkpoint cannot resume paper execution: recovered open orders are deterministically
  canceled, cash/position locks are released, the evidence remains persisted, and the independent
  paper-order gate stays blocked across subsequent restarts.
- Container termination signals now request the same clean supervisor shutdown. An unclean state can
  avoid permanent blocking only when simulation is disabled and every order, fill, lock, lot, ledger
  record, cost, turnover, and balance change is provably absent (`EMPTY_UNCLEAN_RECOVERED`).
- Stop requests explicitly close the active public WebSocket, so a stalled receive cannot outlive the
  supervisor cleanup window.
- Consequential order/accounting mutations are synchronously persisted and included in measured
  decision latency. Neutral state is refreshed by the existing heartbeat without per-event disk I/O.
- Added recovery state to the redacted decision snapshot, CLI benchmark, and compact Korean monitor.
  No approval, strategy proposal, simulated order, authenticated call, or real-order capability was
  added to the supervised runtime.
- Verified an actual Docker replacement: the first migration safely classified the disabled empty
  state as `EMPTY_UNCLEAN_RECOVERED`; the next signal-driven restart restored `VERIFIED_CLEAN` with
  recovery unblocked and the paper-order gate still closed.
- Replayed 10,000 retained events after recovery integration: 2,286.57 events/s, feature p99 0.352ms,
  decision p99 0.850ms, combined p99 1.133ms, and combined max 2.602ms. All 3,328 ready frames ran
  inference with zero proposals, risk approvals, orders, fills, or real capabilities.
- Confirmed the final healthy runtime at 895 accepted / 561 newly committed / 70,517 retained rows:
  decision p99 1.079ms, max 1.289ms, 0 budget breaches, queue depth/overflow 0, and recovery
  `VERIFIED_CLEAN` without any paper or real order.

## Completed in Phase 11.2

- Composed ready feature frames into versioned regime/execution inference, an always-neutral alpha,
  proposal-only strategy routing, independent risk, conservative paper execution, and exact Decimal
  accounting. The supervised alpha has no paper approval and always abstains.
- Added a separate human paper-approval contract bound to model version, artifact SHA-256, market
  scope, approval time, and validity. No approval or actionable alpha artifact is present in the
  runtime or repository.
- Added an independent disabled-by-default paper-order simulation gate. A valid model approval alone
  cannot create a simulated order, and the supervised runtime leaves both controls closed.
- Enforced an explicit alpha `TRADE` action in both baseline strategies; alpha `HOLD` or `ABSTAIN`
  cannot create a strategy trade even if individual feature or edge thresholds happen to pass.
- Exercised the complete paper-only path with a human-approved test fixture: one proposal crossed
  independent risk sizing, cash reservation, latency-aware simulated fill, fee/cost attribution,
  release, and verified ledger. The fixture is not market, research, or performance evidence.
- Added read-only portfolio valuation so market marks do not grow the ledger on every event. Rare
  Decimal associativity remainders reconcile to authoritative balances without changing frozen
  Phase 3 replay hashes.
- Added atomic `realtime-paper-decision-1`, the `benchmark-paper-decision` verified replay, and a
  compact monitor panel for model review, proposals, simulated order/fill counts, and paper PnL.
- Replayed 10,000 retained events through the final neutral path: 2,179.38 events/s, feature p99
  0.362ms, downstream decision p99 0.896ms, combined p99 1.185ms, combined max 2.892ms. All 3,328
  ready frames ran inference; proposals, risk approvals, orders, fills, and real capabilities were 0.
- Confirmed the final public runtime remained healthy while 1,439 events were accepted and 1,436 were
  periodically committed: decision p99 1.221ms, 0/1,439 over 5ms, queue depth/overflow 0, `HOLD`, and
  no approved model, paper-order permission, paper order, authentication, private network, or live
  capability.

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
Python: PASS — 3.13.15; no Phase 11.9 dependency added
ruff: PASS — all checks passed
format check: PASS — 167 Python files formatted
mypy: PASS — 116 source files, no issues
pytest: PASS — 373 tests, 85.69% branch coverage
secret scan: PASS — 387 text files checked
dependency audit: PASS — no known vulnerabilities
Compose config: PASS — base + paper overlays
container build: PASS — quantforge-paper-runtime:latest 7f6bafb5c2a1
Work audit exports: PASS — work-ops-1 RUNNING; data quality VERIFIED_STORAGE with 2,000,404
  indexed rows/140 manifests; incidents NOT_CONFIGURED; performance/models INSUFFICIENT_SAMPLE;
  authentication/order capability false
incremental D-drive quality index: PASS — initial 222 files/1,938,743 rows in 31.27 seconds; next
  refresh reused 222 and scanned 5 new files in 2.16 seconds; 286 observed markets; current future-
  preregistration eligible markets 0; current experiment authorization false
Phase 11.9 restart: PASS — paper-runtime-6 RUNNING/healthy; WebSocket connected; VERIFIED_CLEAN;
  parser errors/reconnects/queue overflows 0; model approval/paper/real order capability false
recovery review live check: PASS — running D-drive checkpoint read-only; unblocked/ineligible as
  expected; no pending acknowledgement or receipt created
synthetic registered entry/exit: PASS — deterministic conservative fills, positive net round trip,
  non-zero fees/slippage/adverse selection; neutral baseline orders/fills 0
D-drive fixed-cutoff research inventory: PASS — 430,655 detailed events, 123 observed markets,
  0 eligible; BLOCKED, 0 trials, final holdout unused
post-assessment paper runtime: PASS — RUNNING/healthy; public events fresh; parser errors/reconnects
  0; authentication/order/live capability false
D-drive verified 10,000-event neutral replay: PASS — 2,132.31 events/s; feature p99 0.377ms;
  decision p99 0.812ms; combined p99 1.137ms; max 2.520ms; 3,328 inference frames
D-drive all-KRW runtime: PASS — healthy after 517 seconds; 285/285 ticker coverage, rotating
  20-market focus, 23,993 accepted at 46.41 events/s
live latency snapshot: PASS — feature p99 0.408ms; decision p99 1.459ms; parser errors/reconnects/
  queue overflows 0; HOLD
storage sample: 1.04MB added over 136 seconds; observed throughput projects roughly 20–70GB per
  30 days before bounded compaction/retention, depending on market activity and Parquet batching
D-drive migration: PASS — 314,560 rows preserved; 781 -> 134 active files; 6,749,864 bytes reclaimed;
  30 days / 50GiB / 20GiB floor visible in paper-runtime-5; 563.37GiB free; original named volume
  retained
model approval/paper-order gate/proposals/risk approvals/paper orders/fills/authentication/private/
  real/live capability all false or 0
actual/private/test orders: NONE
scheduled filesystem access: PASS — one-time Work read/write test; recurring schedules NONE
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
- Phase 8 recurring tasks remain unregistered. Manual and one-time scheduled local-file access
  passed, but standard performance/model/incident files intentionally report unavailable or
  insufficient evidence rather than representative results. Execution still depends on the host
  and desktop app being available.
- The Windows host lacks `uv` and `make` on PATH, so exact Make targets were not run in this phase;
  their equivalent locked project-venv commands passed. Container builds use the pinned uv image.
- The public collector, feature path, and neutral paper composition are supervised, but sustained
  coverage has not accumulated and no alpha or exit lifecycle has paper approval. The full-path
  simulated fill is a fixture only; representative performance does not exist.
- Clean paper state restores deterministically. Unclean state is reconciled fail-closed; a local
  one-use human acknowledgement can clear only the recovery block after a clean stop and a second
  runtime verification. This is not production recovery, cryptographic identity, multi-operator
  authorization, or performance validation.
- The Korean monitor now shows neutral decision, proposal, simulated-order/fill, and portfolio
  counters. The authenticated dashboard and Grafana remain developer/operations skeletons.
- Dashboard, local journals, backup proof, public-L2 fill approximation, missing authenticated
  transport, and synthetic research limitations remain documented.
- `D:/Sentinel-Data` is bounded local paper storage, not an encrypted off-host backup. The 50GiB cap
  may shorten the effective 30-day window, and pruned raw payloads require a separate backup to
  recover.

## Next milestone

Do not enable live trading. Keep the bounded D-drive burn-in running and verify maintenance across
hour/day boundaries, actual retention pressure, restart recovery, parser failures, gaps, and disk
growth. Next preregister falsifiable alpha and exit hypotheses, evaluate challengers on cost-
inclusive chronological data, and submit any surviving artifact for separate human paper review.
Exercise the recovery acknowledgement against an actual block only when a real paper incident
creates one; do not manufacture or clear an incident merely to produce evidence.
Only clean recovery, a reviewed artifact, and a separately enabled paper-order gate may turn the
already composed path from neutral to simulated entry/exit lifecycle and representative performance
exports.
Re-run all four Work prompts manually against the fixed-path standard exports. Operations can become
report-only while performance/model/research may remain `BLOCKED` or `INSUFFICIENT_SAMPLE` until
their actual evidence exists; do not weaken those conclusions to enable a schedule.
Extend the monitor into a polished paper-performance GUI only after those contracts produce stable
data. Production storage/backup/TLS/RBAC/network design and any authenticated dry-run work remain
separately reviewed.

# QuantForge Handoff

## Restore context

Read `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, and this
file before continuing. Inspect code and evidence; do not infer completion from prompts alone.

## Current state

- Date: 2026-08-24 KST
- Completed phases: 0–10; Phase 11.1–11.7 checkpoints complete
- Current checkpoint: fixed-path bounded Work audit exports and baselines; manually re-run the Work
  prompts before considering any schedule
- Branch: `main` by explicit owner instruction
- Remote: `origin` -> `https://github.com/Anchovia/Sentinel.git`
- Default mode: paper
- Live readiness: `NOT_READY`
- Live network capability: false
- Actual/private/test orders: none
- Production Secrets: not requested or accessed
- Scheduled tasks registered: none
- Phase 0: `cfc1617 feat: QuantForge 안전 기반 구축`
- Phase 1: `136295c feat: 업비트 공개 데이터 파이프라인 구축`
- Phase 2: `41b64d1 feat: 결정적 재생과 인과 특징 구축`
- Phase 3: `0f7e3a1 feat: 보수적 모의 체결과 백테스트 구축`
- Phase 4: `b1a6b03 feat: 재현 가능한 기준 모델 연구 구축`
- README cleanup: `74a2bee chore: 공개 README 간소화`
- Phase 5: `91962b9 feat: 전략 라우팅과 위험 게이트 구축`
- Phase 6: `ac7798b feat: 모의 비공개 주문 안전 경계 구축`
- Phase 7: `b71424e feat: 운영 대시보드와 감사 경계 구축`
- Phase 8: `84b751c feat: 격리된 자동 감사 기반 구축`
- Phase 9: `a2c0542 feat: 읽기 전용 실거래 준비도 검증 구축`
- Phase 10: `34ac186 feat: 공개 페이퍼 감독 런타임 구축`
- Phase 11.1: `eb8a4da feat: 저지연 실시간 처리 기반 구축`
- Phase 11.2: `af50599 feat: 중립 실시간 모의 판단 경로 구축`
- Phase 11.3: `f067442 feat: 모의 거래 재시작 복구 구축`
- Phase 11.6 preregistration: `4cb419c chore: 단타 전략 실험 사전등록`
- Phase 11.6 implementation: `0e3040b feat: 단타 전략 연구 기반 구축`

## Implemented through Phase 11.7

- Safety-first Python modular monolith, six closed live gates, Decimal domain/accounting boundary,
  keyless Upbit public transport, versioned immutable raw lineage, deterministic replay/bars/features,
  conservative L2 paper execution, exact ledger, cost-aware backtesting, chronological preregistered
  research, calibrated baselines, uncertainty/abstention, and immutable model registry.
- Proposal-only strategies, independent risk gateway, attribution, manual-release kill switch,
  mock-only private contracts, deterministic burned identifiers, fsynced order journal, identifier-
  first uncertain-order recovery, exact reconciliation, and a disabled live adapter with no network.
- Secret-rejecting operations exports, authenticated read dashboard, Prometheus/Grafana, hash-chain
  incident/audit/control records, local cancel-only and incident acknowledgement, and a checksummed
  paper restore drill. These are not production operations/recovery claims.
- Nine repository-local Work/Codex skills, ten standalone prompts, closed automation report/trigger
  schemas, deny-first write paths, actual background-worktree verification, and an unregistered
  Asia/Seoul catalog. Work stays report-only; Codex stays draft-candidate-only.
- Read-only live readiness with 13 gates, two-tier conservative thresholds, input/policy hashes,
  staleness/contradiction checks, distinct approvals, Decimal canary limits, and atomic output. The
  highest status is manual review only; all mutation/order/network/Secret flags are false-only.
- Supervised keyless public burn-in with credential/production/partial-live-gate startup refusal,
  atomic lifecycle heartbeats, periodic immutable raw flushes, public market operations views,
  reconnect/parser/duplicate/latency evidence, offline health status, and clean bounded shutdown.
- A separate read-only Compose service stores paper raw data in a persistent volume and writes only
  redacted runtime exports. It has no authenticated/private/real-order path; its composed paper
  decision path remains neutral and independently gated.
- A self-contained Korean local monitor refreshes from atomic exports every five seconds and shows
  public market/collector health plus manifest-backed retained rows, files, and bytes. It needs no
  server, token, account, or control path and excludes raw payloads and internal identifiers.
- A causal incremental real-time feature path calculates book/trade/ticker state and rolling
  microstructure features while measuring validation/feature latency. Raw persistence runs in a
  bounded asynchronous queue and any overflow fails the supervisor instead of dropping data.
- Three short-horizon hypotheses, fixed entry/profit/stop/time/cooldown rules, base/stress execution
  costs, data minimums, folds, metrics, and a sealed holdout were committed before execution. The
  offline engine routes causal signals through the conservative paper broker and Decimal ledger.
- A row-identity inventory and `assess-scalping-research` command retain insufficient data as a
  blocked Markdown/JSON/experiment-ledger bundle with zero trials. The registered minimum is 24
  hours and 20,000 trade plus 20,000 orderbook events in each of three markets.
- The first committed-cutoff result verified 430,655 detailed events across 123 markets but found
  zero eligible markets. `KRW-BTC` was longest at 4.70 hours with 18,637 trades and 108,102
  orderbooks. The result is `BLOCKED`; no trial or final-holdout access occurred.
- Fresh Work inputs now exist at fixed `ops`, `data_quality`, `incidents`, `performance`, and
  `models` paths. They are atomic, Secret-rejected, ignored by Git, and opened by direct filesystem
  path so ignore-aware discovery cannot repeat the first false absence result.
- Fifteen-minute combined audit baselines retain at most 30 days and 100MiB. Unsupported private,
  incident, performance, and drift evidence remains explicitly unavailable or insufficient rather
  than being converted into a healthy result. The versioned paper registry is present but empty.
- The decision remains `HOLD` with no approved real-time model, strategy order, private network,
  account, or live capability.
- An always-neutral alpha now exercises regime/execution inputs and the proposal/risk/paper/ledger
  composition on each ready frame. A separate time-bounded human approval must exactly match model
  version, artifact hash, and market before any actionable paper alpha can reach risk. A second,
  disabled-by-default paper-order gate must also be explicitly enabled before simulation.
- Both baseline strategies require an explicit alpha `TRADE`; `HOLD` and `ABSTAIN` are hard proposal
  blocks regardless of other feature or edge values.
- A test-only approved fixture proves the complete simulated order/fill/accounting plumbing. It is
  not shipped or promoted. Atomic decision exports and the Korean monitor show review status,
  proposals, paper orders/fills, PnL, and latency. ADR-001 through ADR-022 record consequential
  choices. README remains intentionally minimal.
- `realtime-paper-recovery-1` now preserves policy-bound orders, fills, reservations, FIFO lots,
  exact balances, ledger chains, counters, and the event cursor in the durable paper volume. Clean
  state restores automatically without a stale book. Unclean state cancels open paper orders,
  releases locks, persists the evidence, and blocks future simulation pending separate review.
- Container signals now use the clean shutdown path. A disabled and provably empty economic state may
  report `EMPTY_UNCLEAN_RECOVERED`; any order, fill, lock, lot, ledger record, cost, turnover, or
  balance change preserves the unclean block.
- The paper runtime now discovers every current KRW pair from Upbit's credential-free official
  catalog at startup. All pairs receive ticker monitoring while a deterministic, fresh, liquid,
  warning-free 20-market focus receives trade and five-level orderbook streams.
- Focus ranking uses the latest 60-second activity and short move with 24-hour turnover, enforces a
  one-minute dwell, and replaces the validated subscription through the existing limiter. The
  complete focus evidence is exported as `realtime-universe-1` and the Korean monitor stays compact.
- Exact incremental portfolio aggregates keep focused risk decisions from rescanning all monitored
  ledgers on every event; live decision p99 remained below the 5ms budget during validation.
- Full-list recovery checkpoints are namespaced by the discovered market-set hash. BTC/USDT quote
  markets remain outside the KRW accounting and risk contracts. README remains intentionally
  minimal.
- The local paper-data mount is now supplied by ignored `compose.paper.local.env`; this host uses
  `D:/Sentinel-Data`, while committed configuration remains portable. The prior
  `quantforge_paper-data` named volume is intentionally preserved as a migration rollback copy.
- ZSTD raw files from completed creation hours are compacted through checksummed version-2
  supersession manifests. Age/capacity retirement uses durable reason markers and resumes safely
  after interruption. Active totals are always rebuilt from verified manifests.
- `paper-runtime-5` enforces and reports 30-day retention, 50GiB maximum active raw data, a 20GiB
  free-space fail-closed stop, 15-minute maintenance, compacted/deleted files, reclaimed bytes, and
  actual filesystem free space. ADR-001 through ADR-022 record consequential choices.
- Compose grants the paper runtime a 60-second stop grace period. The final signal stop persisted a
  clean checkpoint and the next run reported `VERIFIED_CLEAN` before resuming full coverage.

## Latest validation

```text
Python 3.13.15; no Phase 11.7 dependency added
ruff + format: PASS (227 Python files)
mypy: PASS (114 source files)
pytest: PASS (363 tests, 85.94% branch coverage)
Secret scan: PASS (344 text files)
pip-audit: PASS (no known vulnerabilities)
Compose config: PASS
Phase 11.7 image: PASS (quantforge-paper-runtime:latest, a087495dc683)
Work audit exports: work-ops-1 RUNNING; data quality PARTIAL; incidents NOT_CONFIGURED;
performance/models INSUFFICIENT_SAMPLE; baseline created; authentication/order capability false
Synthetic registered entry/exit: deterministic conservative fills, positive net round trip,
non-zero fees/slippage/adverse selection; neutral baseline orders/fills zero
D-drive fixed-cutoff inventory: 430,655 detailed events across 123 markets; 0 eligible; BLOCKED,
0 trials, final holdout unused
Post-assessment runtime: healthy RUNNING, public events fresh, parser errors/reconnects zero,
authentication/order/live capability false
D-drive verified 10,000-event neutral replay: 2,132.31 events/s; feature p99 0.377ms;
decision p99 0.812ms; combined p99 1.137ms; max 2.520ms; 3,328 inference frames
D-drive All-KRW runtime: healthy after 517 seconds; 285/285 ticker coverage, rotating 20-market
dense focus; 23,993 accepted at 46.41 events/s
Live snapshot: feature p99 0.408ms; decision p99 1.459ms; parser errors/reconnects/queue
overflows zero
Observed storage sample: 1.04MB/136 seconds, projecting roughly 20–70GB per 30 days before
bounded compaction/retention depending on activity and batching
D-drive migration: exact 314,560 rows and 46,643,200 Parquet bytes copied; 781 active files reduced
to 134 with all rows preserved and 6,749,864 bytes reclaimed; 563.37GiB free; recovery
VERIFIED_CLEAN; healthy
Model approval, paper-order gate, proposals, risk approvals, paper orders/fills,
authentication/private/real/live capability all false or zero
Actual/private/test orders: none
Scheduled tasks: not registered
```

## Important constraints

- `NOT_READY` is intentional and truthful. There is no sustained paper/production-quality evidence,
  authenticated order-test, live adapter/network review, production recovery, operator drills, or
  release/risk/model/operator approval bundle.
- Complete/conditional readiness fixtures are synthetic classifier tests, not market or approval
  evidence. Numeric thresholds do not guarantee profitability, safety, capacity, or recovery.
- The validator reads a prepared bundle; it does not query production systems. Evidence production
  must remain Secret-free, reproducible, and independently reviewed.
- Work/Codex schedules are not active. Standard files are populated, but representative strategy
  performance, incident-store integration, and model drift are still unavailable. Repeat the manual
  trials and prove unattended local-file access before registering any task.
- No authenticated exchange client, credential provider, cancellation/order endpoint, order-capable
  live adapter, production database/recovery, or canary activation path exists.
- Public L2 fill/queue behavior is approximate. The collector and neutral composition are supervised,
  but sustained coverage is not evidence. No alpha/exit artifact is approved; the only simulated
  fill is a fixture with no profitability or promotion claim.
- Clean paper state restores deterministically, but there is no operator workflow to acknowledge and
  clear an unclean recovery block. Interrupted sessions remain invalid for performance evidence, and
  long-history checkpoint growth has not been load-tested.
- The Korean monitor covers public feed/storage and neutral paper counters. The authenticated
  server-rendered dashboard/Grafana views remain internal operations skeletons, and there are no
  representative paper strategy, round-trip, or performance results yet.
- Dashboard/recovery/authorization/network/storage hardening remains incomplete. Consult
  `docs/KNOWN_LIMITATIONS.md` and `docs/readiness/LIVE_READINESS.md`.
- D-drive retention is single-host local storage, not an encrypted backup. High activity can reach
  the 50GiB cap before 30 days, and pruned payloads need independent backup to recover.
- The Windows host lacks `uv` and `make` on PATH; exact Make targets were unavailable. Equivalent
  isolated-venv checks and the pinned-uv container build passed.
- The owner requires concise Korean Conventional Commits, committed and pushed on `main`, and a
  minimal public README.

## Next actions

1. Keep paper mode. Observe bounded D-drive maintenance across hour/day boundaries and under real
   disk growth; verify compaction, retention pressure, restarts, coverage, gaps, parser failures, and
   reconnects without treating uptime as readiness.
2. Preregister falsifiable alpha and exit hypotheses, run cost-inclusive chronological challengers,
   preserve negative results, and present any candidate artifact for separate human paper review.
3. Add a reviewed operator acknowledgement workflow for unclean paper recovery. Only after clean
   recovery, model approval, and separate gate approval, exercise complete simulated entry/exit
   lifecycles and produce representative exports before expanding the GUI further.
4. Design production PostgreSQL persistence, encrypted off-host backup/restore with measured RPO/RTO,
   TLS/RBAC/rate limits, Secret delivery, network isolation, and monitoring retention.
5. Under separate human authorization only, implement and review credential/order-test transport,
   identifier reconciliation, withdrawal-disabled/IP-allowlisted key policy, and multi-operator
   incident/cancel/recovery drills. Do not send a real order.
6. Re-run all four Work prompts manually against exact local paths. Register only individually
   passing tasks and only if the current scheduled surface proves unattended local-file access.
   Continue report-only/dedicated-worktree boundaries and never auto-merge/deploy/promote/change
   risk/live state.
7. Assemble reviewed evidence and re-run `validate-live-readiness`. A manual canary remains a future
   separately approved project even if the output reaches manual-review eligibility.

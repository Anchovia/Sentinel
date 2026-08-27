# QuantForge Handoff

## Restore context

Read `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, and this
file before continuing. Inspect code and evidence; do not infer completion from prompts alone.

## Current state

- Date: 2026-08-27 KST
- Completed phases: 0–10; Phase 11.1–11.10 checkpoints complete
- Current checkpoint: durable continuity plus storage-acceptance, local-clock, and audit-evidence
  stabilization
- Branch: `main` by explicit owner instruction
- Remote: `origin` -> `https://github.com/Anchovia/Sentinel.git`
- Default mode: paper
- Live readiness: `NOT_READY`
- Live network capability: false
- Actual/private/test orders: none
- Production Secrets: not requested or accessed
- Active scheduled tasks: recurring six-hour local report-only audit on `gpt-5.6-luna` and one-time
  24-hour data verification on `gpt-5.6-terra`; both create separate local Codex tasks
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

## 24-hour evidence and version-7 rollout

- The validated report-only evidence is
  `reports/work/model-health/2026/08/27/20260827T083445Z-model-health.{md,json}`. Its exact session
  exceeded 30 hours, retained 14,475,141 indexed rows, and had no locally observed WebSocket/stale
  gaps, reconnects, parser errors, or queue overflows. An independent clean detailed-row scan found
  fifteen markets above the registered 24-hour/20,000-trade/20,000-orderbook minimum.
- The first planned stop exhausted the original 60-second Compose budget and exited 137 before the
  terminal lifecycle records, although the durable store verified all 14,518,628 rows in 362 files
  with zero checksum failures. The next continuity record correctly calls that prior session
  `UNEXPECTED_INTERRUPTION`; do not relabel or remove that incident evidence.
- ADR-020, Compose, the runbook, and repository safety tests now use a bounded 300-second stop grace
  period and 180-second health-check start period. The reproduced version-7 stop took about 67
  seconds and completed with Docker exit 0, equal 29,249 accepted/committed rows, queue depth zero,
  a clean checkpoint, and 377/377 verified files.
- The final container uses image `a50531c4b6e1`, exports `paper-runtime-7` and `work-ops-3`, and is
  healthy on the unchanged `C:/Sentinel/data/paper` mount. It reports prior `CLEAN_STOP`, recovery
  `VERIFIED_CLEAN`, fresh public events, 14,547,877 retained rows, and no authentication, private
  network, paper-order, unknown-order, or live-order capability.
- The post-rollout monitor crossed one 15-minute maintenance cycle. Compaction superseded 207 source
  files, reclaimed 2,929,931 bytes, preserved 14,705,609 rows in 251 verified files, and drained the
  queue while collection continued. Docker finished healthy with restart/OOM/parser/reconnect/
  overflow counts zero.

## Short-horizon research preregistration preparation

- Keep the existing `H-SCALP-001` through `H-SCALP-003` hypotheses and the immutable blocked `v1`
  result. Do not duplicate the hypotheses or mutate the old D-drive/cutoff evidence.
- New growing-feed plans can fix `maximum_received_at_utc` in addition to the exchange timestamp.
  The inventory filters both bounds before duplicate checks, so rows received after registration
  cannot enter through an older exchange timestamp.
- The scanner also returns the exact active manifest-set hash captured at scan start. Require it to
  equal the new plan's lineage at preregistration; later compaction may change file layout but not a
  correctly preserved selected row hash.
- The new plan must set both clean-row filters: exclude `is_duplicate=true` and every nonempty
  `quality_flags` row. Inventory and event loading share these parameters; raw evidence remains
  retained and unchanged.
- The extension remains backward-readable for the historical plan, but every new plan must carry
  both UTC cutoffs. ADR-028 records this rule.
- No trial or final holdout has been run. Next bind the eligible 24-hour retained rows to the exact
  committed source revision and write one open `v2` preregistration record before any computation.

## Six-hour operations-audit stabilization

- The first unattended report correctly observed a healthy public paper runtime and strict six-hour
  continuity, but misclassified the session's maximum positive ingress latency as Windows clock
  skew. The exact 5,661,490.659ms row was a stale duplicate `KRW-USDG` ticker, not an NTP reading.
- Independent host evidence showed W32Time running automatically, a `time.windows.com` source and
  roughly 0.13s sampled offset. Docker was `running`/`healthy`, restart count 0, OOM false, and the
  inspected error-log filter was empty.
- `paper-runtime-7`, `work-ops-3`, and `operations-dashboard-2` now publish the positive session
  latency high-water mark, newest signed latency, and newest exchange-ahead proxy separately. The
  legacy dashboard clock field uses only the fresh exchange-ahead proxy.
- The report's JSON sidecar failed the repository `automation-report-1` validator with 24 errors.
  The scheduled prompt and operations-audit skill now require the exact fixture shape, structured
  evidence, false-only safety fields, and a successful validator run before completion.
- Audit guidance no longer guesses `D:/Sentinel-Data`. The current container actually mounts
  `C:/Sentinel/data/paper`; host-only checks remain optional/unknown when a scheduled sandbox cannot
  access them, while fresh verified runtime exports remain usable for their supported claims.
- ADR-027 records the decision. Targeted supervisor and automation validation passes 39 tests. Full
  validation passes 385 tests at 85.70% branch coverage, Ruff/format across 238 files, mypy across
  117 source files, 499-file Secret scanning, dependency audit, manifest boundary, and Compose
  config. The 24-hour evidence and version-7 runtime replacement are now complete.
- The 24-hour checkpoint was preserved before replacement. The active audit prompts can now consume
  the version-3 operations export; current 6-hour/12-hour continuity readiness is intentionally false
  because the final version-7 session started a new strict horizon.

## Stabilization after Phase 11.10

- Docker restart evidence exposed a terminal snapshot validation error: raw storage could commit an
  event that its session had not yet counted as accepted when later causal processing failed. The
  validation error then replaced the original processing exception during shutdown.
- `PaperRuntimeSupervisor` now defines successful bounded storage-queue admission as acceptance and
  records event counts, duplicate state, timestamps, and ingress latency before downstream causal
  work. Queue overflow remains fail-closed and uncounted.
- A regression test forces the exact post-admission failure boundary and verifies the original error,
  a valid `FAILED` snapshot, equal accepted/committed rows, and no order capability. This restores an
  existing invariant; it does not change a data, risk, order, approval, or live-trading contract, so
  no new ADR was required.
- The paper image was rebuilt and recreated without replacing durable data. The old session stopped
  cleanly at 50,449 accepted/committed rows and the new session started `RUNNING`, healthy, connected
  to the public WebSocket, and at zero Docker restarts with every authentication/order gate closed.
- A 15-minute per-minute monitor crossed the configured storage-maintenance interval with zero
  restarts, OOM kills, parser errors, or reconnects. Maintenance compacted active files and reclaimed
  2,332,645 bytes; the final read reported 86,322 accepted, 84,475 committed, 1,093,099 retained rows,
  and no authentication, paper-order, or live-submission capability.
- Continued runtime evidence then exposed the preserved downstream cause: the prior image restarted
  three times because `received_at_utc` moved backwards inside an otherwise sequential public event
  callback. The container was not OOM-killed and transport reconnect accounting remained zero.
- `UpbitPublicWebSocketClient` now pairs every wall-clock sample with the process monotonic clock. If
  the wall clock regresses, availability advances by monotonic elapsed time, the stored envelope is
  marked `local_clock_regression`, and the real-time frame remains
  `LOCAL_CLOCK_REGRESSION`/`HOLD`. A true monotonic-clock regression remains fatal.
- The exact 50ms regression is covered through the public client and causal pipeline: collection
  continues at a deterministic adjusted time, the anomaly remains queryable, and no inference-ready
  frame is emitted. New live envelopes use `upbit-public-live-v2`; raw exchange payloads, risk,
  approval, and order contracts did not change. ADR-026 records the availability-time decision.
- The initial fix image replaced the three-restart container after a clean 76,025-row terminal
  flush. Final versioned image `3f6728165257` then cleanly replaced that intermediate session.
  Durable data remained mounted; the final image started healthy with every authentication,
  paper-order, and live-submission capability closed.
- A read-only check of the newest committed Parquet file found 860/860 rows carrying
  `normalization_version=upbit-public-live-v2`.
- The final image passed a 15-minute per-minute monitor with Docker restarts, OOM kills, parser
  errors, reconnects, and exceptions all zero. The final read reported 127,660 accepted, 123,307
  committed, and 2,286,110 retained rows. Maintenance elapsed with no currently eligible compaction;
  reclaimed bytes remained zero and collection continued.

## Implemented through Phase 11.10

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
- `raw-data-quality-index-1` verifies active checksums and Parquet contracts, caches immutable
  manifest evidence, drops retired entries, aggregates market availability, and fails closed while
  preserving the prior valid index. The runtime and Work export now distinguish verified storage
  from unsupported public-exchange gap completeness.
- The research-availability gate reports only whether enough current data exists to preregister a
  new experiment. It cannot alter the registered fixed cutoff, run a trial, approve a model, or
  enable paper orders. The current result remains insufficient.
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
  proposals, paper orders/fills, PnL, and latency. ADR-001 through ADR-027 record consequential
  choices. README remains intentionally minimal.
- `realtime-paper-recovery-1` now preserves policy-bound orders, fills, reservations, FIFO lots,
  exact balances, ledger chains, counters, and the event cursor in the durable paper volume. Clean
  state restores automatically without a stale book. Unclean state cancels open paper orders,
  releases locks, persists the evidence, and blocks future simulation pending separate review.
- Container signals now use the clean shutdown path. A disabled and provably empty economic state may
  report `EMPTY_UNCLEAN_RECOVERED`; any order, fill, lock, lot, ledger record, cost, turnover, or
  balance change preserves the unclean block.
- A cleanly stopped, still-blocked checkpoint can now receive one short-lived
  `paper-recovery-acknowledgement-1` after explicit human confirmation. It binds the exact
  checkpoint/policy/market hashes, pseudonymous reviewer, review reference, and terminal-order,
  reservation, locked-cash, and ledger verification facts without editing the checkpoint.
- The runtime alone revalidates and consumes that approval at the next start, clears only the
  recovery block as `OPERATOR_ACKNOWLEDGED`, and writes a hash-bound receipt. Reuse, expiry, tamper,
  mismatch, changed facts, unknown/open orders, locks, or ledger failure remains fail-closed.
- The workflow does not approve a model, enable the independent paper-order policy, change risk or
  settings, validate interrupted performance, access an exchange network, or add live capability.
- `paper-runtime-continuity-1` now derives strict process/session evidence from an atomic mounted-data
  heartbeat lease and a low-volume fsynced SHA-256 event chain. The next start distinguishes clean,
  failed, and missing-terminal restarts; locally observed socket/stale gaps and reconnect changes are
  separate from sparse 15-minute Work baselines.
- `work-ops-2` and the compact Korean monitor expose uptime, prior outcome, observed gaps, and strict
  6-hour/12-hour results. They always refuse an exchange-completeness claim, do not reconstruct
  history before the first recorded session, and have no model/order/private/live capability.
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
- Phase 11.5 used an ignored `compose.paper.local.env` override for `D:/Sentinel-Data`; the current
  container instead uses the committed repository-local fallback at `C:/Sentinel/data/paper`.
  Historical D-drive and preserved `quantforge_paper-data` volume evidence is rollback context, not
  proof of the current mount or an off-host backup.
- ZSTD raw files from completed creation hours are compacted through checksummed version-2
  supersession manifests. Age/capacity retirement uses durable reason markers and resumes safely
  after interruption. Active totals are always rebuilt from verified manifests.
- `paper-runtime-5` enforces and reports 30-day retention, 50GiB maximum active raw data, a 20GiB
  free-space fail-closed stop, 15-minute maintenance, compacted/deleted files, reclaimed bytes, and
  actual filesystem free space. ADR-001 through ADR-027 record consequential choices.
- Compose grants the paper runtime a 300-second stop grace period and a 180-second health-check start
  period. The reproduced signal stop persisted a clean checkpoint and the final run reported
  `VERIFIED_CLEAN` before resuming full coverage.

## Latest validation

```text
Python 3.13.15; no dependency added by the operations audit stabilization
ruff + format: PASS (238 files)
mypy: PASS (117 source files)
pytest: PASS (385 tests, 85.70% branch coverage)
Secret scan: PASS (499 text files)
pip-audit: PASS (no known vulnerabilities)
Automation report fixture: PASS (schema and write boundary)
Compose config: PASS (base + paper overlays)
24-hour report: PASS_WITH_LIMITATIONS; 14,475,141 indexed rows, 15 clean minimum-qualified markets
Version-7 rollout: PASS; image a50531c4b6e1, paper-runtime-7/work-ops-3, healthy, prior CLEAN_STOP,
VERIFIED_CLEAN, 14,547,877 retained rows, no authentication/private/paper/live order capability
Shutdown bound: PASS; about 67 seconds, Docker exit 0, accepted=committed=29,249, queue depth zero,
clean checkpoint, 377/377 verified files; Compose stop/start health budgets 300s/180s
Version-7 maintenance: PASS; 207 source files compacted, 2,929,931 bytes reclaimed, 14,705,609 rows
in 251 verified files, queue drained, Docker healthy with restart/OOM/parser/reconnect/overflow zero
Runtime acceptance regression: PASS; original downstream exception preserved, accepted=committed=1
Wall-clock regression: PASS; monotonic continuation, quality flag retained, affected frame HOLD
Clock-stabilized image: PASS (quantforge-paper-runtime:latest, 3f6728165257)
Clock-stabilized monitor: PASS (15 minutes); RUNNING/healthy, restart/OOM/parser/reconnect/error zero
Stabilized image: PASS (quantforge-paper-runtime:latest, 9e3c59fe3665); 15-minute maintenance-cycle
monitor PASS, Docker restarts/OOM/parser errors/reconnects zero, final state RUNNING/healthy
Compose config: PASS
Phase 11.10 image: PASS (quantforge-paper-runtime:latest, 601f99523d68)
Continuity restart: PASS_WITH_RETAINED_INCIDENT; VERIFIED/ACTIVE, prior CLEAN_STOP, 4 sessions/
2 clean stops, 0 failed stops, 1 earlier missing-terminal interruption with 40.046s downtime,
observed WebSocket gaps/stale gaps/reconnects zero; exchange completeness false; final image stayed
healthy beyond the earlier 322-second failure point
Work audit exports: work-ops-2 RUNNING; data quality VERIFIED_STORAGE with 2,000,404 indexed
rows/140 manifests; incidents NOT_CONFIGURED; performance/models INSUFFICIENT_SAMPLE;
authentication/order capability false
Incremental D-drive index: initial 222 files/1,938,743 rows in 31.27 seconds; next refresh reused
222 and scanned 5 new files in 2.16 seconds; 286 markets observed; 0 currently eligible
Phase 11.9 restart: paper-runtime-6 healthy RUNNING, public WebSocket connected, recovery
VERIFIED_CLEAN, parser errors/reconnects zero, model/paper/real-order gates closed
Actual recovery review status: current D-drive checkpoint running and unblocked; read-only CLI
correctly returned ineligible, and no real pending acknowledgement or receipt was created
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
Scheduled filesystem access: recurring six-hour local audit and one-time 24-hour verification active;
first invalid six-hour JSON retained; two later unattended manifests validated successfully
```

## Important constraints

- `NOT_READY` is intentional and truthful. There is no representative strategy paper performance,
  authenticated order-test, live adapter/network review, production recovery, operator drills, or
  release/risk/model/operator approval bundle.
- Complete/conditional readiness fixtures are synthetic classifier tests, not market or approval
  evidence. Numeric thresholds do not guarantee profitability, safety, capacity, or recovery.
- The validator reads a prepared bundle; it does not query production systems. Evidence production
  must remain Secret-free, reproducible, and independently reviewed.
- The portable schedule catalog remains unregistered, while two explicitly owner-approved local
  Codex tasks are active. The first six-hour report's invalid manifest is retained as failed audit
  evidence; the corrected prompt has since produced two validator-clean unattended reports.
  Representative strategy performance, incident-store integration, and model drift remain
  unavailable. Scheduled execution depends on the computer and desktop app.
- No authenticated exchange client, credential provider, cancellation/order endpoint, order-capable
  live adapter, production database/recovery, or canary activation path exists.
- Public L2 fill/queue behavior is approximate. The collector and neutral composition are supervised,
  but sustained coverage is not evidence. No alpha/exit artifact is approved; the only simulated
  fill is a fixture with no profitability or promotion claim.
- Clean paper state restores deterministically. The new local acknowledgement is one-use and
  runtime-revalidated, but it is not cryptographic operator identity, multi-operator authorization,
  production recovery, or permission to use an interrupted session as performance evidence.
  Long-history checkpoint growth has not been load-tested.
- Phase 11.10 retained one real missing-terminal interruption from an earlier image: Docker recorded
  exit code 1 after 322 seconds with no kill event, then restarted it after 40.046 seconds. The
  replaced container's exception output is unavailable, so root cause is not claimed. Preserve logs
  and invoke evidence-backed incident triage if the final image repeats it.
- The Korean monitor covers public feed/storage and neutral paper counters. The authenticated
  server-rendered dashboard/Grafana views remain internal operations skeletons, and there are no
  representative paper strategy, round-trip, or performance results yet.
- Dashboard/recovery/authorization/network/storage hardening remains incomplete. Consult
  `docs/KNOWN_LIMITATIONS.md` and `docs/readiness/LIVE_READINESS.md`.
- The current `C:/Sentinel/data/paper` fallback is single-host local storage, not an encrypted
  backup. High activity can reach the 50GiB cap before 30 days, and pruned payloads need independent
  backup to recover. Historical D-drive results do not identify the current mount.
- The Windows host lacks `uv` and `make` on PATH; exact Make targets were unavailable. Equivalent
  isolated-venv checks and the pinned-uv container build passed.
- The owner requires concise Korean Conventional Commits, committed and pushed on `main`, and a
  minimal public README.

## Next actions

1. Keep paper mode. Observe bounded mounted-data maintenance across hour/day boundaries and under real
   disk growth; verify compaction, retention pressure, restarts, coverage, gaps, parser failures, and
   reconnects without treating uptime as readiness.
2. Preregister falsifiable alpha and exit hypotheses, run cost-inclusive chronological challengers,
   preserve negative results, and present any candidate artifact for separate human paper review.
3. Exercise the reviewed acknowledgement only if an actual paper incident creates a persistent
   recovery block; preserve the interrupted evidence and never manufacture an incident to force a
   successful receipt. Model approval and the paper-order gate remain separate.
4. Design production PostgreSQL persistence, encrypted off-host backup/restore with measured RPO/RTO,
   TLS/RBAC/rate limits, Secret delivery, network isolation, and monitoring retention.
5. Under separate human authorization only, implement and review credential/order-test transport,
   identifier reconciliation, withdrawal-disabled/IP-allowlisted key policy, and multi-operator
   incident/cancel/recovery drills. Do not send a real order.
6. Re-run the four Work prompts against the new version-3 quality export. Register a recurring task
   only after its own report is acceptable; keep report-only/dedicated-worktree boundaries and never
   auto-merge/deploy/promote/change risk/live state.
7. Assemble reviewed evidence and re-run `validate-live-readiness`. A manual canary remains a future
   separately approved project even if the output reaches manual-review eligibility.

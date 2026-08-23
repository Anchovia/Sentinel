# QuantForge Handoff

## Restore context

Read `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, and this
file before continuing. Inspect code and evidence; do not infer completion from prompts alone.

## Current state

- Date: 2026-08-24 KST
- Completed phases: 0–10; Phase 11.1–11.3 checkpoints complete
- Current checkpoint: neutral real-time inference/strategy/risk/paper-broker/ledger composition;
  preregistered alpha and exit research plus separate paper approval next
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

## Implemented through Phase 11.3

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
  redacted runtime exports. It has no private, model, strategy, risk, broker, ledger, or order path.
- A self-contained Korean local monitor refreshes from atomic exports every five seconds and shows
  public market/collector health plus manifest-backed retained rows, files, and bytes. It needs no
  server, token, account, or control path and excludes raw payloads and internal identifiers.
- A causal incremental real-time feature path calculates book/trade/ticker state and rolling
  microstructure features while measuring validation/feature latency. Raw persistence runs in a
  bounded asynchronous queue and any overflow fails the supervisor instead of dropping data.
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
  proposals, paper orders/fills, PnL, and latency. ADR-001 through ADR-018 record consequential
  choices. README remains intentionally minimal.
- `realtime-paper-recovery-1` now preserves policy-bound orders, fills, reservations, FIFO lots,
  exact balances, ledger chains, counters, and the event cursor in the durable paper volume. Clean
  state restores automatically without a stale book. Unclean state cancels open paper orders,
  releases locks, persists the evidence, and blocks future simulation pending separate review.
- Container signals now use the clean shutdown path. A disabled and provably empty economic state may
  report `EMPTY_UNCLEAN_RECOVERED`; any order, fill, lock, lot, ledger record, cost, turnover, or
  balance change preserves the unclean block.

## Latest validation

```text
Python 3.13.15; no Phase 11.3 dependency added
ruff + format: PASS (213 files)
mypy: PASS (109 source files)
pytest: PASS (340 tests, 86.62% branch coverage)
Secret scan: PASS (317 text files)
pip-audit: PASS (no known vulnerabilities)
Compose config: PASS; paper-runtime healthy
Final image: PASS (quantforge-paper-runtime, sha256:33680a3c...eff37)
Verified 10,000-event neutral decision replay: 2,286.57 events/s; feature p99 0.352ms;
decision p99 0.850ms; combined p99 1.133ms; max 2.602ms; 3,328 inference frames
Sustained runtime: 895 accepted, 561 periodic committed, retained rows 70,517;
queue 0/65,536, overflows/parser errors/reconnects zero
Live decision snapshot: p99 1.079ms; max 1.289ms; zero 5ms breaches; recovery VERIFIED_CLEAN;
recovery block, model approval, paper-order gate, proposals, risk approvals, paper orders/fills,
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
- Work/Codex schedules are not active. Most representative exports are not populated. Follow the
  manual-trial and first-three-run review process before registering any task.
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
- The Windows host lacks `uv` and `make` on PATH; exact Make targets were unavailable. Equivalent
  isolated-venv checks and the pinned-uv container build passed.
- The owner requires concise Korean Conventional Commits, committed and pushed on `main`, and a
  minimal public README.

## Next actions

1. Keep paper mode. Run and observe the supervised public burn-in; measure coverage, gaps, parser
   failures, reconnects, restarts, disk growth, and retention without treating uptime as readiness.
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
6. Register Work/Codex schedules only after each manual prompt passes. Continue report-only/dedicated-
   worktree boundaries and never auto-merge/deploy/promote/change risk/live state.
7. Assemble reviewed evidence and re-run `validate-live-readiness`. A manual canary remains a future
   separately approved project even if the output reaches manual-review eligibility.

# QuantForge Handoff

## Restore context

Read `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, and this
file before continuing. Inspect code and evidence; do not infer completion from prompts alone.

## Current state

- Date: 2026-08-24 KST
- Completed phases: 0–10
- Current checkpoint: Korean public-data monitor added to supervised public paper burn-in;
  sustained evidence and real-time paper orchestration next
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

## Implemented through Phase 10.1

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
- ADR-001 through ADR-015 record consequential design choices. README remains intentionally minimal.

## Latest validation

```text
Python 3.13.15; no Phase 10 dependency added
ruff + format: PASS (207 files)
mypy: PASS (107 source files)
pytest: PASS (307 tests, 86.60% branch coverage)
Secret scan: PASS (307 text files)
pip-audit: PASS (no known vulnerabilities)
Compose config: PASS, including isolated paper-runtime
Host public smoke: 30 accepted/committed, no parser error/reconnect/auth/private/order path
Host offline replay: 30 verified inputs, stable dataset/output hashes
Phase 10 image: PASS (quantforge:phase10, sha256:9fade54b...0522)
Monitor image: PASS (quantforge-paper-runtime, sha256:37e8961e...1e087)
Container safety: paper, live=false, credentials=false, all six gates closed
Container public smoke: 10 accepted/committed; every auth/private/order/live flag false
Korean monitor: PASS; atomic self-contained HTML, five-second reload, no server/token/control path
Retained restart: 7,671 rows/48 files/1,568,641 bytes recovered; then increased to 8,109 rows/
51 files/1,656,597 bytes with healthy public WebSocket and no parser error/reconnect
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
- Public L2 fill/queue behavior is approximate. The collector is now supervised, but sustained
  coverage is not yet evidence and real-time paper strategy/execution is not composed. Models and
  strategies remain fixture-scale baselines with no profitability or promotion claim.
- The Korean monitor currently covers only public feed/storage visibility. The authenticated
  server-rendered dashboard/Grafana views remain internal operations skeletons, and there are no
  paper strategy, order, position, or performance results to display yet.
- Dashboard/recovery/authorization/network/storage hardening remains incomplete. Consult
  `docs/KNOWN_LIMITATIONS.md` and `docs/readiness/LIVE_READINESS.md`.
- The Windows host lacks `uv` and `make` on PATH; exact Make targets were unavailable. Equivalent
  isolated-venv checks and the pinned-uv container build passed.
- The owner requires concise Korean Conventional Commits, committed and pushed on `main`, and a
  minimal public README.

## Next actions

1. Keep paper mode. Run and observe the supervised public burn-in; measure coverage, gaps, parser
   failures, reconnects, restarts, disk growth, and retention without treating uptime as readiness.
2. Compose causal real-time bars/features, baseline inference, proposal-only routing, independent
   paper risk, conservative broker, exact ledger, and representative performance/model/data exports.
3. Extend the Korean monitor with strategy, risk, simulated order/fill, portfolio, and performance
   views only after those runtime export contracts are stable.
4. Design production PostgreSQL persistence, encrypted off-host backup/restore with measured RPO/RTO,
   TLS/RBAC/rate limits, Secret delivery, network isolation, and monitoring retention.
5. Under separate human authorization only, implement and review credential/order-test transport,
   identifier reconciliation, withdrawal-disabled/IP-allowlisted key policy, and multi-operator
   incident/cancel/recovery drills. Do not send a real order.
6. Register Work/Codex schedules only after each manual prompt passes. Continue report-only/dedicated-
   worktree boundaries and never auto-merge/deploy/promote/change risk/live state.
7. Assemble reviewed evidence and re-run `validate-live-readiness`. A manual canary remains a future
   separately approved project even if the output reaches manual-review eligibility.

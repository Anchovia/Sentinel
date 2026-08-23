# QuantForge Handoff

## Restore context

Read `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, and this
file before continuing. Inspect code and evidence; do not infer completion from prompts alone.

## Current state

- Date: 2026-08-23 KST
- Completed phases: 0–9
- Current checkpoint: implementation plan complete; operational evidence/hardening next
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

## Implemented through Phase 9

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
- ADR-001 through ADR-013 record consequential design choices. README remains intentionally minimal.

## Latest validation

```text
Python 3.13.15; no Phase 9 dependency added
ruff + format: PASS (202 files)
mypy: PASS (105 source files)
pytest: PASS (294 tests, 86.59% branch coverage)
Secret scan: PASS (300 text files)
pip-audit: PASS (no known vulnerabilities)
Compose config: PASS
Phase 9 image: PASS (quantforge:phase9, sha256:15fd924d...bf786)
Container safety: paper, live=false, credentials=false, all six gates closed
Container readiness: NOT_READY, all 13 missing gates fail, no activation/network/order/settings
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
- Public L2 fill/queue behavior is approximate; the collector is bounded; models/strategies are
  fixture-scale baselines with no profitability or promotion claim.
- Dashboard/recovery/authorization/network/storage hardening remains incomplete. Consult
  `docs/KNOWN_LIMITATIONS.md` and `docs/readiness/LIVE_READINESS.md`.
- The Windows host lacks `uv` and `make` on PATH; exact Make targets were unavailable. Equivalent
  isolated-venv checks and the pinned-uv container build passed.
- The owner requires concise Korean Conventional Commits, committed and pushed on `main`, and a
  minimal public README.

## Next actions

1. Keep paper mode. Build continuous supervised public collection and representative Secret-free
   operations/performance/model/data/incident/readiness evidence producers.
2. Design production PostgreSQL persistence, encrypted off-host backup/restore with measured RPO/RTO,
   TLS/RBAC/rate limits, Secret delivery, network isolation, and monitoring retention.
3. Under separate human authorization only, implement and review credential/order-test transport,
   identifier reconciliation, withdrawal-disabled/IP-allowlisted key policy, and multi-operator
   incident/cancel/recovery drills. Do not send a real order.
4. Register Work/Codex schedules only after each manual prompt passes. Continue report-only/dedicated-
   worktree boundaries and never auto-merge/deploy/promote/change risk/live state.
5. Assemble reviewed evidence and re-run `validate-live-readiness`. A manual canary remains a future
   separately approved project even if the output reaches manual-review eligibility.

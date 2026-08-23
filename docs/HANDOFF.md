# QuantForge Handoff

## Restore context

Read `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, and this
file before continuing. Inspect code and evidence; do not infer completion from prompts alone.

## Current state

- Date: 2026-08-23 KST
- Completed phase: 8 — Work/Codex Automation Support
- Current phase: 9 — Live Readiness (`IN_PROGRESS`)
- Branch: `main` by explicit owner instruction
- Remote: `origin` -> `https://github.com/Anchovia/Sentinel.git`
- Default mode: paper
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

## Implemented through Phase 8

- Safety-first modular monolith, six closed live gates, Decimal boundary, keyless public pipeline,
  immutable raw lineage, deterministic replay/features/backtests, conservative paper execution,
  exact portfolio ledger, chronological preregistered research, and immutable model registry.
- Proposal-only strategies, independent risk gateway, attribution, manual-release kill switch,
  mock-only private contracts, burned identifiers, fsynced journal, identifier-first recovery,
  reconciliation, and a disabled live adapter with no order network.
- Secret-rejecting operations export, authenticated read dashboard, Prometheus/Grafana health views,
  hash-chain incident/audit/control records, local cancel-only and incident acknowledgement, and
  checksummed paper restore drills. Production backup/recovery is not claimed.
- Nine repository-local skills cover the requested Work/Codex roles. Ten independent prompts and an
  Asia/Seoul RRULE catalog exist, but registration is deliberately `not_registered`.
- `automation-report-1` and `automation-trigger-1` are closed evidence contracts. Safety flags can
  only be false, Work cannot emit a change candidate, and triggers contain no command field.
- A deny-first allowlist limits Work to report/proposal paths and excludes Codex writes to Secret,
  risk/live/release/CI/production/data/artifact boundaries. Traversal, drive paths, symlink
  components, and credential-shaped report text fail closed.
- Offline validation commands check manifests, requested writes, and the actual linked-worktree
  state. Codex scheduled reports fail in the primary checkout; source candidates require evidence,
  validation, and a non-main branch. There is no merge/deploy/promote/live/order function.
- An actual detached worktree no-op passed at Phase 7 `main` without creating a branch. The temporary
  clean worktree was deliberately removed; the primary `main` checkout is the only remaining one.
- ADR-012 records the isolation decision. Official current OpenAI scheduled-task, Work, skill, and
  worktree guidance is linked from the setup guide and ADR.

## Latest validation

```text
Python 3.13.15; no Phase 8 dependency added
ruff + format: PASS (195 files)
mypy: PASS (101 source files)
pytest: PASS (278 tests, 87.04% branch coverage)
repository skills: PASS (9/9)
manual report envelopes: PASS (all skill actor modes)
main-checkout rejection + detached worktree no-op: PASS
Secret scan: PASS (289 text files)
pip-audit: PASS (no known vulnerabilities)
Compose config: PASS
real/private/test orders: none
automation network/order capability: false
automatic merge/deploy/promotion/live activation: false
schedules: not registered
```

## Important constraints

- Real Work/Codex schedules have not been created. Follow `automation/SCHEDULED_TASK_SETUP.md`; test
  manually and review the first three runs. Local tasks require the computer and desktop app.
- Performance/model/open-incident exports are not yet populated with representative runtime data.
  Missing evidence should yield a short `BLOCKED` report, not invented findings.
- The repository validator and prompt write allowlist are not OS-level per-path ACLs. Preserve
  before/after Git evidence and keep task sandbox/network permissions narrow.
- No Codex change candidate or PR was needed in Phase 8. The no-op worktree proof does not validate a
  future patch's correctness; every future candidate still needs reproduction, regression tests,
  full checks, and human review.
- The dashboard, single-writer journals, local backup proof, and incomplete runtime producers retain
  the Phase 7 limitations documented in `PROGRESS.md` and `docs/KNOWN_LIMITATIONS.md`.
- No authenticated exchange transport, production Secret provider, live/test order endpoint,
  production recovery, or profitable/promotable strategy/model evidence exists.
- The owner requires one concise Korean Conventional Commit per phase, committed and pushed directly
  on `main`. Keep the public README extremely minimal.

## Next actions

1. Implement a deterministic, read-only Phase 9 readiness evidence contract and evaluator. Keep all
   missing evidence fail-closed as `NOT_READY`.
2. Cover paper duration/trade count, reconciliation, data availability, incidents, model/drawdown/
   cost stability, order-test evidence, backup/restore, security, runbooks, all six live locks, and
   human approvals without executing an order or changing state.
3. Add fixtures for contradictory, stale, tampered, missing, conditionally ready, and fully evidenced
   manual-canary-review cases. `READY_FOR_MANUAL_CANARY_REVIEW` must not activate live.
4. Run all validation, update ADR/progress/handoff, then commit and push Phase 9 on `main` with a
   concise Korean Conventional Commit.

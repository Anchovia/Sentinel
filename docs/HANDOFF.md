# QuantForge Handoff

## Restore context

Read `AGENTS.md`, `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `RISK_POLICY.md`, `ARCHITECTURE.md`, and this
file before continuing. Inspect code and evidence; do not infer completion from prompts alone.

## Current state

- Date: 2026-08-23 KST
- Completed phase: 7 — Dashboard and Operations
- Current phase: 8 — Work/Codex Automation Support (`IN_PROGRESS`)
- Branch: `main` by explicit owner instruction
- Remote: `origin` -> `https://github.com/Anchovia/Sentinel.git`
- Default mode: paper
- Live network capability: false
- Actual/private/test orders: none
- Production Secrets: not requested or accessed
- Phase 0: `cfc1617 feat: QuantForge 안전 기반 구축`
- Phase 1: `136295c feat: 업비트 공개 데이터 파이프라인 구축`
- Phase 2: `41b64d1 feat: 결정적 재생과 인과 특징 구축`
- Phase 3: `0f7e3a1 feat: 보수적 모의 체결과 백테스트 구축`
- Phase 4: `b1a6b03 feat: 재현 가능한 기준 모델 연구 구축`
- README cleanup: `74a2bee chore: 공개 README 간소화`
- Phase 5: `91962b9 feat: 전략 라우팅과 위험 게이트 구축`
- Phase 6: `ac7798b feat: 모의 비공개 주문 안전 경계 구축`

## Implemented through Phase 7

- Safety-first Python modular monolith, six live gates, Decimal domain boundary, structured
  redaction, CI/Compose/container skeleton, and public health/safety/metrics.
- Keyless Upbit public transport, immutable raw lineage and Parquet manifests, deterministic replay,
  explicit gaps/bars/causal features, runtime data-quality snapshots, and public metrics.
- Conservative event-driven paper execution and exact FIFO portfolio accounting, deterministic
  backtests, chronological preregistered model research, sealed holdout, immutable model registry,
  proposal-only strategies, independent risk gateway, attribution, and manual-release kill switch.
- Mock-only private order/event contracts, deterministic burned identifiers, fsynced order journal,
  identifier-first timeout/restart recovery, exact reconciliation, and disabled live adapter.
- Versioned operations read model and atomic Secret-rejecting export; authenticated JSON/HTML
  dashboard; operations Prometheus metrics and Grafana health dashboard.
- Fsynced hash-chain incident/audit/control records; confirmation, CSRF, idempotency, result
  verification, duplicate suppression, and interrupted-request UNKNOWN handling.
- Local-only cancel-only activation and incident acknowledgement. Strategy pause is proposal-only;
  cancel-all is blocked and no control can release/flatten/edit risk/models/live state/send orders.
- Checksummed explicit-source local backup and empty-target paper restore drill with Secret, symlink,
  traversal, extra-file, and tamper rejection. Production backup is not claimed.

## Latest validation

```text
ruff + format: PASS (169 files)
mypy: PASS (98 source files)
pytest: PASS (254 tests, 87.17% branch coverage)
Secret scan: PASS (244 text files)
pip-audit: PASS (no known vulnerabilities)
Compose config: PASS
Phase 7 API/control/export/backup tests: PASS
Phase 7 image: PASS (quantforge:phase7, sha256:c52ccccf...5ae6a)
Container safety: paper, live=false, six gates closed
Container operations: dashboard auth false by default; control/live network false
Container export: operations-dashboard-1; auth/network/order use false
```

## Important constraints

- The dashboard has a single bearer operator role and no RBAC/SSO/TLS ingress/application rate
  limiter. External dashboard Secret delivery is required; default operations access is closed.
- Operations journals are single-writer files, not a transactional or replicated database.
- Runtime producers do not yet populate every dashboard view. Exports are generated manually.
- Local backups are unencrypted restore proofs; PostgreSQL/off-host/credential/raw-tick recovery and
  measured RPO/RTO are absent.
- No authenticated exchange transport, real cancellation, test-order call, or live adapter exists.
- Work/Codex scheduled skills, schemas, prompts, allowlists, and schedules are not implemented yet.
- The owner requires one concise Korean Conventional Commit per completed phase, committed and
  pushed directly on `main`. Keep the public README extremely minimal.

## Next actions

1. Read the official OpenAI/Codex scheduled-task guidance through the repository's required
   documentation workflow before implementing Phase 8 support.
2. Add repository-local Work and Codex skills, prompts, schemas, output allowlists, and dedicated
   scheduled-worktree rules from the supplied second and third prompts.
3. Generate representative redacted exports and run every skill manually, including clean no-op,
   failed-test, untrusted-input, and forbidden-write cases.
4. Keep Work report-only and Codex PR-candidate-only. Do not register a schedule until manual trials
   pass; do not auto-merge, deploy, promote, change risk, access Secrets, or call order paths.

# QuantForge Progress

## Current checkpoint

- Phase: 9 — Live Readiness
- Status: `COMPLETE`
- Planned implementation phases: 0–9 complete
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; the live adapter has no network capability
- Readiness result: `NOT_READY`
- Actual orders executed: no
- Private/authenticated Upbit calls: no
- Production Secrets accessed: no
- Scheduled task registration: none
- Automatic merge/deploy/model promotion/live activation: unavailable

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
Python: PASS — 3.13.15; no Phase 9 dependency added
ruff: PASS — all checks passed
format check: PASS — 202 files formatted
mypy: PASS — 105 source files, no issues
pytest: PASS — 294 tests, 86.59% branch coverage
readiness missing evidence: PASS — NOT_READY, all 13 gates failed closed
readiness hard/preferred boundary: PASS — CONDITIONALLY_READY
readiness complete synthetic fixture: PASS — READY_FOR_MANUAL_CANARY_REVIEW only
readiness safety regressions: PASS — UNKNOWN order, stale security, local backup, future evidence,
  mismatched approvals/artifacts, protected policy, and oversized canary all rejected
runtime settings isolation: PASS — readiness CLI does not load settings/.env
transport isolation: PASS — readiness package has no exchange/HTTP imports
secret scan: PASS — 300 text files checked
dependency audit: PASS — no known vulnerabilities
Compose config: PASS — base + paper overlays
container build: PASS — quantforge:phase9 sha256:15fd924d...bf786
container safety: PASS — paper, live=false, all six gates failed closed, credentials=false
container readiness: PASS — NOT_READY, 13 missing gates, no activation/network/order/settings change
schedule registration: NONE
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
- Phase 8 tasks remain unregistered and representative performance/model/incident exports are not
  populated. Local schedules require the computer and desktop app.
- The Windows host lacks `uv` and `make` on PATH, so exact Make targets were not run in this phase;
  their equivalent locked project-venv commands passed. Container builds use the pinned uv image.
- Dashboard, local journals, backup proof, public-L2 fill approximation, bounded public collector,
  missing authenticated transport, and synthetic research limitations remain documented.

## Next milestone

Do not enable live trading. The next work is operational evidence production and hardening: sustained
paper supervision, continuous runtime exports, production storage/backup/TLS/RBAC/network design,
authorized dry-run order-test and reconciliation evidence, multi-operator drills, and independent
security/release reviews. Re-run the validator after each reviewed evidence bundle; pursue a manual
canary implementation only if every gate truly passes and separate human authority is granted.

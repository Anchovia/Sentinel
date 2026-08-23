# QuantForge Progress

## Current checkpoint

- Phase: 8 — Work/Codex Automation Support
- Status: `COMPLETE`
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; the live adapter has no network capability
- Actual orders executed: no
- Private/authenticated Upbit calls: no
- Production Secrets accessed: no
- Automation schemas: `automation-report-1` / `automation-trigger-1`
- Scheduled task registration: none
- Automatic merge/deploy/model promotion/live activation: unavailable
- Next phase: 9 — Live Readiness (`IN_PROGRESS`)

## Completed in Phase 8

- Added the five Work skills and five Codex skill roles requested by the supplied prompts. The shared
  strategy-research skill has explicit report-only Work and preregistered-worktree Codex modes. All
  nine skill packages pass the repository skill validator and can produce valid no-op/blocked
  envelopes when inputs are absent or no issue is found.
- Added five Work and five Codex standalone prompt files plus an Asia/Seoul schedule catalog. The
  catalog remains `not_registered`; local tasks require the desktop project and manual trial review.
- Added closed, versioned report and Work-to-Codex trigger schemas. Safety fields accept only false;
  triggers contain structured evidence and requested paths, not executable command fields.
- Added a deny-first write allowlist. Work is limited to reports/proposals. Codex rejects Secret,
  risk/live configuration, release artifact, CI workflow, production operations, data/artifact, path
  traversal, drive-qualified, and existing-symlink writes.
- Added `validate-automation-report` and `validate-automation-trigger`. Both are offline and have no
  authentication or order dependency. Work cannot claim a source-change outcome.
- Added real Git linked-worktree inspection. A Codex report is rejected from the primary checkout;
  a change candidate additionally needs a non-main branch, reproducible evidence, and validation.
- Proved a Codex no-op report in a temporary detached worktree at the reviewed `main` revision. No
  branch was created, the owner checkout stayed untouched, and the clean temporary worktree was
  removed after verification.
- Added ADR-012 and updated architecture, data, security, runbook, recovery, schedule, and handoff
  documentation. The public README remained unchanged and minimal.

## Validation evidence

```text
Python: PASS — 3.13.15; no Phase 8 dependency added
ruff: PASS — all checks passed
format check: PASS — 195 files formatted
mypy: PASS — 101 source files, no issues
pytest: PASS — 278 tests, 87.04% branch coverage
skill validation: PASS — 9/9 repository skills
manual skill envelopes: PASS — every Work/Codex skill, including both research modes
report/trigger boundary: PASS — no-op, blocked, source denial, protected path, traversal, Secret
primary checkout rejection: PASS — Codex scheduled report denied on main checkout
detached worktree proof: PASS — Codex NO_ACTION, branch=null, network/order capability false
temporary worktree cleanup: PASS — no branch created and only primary main worktree remains
secret scan: PASS — 289 text files checked
dependency audit: PASS — no known vulnerabilities
Compose config: PASS — base + paper overlays
schedule registration: NONE — catalog remains not_registered pending operator setup
```

## Known constraints

- The prompts, skills, schemas, and catalog are implemented, but no Work or Codex scheduled task has
  been registered. Most performance/model/incident exports are still placeholders, so their real
  manual runs should correctly return `BLOCKED` until representative producers exist.
- Write allowlists and validation are repository controls, not an operating-system ACL. Work must
  still compare protected Git paths before/after, and scheduled permissions must remain narrow.
- A report manifest describes intended/observed writes; human review remains necessary to detect an
  omitted write or misleading external evidence. The first three scheduled results require review.
- Codex change candidates were not tested because Phase 8 found no reproducible code defect. Only a
  detached no-op worktree was exercised; no branch or PR was created.
- The schedule catalog does not compute next-run timestamps and does not claim account-specific task
  capacity. The desktop app and computer must remain running for local project tasks.
- Phase 7 operational limitations remain: incomplete runtime producers, local single-writer journals,
  development-only dashboard auth/storage, and non-production local backup proof.
- No authenticated exchange transport, real cancellation, test-order call, credential provider, or
  live adapter exists. Research baselines remain synthetic and are not promotion evidence.

## Next milestone

Implement Phase 9 as a read-only live-readiness validator. It must evaluate paper duration/trade
count, reconciliation/data/incident/model/drawdown/cost stability, order-test evidence, backup/
restore, security, operator runbooks, six live locks, and approvals. Output only `NOT_READY`,
`CONDITIONALLY_READY`, or `READY_FOR_MANUAL_CANARY_REVIEW`; never activate live trading.

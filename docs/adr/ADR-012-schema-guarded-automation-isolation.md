# ADR-012: Schema-guard report automation and isolate code automation

- Status: Accepted
- Date: 2026-08-23

## Context

QuantForge needs unattended operational analysis without putting a language model in the order path
or allowing a report job to mutate source. Some Codex audits may justify a code candidate, but the
owner's active `main` checkout, production Secrets, risk approvals, and deployment must remain
outside scheduled authority. External reports and logs can also contain prompt injection.

Current official guidance says desktop scheduled tasks may use a local project or isolated
worktree, local runs require the computer and app to remain available, skills can be invoked
explicitly, and narrow permissions plus manual prompt testing are preferred. Web-only long-running
work cannot directly write a local folder.

## Decision

Use two explicit actor contracts:

- Work is report-only and may write only `reports/work/**` or research proposals. It never claims a
  code-change outcome or Codex worktree.
- Scheduled Codex work requires a linked dedicated worktree. A no-op may remain detached; a change
  candidate requires a non-`main` branch, reproducible evidence, regression validation, and only a
  draft PR candidate.

Every run emits an `automation-report-1` JSON manifest whose safety flags can only be false. Work-to-
Codex handoffs use `automation-trigger-1`, which carries typed evidence and requested paths but no
command field. A deny-first path allowlist rejects source writes from Work and protected Secret,
risk, live-release, CI, production operations, artifact, and data paths from Codex. Existing symlink
components and path traversal are rejected. The validator has no network or order dependency.

Repository-local skills and prompts are versioned, but schedules remain unregistered until the
matching prompt passes a manual trial and a human reviews it. The first three scheduled results also
require review. No automation may merge, deploy, promote, change risk/live approval, or access an
order endpoint.

## Consequences

- Normal no-finding, insufficient-evidence, and blocked results are preserved without unnecessary
  diffs.
- Work cannot repair a report-path violation; it must expose the breach for human handling.
- Codex can prepare a reviewable patch without modifying the active checkout, but a human remains
  responsible for branch/PR review, merge, release, and worktree cleanup.
- Missing runtime exports correctly block task registration; the catalog is documentation, not
  evidence that any schedule is active.

## References

- [Scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app)
- [Long-running work](https://learn.chatgpt.com/docs/long-running-work)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)

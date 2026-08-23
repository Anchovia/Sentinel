# Scheduled Task Setup

This file is an operator checklist. The repository does not register or enable any task by itself.

## Preconditions

1. Review `AGENTS.md`, `SECURITY.md`, `RISK_POLICY.md`, this guide, and
   `automation/write-allowlist.yaml`.
2. Generate only Secret-free runtime exports. Never expose `.env`, exchange credentials, production
   databases, or order endpoints to a task.
3. Run the exact prompt manually. Validate its JSON manifest with
   `uv run quantforge validate-automation-report` and inspect the Git diff.
4. Register only a prompt whose manual run is correct, concise in a normal state, and within its
   write boundary. Review at least its first three scheduled results.

## Work tasks

- Create these from the ChatGPT desktop project that points at this local repository. A web-only
  task cannot directly use this local folder.
- Use a standalone scheduled task, Asia/Seoul, the RRULE in
  `automation/schedules/tasks.yaml`, and the matching file under `automation/work/`.
- Keep network access disabled and grant writes only to `reports/work/**` and
  `runtime_exports/research/proposals/**`.
- Capture `git diff -- src configs ops migrations dashboard` before and after. If it changes, stop
  and report the breach without trying to conceal or rewrite it.

## Codex tasks

- Select the local repository and the dedicated background worktree option. Never select the user's
  primary `main` checkout for a scheduled code task.
- Use `workspace-write`. Keep network disabled unless a dependency review needs a named official
  source; never grant general full access.
- A finding needs reproducible evidence before code changes. A change needs a regression test and
  all required checks passing before a draft PR candidate. No finding is a successful no-op.
- Do not auto-merge, deploy, promote, change risk values, enable live mode, or submit/test/cancel an
  exchange order. A human must review every candidate.

See `automation/WORKTREE.md` for the isolation proof and cleanup rule. The computer and desktop app
must remain running for scheduled tasks that use local files. Official references reviewed on
2026-08-23: [Scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app),
[long-running work](https://learn.chatgpt.com/docs/long-running-work),
[skills](https://learn.chatgpt.com/docs/build-skills), and
[Git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees).

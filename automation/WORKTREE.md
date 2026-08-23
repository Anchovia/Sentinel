# Scheduled Codex Worktree Contract

A scheduled Codex run must use a dedicated background worktree. Worktrees share Git history but
have separate checked-out files, so the owner's primary `main` checkout remains untouched.

Before analysis:

1. Confirm `.git` is a linked-worktree file rather than the primary checkout directory.
2. Record the reviewed `main` base revision in the report manifest.
3. Keep the worktree detached for a no-op audit. Create a non-`main` candidate branch only after a
   reproducible issue justifies a change.
4. Confirm paper mode, closed live gates, no exchange credentials, no order network capability, and
   the write allowlist.

Before a PR candidate:

1. Add the smallest regression test first, then the smallest safe fix.
2. Run the relevant suite, Ruff, formatting, mypy, Secret scan, dependency/security checks, and any
   required deterministic replay.
3. Validate the report manifest from inside the same worktree. A change candidate on detached HEAD
   or `main` is rejected.
4. Create at most a draft PR candidate. Never merge or deploy it.

No-op and blocked runs write only their `reports/codex/**` report artifacts. After human review or
archive, remove stale worktrees through the Codex task UI or a deliberate operator cleanup. Never
delete an unreviewed worktree with changes.

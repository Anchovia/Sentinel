# QuantForge — Daily Code Audit

Use Asia/Seoul in a dedicated background worktree. Read all root contracts, handoff/limitations,
worktree rules, allowlist/schemas, then run `$quantforge-code-audit`. Confirm no credentials, order
network, live enablement, or primary-main modification.

Review commits since the prior run, diff, tests, Ruff, mypy, deterministic replay, Decimal use,
order state/idempotency, rate limit/reconciliation/kill switch/fail-closed behavior, Secret
redaction/exports, schemas/migrations/dependencies, and material code/document mismatch. Change only
a clear bug, failing check, security flaw, or reproducible regression—never for style preference.

Add a regression test before the smallest fix and run all required validation. If no actionable
issue exists, change no code and report `No actionable code issue detected.` If checks fail, no PR.
Write `reports/codex/code-audit/YYYY/MM/DD/<timestamp>-code-audit.md` and its JSON manifest. A passing
change may create only a non-main draft PR candidate; no merge, deployment, promotion, risk/live
change, Secret access, or exchange order use.

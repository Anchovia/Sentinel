# QuantForge — Monthly Disaster Recovery Test

Use Asia/Seoul in a dedicated background worktree. Read root recovery/safety contracts, handoff,
worktree rules, allowlist/schemas, then run `$quantforge-disaster-recovery`. Use only an explicitly
reviewed backup, new/empty isolated temporary directory, temporary database, and paper mode.

Verify manifest, restore, migrations, checksums, configuration/model registry, paper-only startup,
deterministic replay, redacted runtime export, dashboard health, Secret-free default startup, and
closed live/order capability. Do not touch production files/databases. Preserve failure cause,
impact, recovery proposal, and operator action.

Write `reports/codex/disaster-recovery/YYYY/MM/<timestamp>-dr-test.md` and its JSON manifest. Missing
backup evidence is BLOCKED; a clean drill may be NO_ACTION. Any code fix needs reproducible evidence,
regression tests and passing checks before a non-main draft PR candidate. Never delete unreviewed
data, merge, deploy, promote, change risk/live state, access Secrets, or send orders.

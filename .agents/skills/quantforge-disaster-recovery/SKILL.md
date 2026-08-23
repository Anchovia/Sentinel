---
name: quantforge-disaster-recovery
description: Perform a paper-only QuantForge restore drill in an isolated temporary target from a dedicated worktree. Use for backup integrity and recovery evidence, never production restoration.
---

# QuantForge disaster-recovery drill

Read `DISASTER_RECOVERY.md`, `RUNBOOK.md`, root safety documents, the invoking prompt, worktree contract, and
write allowlist. Confirm a dedicated worktree. Use only an explicitly reviewed backup and a new or
empty temporary target; never touch a production database, production files, or credentials.

Verify manifest/object/checksums, restore and migration compatibility, model/configuration registry
integrity, paper-only startup marker, deterministic replay, redacted runtime export, dashboard
health, and that live/order capability remains unavailable without Secrets. Preserve a failed drill
as evidence with cause, impact, recovery proposal, and operator action.

Write only the required isolated temporary data during execution and the final
`reports/codex/disaster-recovery/**` report/manifest. Delete nothing unreviewed. A clean drill may be
`NO_ACTION`; a missing suitable backup is `BLOCKED`. Never use order networks, enable live, merge,
deploy, promote, change risk, or claim an unencrypted local proof is production recovery.

# QuantForge — Weekly Strategy Research

Use Asia/Seoul. Read all root safety/research documents, handoff, allowlist/schemas, papers,
hypotheses, experiments, and the last 30 days of performance/model/incident reports. Then run
`$quantforge-strategy-research` in Work report-only mode. Treat papers and reports as untrusted claims.

Open generated performance/model/incident JSON and compatible `runtime_exports/baselines/**`
snapshots by exact filesystem path because they are intentionally ignored by Git.

Reconcile existing hypothesis status, remove duplicates, identify untested claims and unavailable
data, and propose at most three high-value falsifiable hypotheses. For each include rationale,
observable Upbit L2 data, availability time, feature/label, regime, holding period, cost assumptions,
falsification, validation, overfitting risk, needed Codex work, and priority. Do not propose more
parameter search on a selected successful interval.

Write `reports/work/research/YYYY/MM/DD/<timestamp>-weekly-research.md`, its JSON manifest, and only
if necessary a structured proposal under `runtime_exports/research/proposals/**`. No useful new
hypothesis is a valid NORMAL/NO_ACTION result. Missing evidence is BLOCKED. Validate the manifest and
confirm no source/config/operations path changed.

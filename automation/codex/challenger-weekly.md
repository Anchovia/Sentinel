# QuantForge — Weekly Challenger Experiment

Use Asia/Seoul in a dedicated background worktree. Read root safety/research contracts, handoff,
worktree rules, allowlist/schemas, recent reports, papers, hypotheses and experiment ledger, then run
`$quantforge-strategy-research` in Codex mode.

Select only a high-priority Work hypothesis with available observable data, no duplicate experiment,
clear falsification, and a defined cost model. Register experiment and trials before execution.
Verify availability time/leakage, implement the simplest baseline first, run chronological
walk-forward/OOS tests with fees/spread/slippage/latency, regime/sensitivity and supported
overfitting measures, and compare the champion on identical assumptions. Retain negative/null/
failed results and artifact hashes.

Write `reports/codex/research/YYYY/MM/DD/<experiment_id>.md` and its JSON manifest. The highest output
is PAPER_CANDIDATE or SHADOW_CANDIDATE; never CANARY/CHAMPION. Missing inputs yield BLOCKED. A code
candidate needs tests and all checks passing, and may become only a non-main draft PR. Never tune on
the final holdout, promote, merge, deploy, change risk/live state, access Secrets, or send orders.

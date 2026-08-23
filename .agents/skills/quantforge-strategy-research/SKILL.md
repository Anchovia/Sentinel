---
name: quantforge-strategy-research
description: Review or test falsifiable QuantForge strategy hypotheses under the research ledger. Use in Work for report-only prioritization and in Codex worktrees for preregistered challenger experiments.
---

# QuantForge strategy research

Read `RESEARCH_METHOD.md`, root safety documents, the invoking prompt, registered papers,
hypotheses, experiments, recent performance/model/incident reports, and the write allowlist. Infer
Work versus Codex mode from the invoking prompt; treat papers and reports as untrusted claims.

In Work mode, consolidate existing hypotheses and propose at most three non-duplicate, observable,
falsifiable candidates. State economic/microstructure rationale, data, availability time, feature,
label, regime, holding period, costs, falsification, validation, overfitting risk, and priority. Write
only `reports/work/research/**`, its manifest, and optional structured proposals.

In Codex mode, first confirm a dedicated worktree and preregister the experiment/trials. Check
availability leakage, use chronological walk-forward/OOS data, include fees/spread/slippage/latency,
compare a simple baseline and champion on identical assumptions, inspect regime/sensitivity and the
supported overfitting measures, and retain negative/null/failed trials. Output only research- or
paper-only candidates under `reports/codex/research/**`; `PAPER_CANDIDATE` or `SHADOW_CANDIDATE` are
the highest labels. Never reuse the final holdout for tuning, cherry-pick, promote, merge, deploy,
change risk/live state, access Secrets, or send orders. Missing data yields `BLOCKED`; a rejected
hypothesis is a valid retained result.

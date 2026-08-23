# QuantForge

QuantForge is an AI-assisted quantitative research and autonomous trading platform for Upbit KRW spot markets. The repository is named **Sentinel**; the product and Python package are named **QuantForge**.

The project is safety-first:

- `paper` is the default trading mode.
- Real order submission is disabled unless six independent live gates are satisfied.
- ChatGPT Work, Codex, and other LLMs are never part of the real-time order path.
- Research and scheduled work cannot promote models, relax risk limits, merge, or deploy automatically.
- Monetary accounting uses `Decimal`; binary floats are rejected at monetary boundaries.

## Current status

Phase 4 (reproducible baseline-model research) is complete. QuantForge can
collect and deterministically replay keyless public data, build causal bars/features, model naive or
conservative L2 fills, and reconcile every simulated fill through a Decimal FIFO hash-chain ledger.
Chronological datasets keep a sealed final holdout; experiments require preregistration; simple
regime, alpha, and execution baselines are evaluated with calibration, uncertainty, abstention, and
non-zero costs; artifacts enter an immutable hash-verified registry without automatic promotion.
No model has been trained on production data, promoted, or connected to a real order path.

See [SPEC.md](SPEC.md), [PLAN.md](PLAN.md), [PROGRESS.md](PROGRESS.md), and [RISK_POLICY.md](RISK_POLICY.md) before changing behavior.

## Developer quick start

Prerequisites:

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose for infrastructure smoke tests

```text
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run mypy src
uv run quantforge safety-status
uv run quantforge collect-public --max-messages 100
uv run quantforge replay-raw --input-root data/raw
```

`make bootstrap`, `make test`, `make lint`, and `make typecheck` wrap the same commands on systems with Make installed.

## Safety notice

This software is a research platform, not a promise of profitability. Live trading remains disabled by default and requires separate operator, policy, model-release, and release-manifest approvals.

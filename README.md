# QuantForge

QuantForge is an AI-assisted quantitative research and autonomous trading platform for Upbit KRW spot markets. The repository is named **Sentinel**; the product and Python package are named **QuantForge**.

The project is safety-first:

- `paper` is the default trading mode.
- Real order submission is disabled unless six independent live gates are satisfied.
- ChatGPT Work, Codex, and other LLMs are never part of the real-time order path.
- Research and scheduled work cannot promote models, relax risk limits, merge, or deploy automatically.
- Monetary accounting uses `Decimal`; binary floats are rejected at monetary boundaries.

## Current status

Phase 1 (public market data) is complete. QuantForge can collect keyless Upbit ticker, trade, and
orderbook streams into checksummed ZSTD Parquet partitions. No private API or real orders are
implemented or executed.

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
```

`make bootstrap`, `make test`, `make lint`, and `make typecheck` wrap the same commands on systems with Make installed.

## Safety notice

This software is a research platform, not a promise of profitability. Live trading remains disabled by default and requires separate operator, policy, model-release, and release-manifest approvals.

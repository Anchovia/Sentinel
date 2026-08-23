# QuantForge Product Specification

## Mission

QuantForge is a safety-first quantitative research and trading platform for Upbit KRW spot markets. It combines public and private market data adapters, append-only event storage, deterministic replay, multi-horizon features, regime/alpha/execution models, strategy routing, an independent risk engine, paper trading, backtesting, observability, and human-reviewed research automation.

The system must be able to choose **HOLD** or **ABSTAIN**. Profitability is not guaranteed and is never represented as guaranteed.

## Product identity

- Repository: `Anchovia/Sentinel`
- Product and Python package: `QuantForge` / `quantforge`
- Primary language: Python
- Primary exchange: Upbit
- Initial market: KRW spot
- Storage timezone: UTC
- Display timezone: Asia/Seoul
- Default mode: `paper`
- Production mode: disabled by default

## Safety invariants

1. Development, tests, CI, research, and scheduled tasks never submit a real order.
2. ChatGPT Work, Codex, and other LLMs are outside the real-time decision and order path.
3. Strategies cannot call exchange order endpoints directly.
4. Every order intent passes through an independent deterministic risk decision.
5. Live submission requires all six gates defined in `RISK_POLICY.md`; any missing or invalid state fails closed.
6. Production credentials are never committed, logged, exported, or exposed to scheduled analysis.
7. Monetary accounting and order values use `Decimal`; float is permitted only inside analytical/model calculations.
8. Unknown order state blocks same-market submissions until reconciliation.
9. Models, strategies, risk limits, merge, and deployment require human review.
10. Negative and null research results remain in the trial ledger.

## Functional capabilities

The completed platform will provide:

1. Public Upbit WebSocket collection for supported ticker, trade, orderbook, and candle streams.
2. Private order/asset stream adapters behind credential and network boundaries.
3. Versioned event envelopes and append-only raw storage.
4. Deterministic replay with a virtual clock and input/config/artifact hashes.
5. Time, volume, and imbalance bars that distinguish no-trade intervals from data gaps.
6. Order-book, trade-flow, volatility, cross-asset, breadth, and technical baseline features.
7. Regime, alpha, execution-cost, and anomaly model interfaces with uncertainty and abstention.
8. Strategy routing based on net expected edge, regime, execution cost, and portfolio constraints.
9. Independent pre-trade risk checks, sizing, health gates, and kill switches.
10. Conservative L2 paper fills, partial fills, latency, fees, spread, slippage, and adverse selection.
11. Event-driven backtesting with walk-forward validation and multiple-testing controls.
12. An internal ledger, reconciliation, incident tracking, runtime exports, API, dashboard, and metrics.
13. Research registries for papers, hypotheses, experiments, trials, models, and releases.
14. Report-only ChatGPT Work audits and isolated Codex code/research scheduled tasks.
15. Backup, restore, and live-readiness validation without automatic live activation.

## Explicit non-goals

- Deposits, withdrawals, futures, margin, leverage, multi-exchange arbitrage, or colocation HFT.
- Martingale, unlimited averaging down, unlimited grids, loss chasing, spoofing, layering, or wash trading.
- LLM-generated natural-language trade commands or news-driven immediate orders.
- Self-modifying production code, automatic merge/deploy, or automatic risk-limit relaxation.
- Cost-free backtest claims, selected-result deletion, repeated final-holdout tuning, or profit guarantees.

## Modes

- `backtest`: stored events under a deterministic virtual clock.
- `replay`: stored events at original or adjusted speed.
- `paper`: real-time public market data with simulated execution.
- `shadow`: produces signals and order intents but never transmits them.
- `live`: reserved for separately approved releases; unavailable in the foundation implementation.

## Acceptance baseline

Each phase must install, lint, type-check, test, and document its limitations before the next phase. External functionality that cannot be exercised safely uses mocks and recorded fixtures. No feature is marked complete without evidence in `PROGRESS.md` and `docs/HANDOFF.md`.

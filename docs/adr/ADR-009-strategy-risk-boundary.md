# ADR-009: Strategy proposals and independent risk authority

- Status: Accepted
- Date: 2026-08-23

## Context

Strategies need shared causal inputs and deterministic selection, but model confidence or expected
edge must never grant order authority. Correlated strategies must not gain weight by repeating the
same signal, and emergency release must not happen automatically.

## Decision

Strategies consume immutable market, feature, regime, alpha, execution, portfolio, and read-only
risk context. They return `StrategyDecision` proposals and do not import exchange, execution, order
intent, or submission code.

The router selects by positive net edge, explicit priority, capacity, status, strategy loss, and
cooldown. It keeps only the strongest member of each declared correlation group; it does not use
majority voting. The sole strategy-to-order adapter creates an intent and immediately submits it to
an independent deterministic risk engine.

The risk engine binds market, signal time, uncertainty, and edge to a versioned snapshot. It rejects
unsafe mode, health, freshness, model release, market, spread, depth, exposure, loss, drawdown,
turnover, order-rate, duplicate, and reconciliation state. Sizing uses exact Decimal arithmetic and
hard caps scaled by volatility, liquidity, confidence, uncertainty, correlation, and drawdown. Full
Kelly and loss-multiplier sizing remain prohibited.

The kill switch defaults to `cancel_only`. `cancel_and_flatten` requires separate operator approval
and an explicit liquidity-safe assessment. Release is a manual two-step action and remains blocked
until reconciliation succeeds. Every transition forms an append-only hash chain.

Attribution records gross edge PnL before fees, spread, slippage, and adverse selection, then
reconciles those costs to net PnL by strategy, model, market, and regime. It is separate from the
actual fill-price portfolio ledger so embedded execution costs are not subtracted twice.

## Consequences

- Strategy code cannot directly construct or submit an order.
- A router acceptance is not a risk approval.
- Missing, mismatched, stale, or unsafe inputs fail closed.
- Paper policies do not configure or approve live risk.
- Future execution adapters must accept only approved decisions and preserve the same boundary.

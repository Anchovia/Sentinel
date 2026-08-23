# ADR-021: Preregistered Short-Horizon Paper Research

- Status: accepted
- Date: 2026-08-24
- Scope: public-data research and paper simulation only

## Context

The real-time paper composition is deliberately neutral and has no approved entry or exit artifact.
Testing short-horizon rules directly on the growing feed without a fixed hypothesis, data cutoff,
cost model, or sample minimum would permit look-ahead, repeated holdout use, and attractive-interval
selection. Public Upbit L2 snapshots also do not reveal individual orders or exact queue position.

## Decision

Register three observable long-only hypotheses before trial execution: five-second trade
continuation, snapshot-derived book pressure, and their intersection. Bind them to a checksummed raw
data cutoff, availability ordering, feature thresholds, fixed KRW notional, profit target, stop
loss, time stop, cooldown, two conservative cost scenarios, three chronological folds, and a sealed
20-percent final holdout that this experiment cannot access.

Require at least 24 hours, 20,000 trade events, and 20,000 orderbook events in each of at least three
markets before running a challenger. A short or incomplete sample produces a retained `BLOCKED`
result with zero trials; it is not searched for a favorable subinterval.

Run any eligible rule through the existing latency-aware `conservative_l2` paper broker and exact
Decimal portfolio ledger. Record observed spread, configured non-zero fees, slippage, adverse
selection, latency, depth haircut, partial/non-fill behavior, turnover, drawdown, win rate, holding
time, and round-trip PnL. Name book-flow pressure `snapshot_derived_ofi`; never represent it as exact
order flow or queue evidence.

The always-neutral baseline emits no intent. The research engine has no credential source, private
or order network, runtime model approval, paper-order gate mutation, real order, automatic
promotion, or live activation method. `PAPER_CANDIDATE` is the maximum research label and still
requires separate human review and a separate paper-runtime approval.

## Consequences

- Initial data can truthfully block research while collection continues uninterrupted.
- Identical events, plan, cost scenario, code revision, market, rule, fold, and seed reproduce the
  same paper orders, fills, ledger, trades, and output hashes.
- A synthetic round trip verifies plumbing only; it is not market or profitability evidence.
- The registered fee is a simulation assumption, not a claim about the current Upbit fee schedule.
- The rotating 20-market detailed tier limits which assets can accumulate L2/trade evidence; all-KRW
  ticker coverage alone is insufficient for a short-horizon challenger.

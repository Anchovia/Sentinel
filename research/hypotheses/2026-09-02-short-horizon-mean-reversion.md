# Short-horizon sell-shock mean-reversion hypotheses

- Preregistered design date: 2026-09-02 (Asia/Seoul)
- Scope: fixed Upbit KRW spot public trade/orderbook observations
- Mode: offline research and paper simulation only
- Maximum outcome: `PAPER_CANDIDATE`
- Prior result: H-SCALP-001 through H-SCALP-003 are closed `REJECT`; they are not retried

## Motivation and separation from v4

The closed v4 continuation experiment was negative before and after costs: successful work units
had aggregate gross PnL `-131237.33226318459320` and net PnL
`-213726.256677355918048200`. V5 therefore does not loosen a v4 threshold or reuse a consumed
trial. It tests the opposite, falsifiable mechanism: a sharp seller-initiated move may become
temporarily exhausted, and causal recovery or visible bid replenishment may identify a short-lived
long-only reversal.

Only events received at or after `2026-08-30T07:44:05.793957Z`, the recorded v4 decision time, are
eligible. The upper receive-time cutoff, exact active-manifest hash, dataset hash, and the following
fixed markets must be sealed before any rule trial:

`KRW-BTC`, `KRW-DRV`, `KRW-ETH`, `KRW-EUL`, `KRW-FLUID`, `KRW-GAS`, `KRW-META2`, `KRW-ONG`,
`KRW-ONT`, `KRW-PROM`, `KRW-SOL`, `KRW-STX`, `KRW-TRUMP`, `KRW-USDT`, and `KRW-XRP`.

## H-SCALP-004 — sell-shock exhaustion

After a five-second trade return at or below `-15` bps with five-second trade imbalance at or below
`-0.25`, at least eight trades, a nonnegative one-second recovery return, and one-second trade
imbalance at or above `-0.05`, the next short horizon may reverse upward enough to exceed
conservative round-trip costs.

Falsification: reject if base or stress cost-inclusive out-of-sample net PnL is non-positive, the
median closed-trade net return is non-positive, sample sufficiency fails, or the direction is
unstable across registered folds or markets.

## H-SCALP-005 — bid-replenishment reversal

After the same five-second return shock, a top visible-book imbalance at or above `0.20`, total
visible-book imbalance at or above `0.10`, and snapshot-derived book-flow change at or above `0.02`
may identify bid replenishment and a short-lived upward reversal. This input is
`snapshot_derived_ofi`; it is not individual-order flow or exact queue evidence.

Falsification: reject under the same cost-inclusive criteria, or if the effect disappears under the
registered depth haircut, latency, partial-fill, slippage, and adverse-selection stress assumptions.

## H-SCALP-006 — confirmed reversal

Requiring H-SCALP-004 and H-SCALP-005 at the same causal feature frame may reduce frequency while
improving cost-adjusted precision and tail behavior over either single rule.

Falsification: reject if it fails the shared criteria or does not improve the preregistered primary
metric over both component rules on identical chronological cells.

## Fixed execution and validation contract

- Spread must be at most `8` bps; each long-only entry requests KRW `10,000` notional.
- Exit is fixed at a `30` bps profit target, `20` bps stop, `15` second time stop, and `15` second
  cooldown. Open positions close at split boundaries.
- Base and stress use the existing conservative public-L2 cost model, including nonzero fees,
  latency, depth haircut, partial/non-fill, slippage, and adverse selection.
- Three purged and embargoed chronological walk-forward folds, a sealed 20-percent final holdout,
  and the always-neutral baseline use identical events and cost assumptions.
- The fifteen fixed markets create exactly 270 validation/test work units: three hypotheses, two
  costs, three folds, and fifteen markets. Every success, failure, and null result is retained.
- Positive claims require the preregistered one-sided exact sign test with Holm correction plus
  market, fold, volatility, and spread stability. The final holdout remains unavailable to the
  bounded runner.

No result authorizes authentication, an exchange order, paper-order gate activation, risk-limit
changes, model promotion, live mode, deployment, or automatic investment.

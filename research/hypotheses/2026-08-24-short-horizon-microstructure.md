# Short-horizon public-microstructure hypotheses

- Registered: 2026-08-24 (Asia/Seoul)
- Scope: Upbit KRW spot public ticker/trade/orderbook observations
- Mode: research and paper only
- Maximum outcome: `PAPER_CANDIDATE`

## H-SCALP-001 — trade continuation

When a fresh market has a positive five-second return, concentrated buyer-initiated quote volume,
and elevated trade count while the spread remains bounded, the next short horizon may continue
upward far enough to exceed conservative round-trip costs.

Falsification: reject if chronological out-of-sample net PnL is non-positive, if the stress-cost
case is non-positive, or if the direction is unstable across planned folds and markets.

## H-SCALP-002 — snapshot book pressure

When top and total visible bid depth exceed ask depth and the snapshot-derived pressure is
increasing, the next short horizon may have positive net continuation after conservative costs.
This is explicitly `snapshot_derived_ofi`; it is not order-level flow or exact queue evidence.

Falsification: reject under the same cost-inclusive criteria, or if results disappear under the
pre-registered depth-haircut and latency stress case.

## H-SCALP-003 — confirmed continuation

Requiring H-SCALP-001 and H-SCALP-002 at the same availability timestamp may reduce trade count but
improve cost-adjusted precision and tail behavior relative to either single-factor rule.

Falsification: reject if it does not improve the pre-registered primary metric over both simple
rules on identical out-of-sample windows, or if sample sufficiency is not reached.

## Shared exit hypothesis

Each entry uses a fixed profit target, fixed stop loss, maximum holding time, and cooldown. These
values are strategy parameters registered before execution, not risk-policy changes. Every result
includes fees, observed spread, paper slippage, adverse selection, latency, partial/non-fill, and
the conservative public-L2 depth haircut.

No result authorizes a model, paper-order gate, real order, live mode, or production promotion.

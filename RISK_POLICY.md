# QuantForge Risk Policy

## Authority

This document is the highest-priority behavioral contract after account and data safety. Automated tasks may report defects or propose stricter behavior, but may not relax numeric limits or change approval state. Any policy change requires human review and an audit record.

## Default posture

- Default mode is `paper`.
- Foundation risk limits are zero and `live_limits_configured=false`.
- A missing, stale, malformed, or contradictory safety input is a rejection, never implied approval.
- A strategy's expected return cannot override health or hard-risk checks.

## Mandatory live gates

Every condition must be independently true at the execution boundary:

```text
TRADING_MODE=live
ALLOW_ORDER_SUBMISSION=true
LIVE_RELEASE_MANIFEST_VALID=true
RISK_POLICY_APPROVED=true
MODEL_RELEASE_APPROVED=true
OPERATOR_UNLOCK_PRESENT=true
```

No command-line flag, GUI toggle, configuration file, model output, or single approval can replace these gates. The live adapter also requires explicit dependency injection, production credentials from an external secret store, successful preflight, current reconciliation, and approved network policy. Phase 0 contains no live adapter.

## Pre-trade decision order

1. Mode and live locks.
2. Exchange/market status and warnings.
3. Public/private/REST health, data freshness, clock skew, and reconciliation age.
4. Feature/model availability, release status, freshness, uncertainty, and input-range checks.
5. Expected gross edge, all expected costs, and required safety margin.
6. Spread, depth, slippage, order policy, minimums, balance, and locked balance.
7. Order, position, portfolio, concentration, correlation, loss, drawdown, turnover, and cooldown limits.
8. Existing/unknown orders, identifier uniqueness, and request-rate capacity.

The risk decision is one of `allow`, `reject`, `resize`, or `hold`, with reason codes and a versioned snapshot.

The Phase 5 paper gateway also binds the snapshot to the intent market, signal time, net edge, and
uncertainty. Reusing a snapshot for a different or newer proposal is a rejection. `allow` or
`resize` can only be produced after every hard check passes; scaling may reduce but never enlarge
the requested amount. `configs/risk.paper.yaml` is a simulation policy and grants no live approval.

## Kill switch

`cancel_only` blocks new orders and requests cancellation of open orders. It is the default emergency behavior.

`cancel_and_flatten` is disabled by default. It requires separate operator approval and may act only within explicit liquidity/slippage limits; it must not panic-sell blindly.

Triggers include daily loss/drawdown breach, unknown order, balance mismatch, stale public data, excessive clock skew, reconciliation failure, authentication/rate-limit lockout, schema failure, repeated abnormal orders, or manual operator action. Unlock requires reconciliation and explicit human approval.

An authenticated create timeout is always `UNKNOWN`. Recovery must query the burned identifier and
must not submit again. Missing, failed, or mismatched lookup evidence keeps the order unknown and
blocks trading. The same fail-closed rule applies after a restart with `SUBMISSION_PENDING` in the
journal. Order-test responses are dry-run evidence only and cannot be queried, canceled, promoted to
an actual order, or used as proof that a later real order is safe.

The Phase 7 dashboard cannot alter this policy or release a kill switch. Its only verified safety
effect is local `cancel_only` activation. Strategy pause is a proposal and cancel-all is blocked
while authenticated cancellation transport is absent. Every emergency request requires bearer
authentication, a short-lived CSRF proof, an exact confirmation phrase, an idempotency key, a
durable request/result record, and a separate audit event. Interrupted requests become `UNKNOWN`
and are not executed again automatically.

## Position sizing

Initial sizing is conservative and combines hard notional caps with volatility, liquidity, confidence, uncertainty, correlation, and drawdown scaling. Full Kelly is forbidden. Risk limits are governance values, not model hyperparameters.

## Live-readiness review

Phase 9 does not enable live trading. The readiness policy checks paper duration/trades/regimes,
zero UNKNOWN orders/mismatches, data and model stability, cost-inclusive drawdown/expectancy,
calibrated costs, order-test, production recovery, security, runbooks, closed live locks, and four
distinct approval records bound to exact code/model hashes.

`READY_FOR_MANUAL_CANARY_REVIEW` means only that a human may review a separately controlled canary.
The runtime remains paper, order submission remains false, operator unlock remains absent, and the
validator changes no setting. Hard/preferred readiness thresholds are governance values that require
human review and do not guarantee profit or safety.

## Prohibited behavior

Martingale, loss-multiplier sizing, unlimited averaging down/grid/re-entry, manipulation, self-trading, rate-limit evasion, trading through data/health failures, ignoring uncertainty/costs, or automated risk relaxation are prohibited.

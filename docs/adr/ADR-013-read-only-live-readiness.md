# ADR-013: Keep live readiness evidence-only and activation-free

- Status: Accepted
- Date: 2026-08-23

## Context

Completing paper software is not evidence that it is safe or useful for a real-money canary. Short
PnL windows, point estimates, local backups, stale checks, or one approval can create false
confidence. A readiness tool that changes the state it inspects would also collapse the human safety
boundary.

## Decision

Implement a deterministic validator over a versioned `readiness-evidence-1` bundle and a reviewed
`readiness-policy-1`. It evaluates 13 gates covering paper history, reconciliation, data,
incidents, models, drawdown/net expectancy, cost calibration, order-test, recovery, security,
runbooks, live locks, and bound release approvals.

Use two policy tiers. Failure of any hard/binary criterion is `NOT_READY`; meeting hard but not all
preferred criteria is `CONDITIONALLY_READY`; meeting all criteria is only
`READY_FOR_MANUAL_CANARY_REVIEW`. Missing, stale, future, incompatible, or contradictory evidence
fails closed. UNKNOWN orders and unresolved critical incidents have zero tolerance.

The highest result still requires a person. `readiness-report-1` can record only false for real
orders, order network use, production Secret access, runtime/live/risk/model/deployment changes, and
always records `activation_performed=false`. The validator imports no exchange or HTTP transport and
does not load runtime settings or `.env`.

Thresholds are configurable but versioned and human-reviewed. Monetary canary limits use Decimal.
The defaults are conservative review gates, not claims of profitability or guaranteed safety.

## Consequences

- Current incomplete evidence produces the honest `NOT_READY` result without blocking ongoing paper
  research.
- Synthetic tests can prove classification logic but are not approval evidence.
- Phase 7's local unencrypted restore proof cannot pass production recovery readiness.
- A future operator may review a canary only after independent release/risk/model/operator records
  bind the exact code and artifacts; activation remains a separate, unimplemented operation.

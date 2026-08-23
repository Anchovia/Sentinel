# Live Readiness Evidence and Review

The Phase 9 validator is a read-only evidence classifier. It cannot activate live mode, change a
risk value, unlock an operator gate, promote a model, deploy code, access a credential, or call an
exchange endpoint. Its highest status is `READY_FOR_MANUAL_CANARY_REVIEW`, never permission to trade.

## Inputs

`readiness-evidence-1` binds every component to a UTC observation and SHA-256 source hash:

1. Paper calendar duration, trade count, and observed regimes; actual orders must be false.
2. Successful reconciliation days/runs, zero mismatches, zero UNKNOWN orders, and recent success.
3. Data availability, gaps, checksums, schema compatibility, and current event freshness.
4. Critical/high incident counts and normalized high-incident rate.
5. Model stability duration, calibration, drift, artifact hashes, and integrity.
6. Cost-inclusive drawdown and the lower bound of net expectancy, not a selected point estimate.
7. Cost-model sample size/error including fees, spread, slippage, latency, and adverse selection.
8. Reviewed, recent order-test dry-run evidence that created no real order. The validator never
   performs this call.
9. Recent production-grade encrypted off-host restore evidence with measured objectives. The Phase
   7 local proof does not satisfy this gate.
10. Recent security review, zero high/critical findings, Secret/dependency checks, auth/network/live
    gates, withdrawal permission disabled, and API-key IP policy reviewed.
11. Multi-operator runbook review and incident, cancel-only, reconciliation, and recovery drills.
12. Paper/order defaults closed, six-gate/single-flag tests, absent unlock, and separately reviewed
    live adapter and order-network allowlist. The validator itself has no order capability.
13. Distinct release/risk/model/operator approval records bound to exact code/model hashes and a
    small, time-bounded, manually monitored canary plan.

Missing, malformed, stale, future-dated, contradictory, or tampered evidence fails closed. Approval
IDs are evidence references, never credentials or runtime settings.

## Policy and results

`configs/readiness.default.yaml` contains reviewed hard and preferred thresholds. Falling below a
hard minimum produces `NOT_READY`. Passing every hard threshold but not every preferred threshold
produces `CONDITIONALLY_READY`. Only all preferred and binary safety gates produce
`READY_FOR_MANUAL_CANARY_REVIEW`.

The numbers are conservative governance defaults, not profitability, safety, capacity, or recovery
guarantees. Changing them requires human review and a consequential decision record; the validator
never changes them.

## Run

```text
uv run quantforge validate-live-readiness \
  --evidence <reviewed-evidence.json> \
  --policy configs/readiness.default.yaml \
  --output-root runtime_exports
```

For reproducible review, pass `--evaluated-at-utc <UTC ISO-8601>`. The atomic output is
`runtime_exports/readiness/latest.json` with evidence/policy hashes, all 13 gate results, mandatory
human approval, and false-only safety fields.

The current repository has no representative paper history, authenticated order-test, production
backup/restore, reviewed live adapter/network, or release approvals. Its truthful status is
`NOT_READY`.

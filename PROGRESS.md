# QuantForge Progress

## Current checkpoint

- Phase: 3 — Backtest and Paper Broker
- Status: `COMPLETE`
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; no live adapter or real order endpoint implemented
- Actual orders executed: no
- Secrets accessed: no
- Data schema version: raw-event-envelope-1 / trade-bar-1 / feature-snapshot-1 / paper-ledger-1
- Model schema version: not created

## Completed in Phase 3

- Added immutable paper execution policy, order, fill, update, fee, latency, time-in-force, and
  deterministic identifier contracts. Zero fees require an explicit research-only override;
  calibrated L2 requires calibration lineage.
- Implemented a public-data-only paper broker for market, best, limit, post-only, IOC, and FOK
  behavior. The default conservative model applies order/cancel latency, L2 depth haircuts, spread,
  slippage, adverse selection, partial/non-fill, passive queue uncertainty, and price priority.
- Added fail-closed stale-book and data-gap behavior. A gap cancels resting paper orders and no new
  order is accepted until a fresh book arrives. Trades during cancel latency may still fill.
- Added an independent append-only Decimal ledger with cash/position locks, duplicate-fill guards,
  FIFO lots, exact balance/PnL invariants, execution-cost attribution, and a verified hash chain.
- Added event-driven backtest orchestration over the Phase 2 virtual clock. Strategies only emit
  intents, risk separately approves amounts, and every run retains dataset/configuration/code/seed
  lineage.
- Added atomic JSON reports, naive-versus-conservative comparison, and frozen golden run, replay,
  ledger, PnL, and fill hashes.

## Validation evidence

```text
uv sync: PASS — Python 3.13.15, 78 locked packages
ruff: PASS — all checks passed
format check: PASS — 110 files formatted
mypy: PASS — 56 source files, no issues
pytest: PASS — 182 tests, 91.08% branch coverage
secret scan: PASS — 178 text files checked
dependency audit: PASS — no known vulnerabilities
compose validation: PASS — paper override renders successfully
golden paper comparison: PASS — naive filled 5, conservative filled 0.5
golden conservative PnL: PASS — net -0.540407575 with non-zero cost attribution
determinism: PASS — repeated run/replay/ledger/output hashes match exactly
accounting invariants: PASS — cash, position, FIFO, fees, PnL, equity, locks, hash chain
network/auth/order safety: PASS — paper broker imports no private transport and sends no request
container build: PASS — quantforge:phase3 image sha256:a645f0a1...85c0b
container safety smoke: PASS — paper, live=false, all 6 live gates failed closed
```

The keyless smoke artifacts remain under ignored local `data/phase1-smoke/raw`; no exchange Secret
was read, no private endpoint was called, and no order capability exists.

## Known constraints

- Local `uv` is not globally installed; validation used a project-isolated bootstrap environment.
- Docker Compose configuration and the application container were validated; the full PostgreSQL/Prometheus/Grafana stack was not left running.
- GitHub CLI is not installed, so PR creation automation is not configured.
- Documentation refresh is currently a reviewed manual operation rather than an automated semantic
  diff.
- Public collection is a bounded CLI path; a supervised long-running service is not configured yet.
- The bounded collector does not persist positive coverage windows automatically. Bar consumers
  must provide reviewed collector-health coverage; absent coverage safely becomes a data gap.
- Snapshot-derived order-flow imbalance is not individual order flow or queue position.
- Conservative queue position is an explicit approximation; public L2 depth decreases cannot
  identify cancellations versus fills. `calibrated_l2` remains unavailable without lineage.
- The Phase 3 ledger is single-market, long-only KRW spot. Multi-asset accounting and private
  balance reconciliation are intentionally deferred.
- Phase 3 fee values are simulation assumptions, not a claim about Upbit's current fee schedule.
- Remote `origin/main` has not been pushed; external publication requires explicit owner approval.

## Next milestone

Begin Phase 4 with versioned dataset/label/trial contracts, preregistered simple baselines,
time-based out-of-sample evaluation, calibration/uncertainty/abstention, and a model registry. Keep
the final holdout untouched and require conservative cost-adjusted reporting.

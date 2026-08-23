# QuantForge Progress

## Current checkpoint

- Phase: 5 — Strategy and Risk
- Status: `COMPLETE`
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; no live adapter or real order endpoint implemented
- Actual orders executed: no
- Secrets accessed: no
- Data schema version: raw-event-envelope-1 / trade-bar-1 / feature-snapshot-1 / paper-ledger-1 / research-dataset-1 / strategy-risk-1 / attribution-1
- Model schema version: model-artifact-1 / prediction-1

## Completed in Phase 5

- Added a causal shared strategy input containing market, feature, regime, alpha, execution,
  portfolio, and read-only risk snapshots, plus exact proposal contracts with validity,
  invalidation, exit, cost, confidence, uncertainty, strategy, and version lineage.
- Added transparent OFI/microprice momentum and liquidity-shock mean-reversion candidates. Strategy
  code has no exchange, execution, order-intent, or submission import and emits proposals only.
- Added a deterministic router with explicit ACTIVE/SHADOW/PAUSED/RESEARCH_ONLY/RETIRED states,
  edge/priority selection, correlation-group deduplication, loss limits, cooldowns, and capacity.
- Added deterministic KRW universe selection that fails closed on inactive/warning/stale,
  low-coverage, low-volume, wide-spread, or low-depth markets.
- Added the independent strategy-to-risk gateway and versioned hard-limit risk engine. Risk binds
  market/signal/edge/uncertainty snapshots, checks health/freshness/model release/depth/exposure/loss/
  drawdown/turnover/rates/identifiers, and uses exact conservative scaling without Kelly.
- Added a manual two-step, reconciliation-gated kill switch. Unapproved or liquidity-unsafe flatten
  activation is rejected and every transition forms an append-only SHA-256 chain.
- Added exact strategy/model/market/regime cost attribution with gross-to-net reconciliation and a
  separate SHA-256 chain, avoiding double subtraction from the actual portfolio ledger.

## Validation evidence

```text
uv sync: PASS — Python 3.13.15, 78 locked packages; no Phase 5 dependency added
ruff: PASS — all checks passed
format check: PASS — 138 files formatted
mypy: PASS — 75 source files, no issues
pytest: PASS — 220 tests, 88.50% branch coverage
secret scan: PASS — 210 text files checked
dependency audit: PASS — no known vulnerabilities
strategy isolation: PASS — no exchange/execution/OrderIntent capability under strategies
correlation router: PASS — strongest edge selected independent of iteration order; cooldown enforced
risk bypass: PASS — only gateway creates intent; hard rejection reaches broker boundary first
kill/daily-loss/stale-data: PASS — each independently rejects; release requires reconciliation
attribution: PASS — exact gross/cost/net arithmetic, aggregation, and chain verification
container build: PASS — quantforge:phase5 image sha256:e006c71f...a202c
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
- Phase 4 models and Phase 5 strategies were validated on synthetic fixtures only. They are not
  profitability evidence, promotion candidates, or live-ready strategies.
- The Gaussian mixture is diagonal and dependency-light; HMMs, richer boosting/survival models,
  drift monitoring, and advanced multiple-testing statistics remain unimplemented.
- Final-holdout protection is enforced by evaluator, vault, and trial-ledger contracts; durable
  operational access control will require the later database/audit service.
- Initial Phase 5 strategies are long-only entry proposals; systematic exit strategies and broader
  cross-sectional/maker-taker candidates remain unimplemented.
- The Phase 5 kill switch is an in-process state/audit contract. Runtime cancellation orchestration,
  durable storage, authentication, and operator controls are deferred to Phases 6 and 7.
- `configs/risk.paper.yaml` is illustrative paper policy only and cannot approve live trading.

## Next milestone

Begin Phase 6 by refreshing official Upbit private/execution documentation, then implement only
interfaces, mock transports, identifiers, persistent state/reconciliation contracts, and a disabled
live adapter. Do not use credentials, private endpoints, test-order endpoints, or real orders.

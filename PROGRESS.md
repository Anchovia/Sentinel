# QuantForge Progress

## Current checkpoint

- Phase: 6 — Private Exchange and Execution Safety
- Status: `COMPLETE`
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; no live adapter or real order endpoint implemented
- Actual orders executed: no
- Secrets accessed: no
- Data schema version: raw-event-envelope-1 / trade-bar-1 / feature-snapshot-1 / paper-ledger-1 / research-dataset-1 / strategy-risk-1 / attribution-1 / private-event-1 / execution-journal-1 / reconciliation-1
- Model schema version: model-artifact-1 / prediction-1

## Completed in Phase 6

- Re-fetched the official Upbit AI document index and reviewed authentication, REST best practice,
  rate limits, order chance/create/test/get/cancel, MyOrder, and MyAsset contracts. No authenticated
  endpoint or credential was used.
- Added ordered query-string/SHA-512 contracts and an opaque authorization interface, but no Secret
  provider, JWT signer, authenticated HTTP/WebSocket client, or network-capable private adapter.
- Added Decimal-preserving private MyOrder/MyAsset wire schemas, exchange-neutral domain mapping,
  source hashes, and pure private-subscription message construction.
- Added strict limit/price/market/best order shapes, IOC/FOK/post-only/SMP compatibility, dynamic
  order-chance preflight, fee/balance/tick/notional/expiry checks, and risk-decision binding.
- Added deterministic <=64-character identifiers and an append-only fsynced file journal that burns
  identifiers, verifies chronology/state transitions, and rejects sequence/hash/identity damage.
- Added fake/disabled private ports, a fake-only order-test adapter, idempotent submission coordinator,
  and identifier lookup after timeout/restart. Unknown outcomes never retry create.
- Added read-only remote order and exact balance reconciliation. Unknown/missing/state/balance
  mismatch evidence sets `safe_to_resume=false`.
- Added a disabled live adapter that has no network capability and still raises after all six live
  configuration gates pass.

## Validation evidence

```text
uv sync: PASS — Python 3.13.15, 78 locked packages; no Phase 6 dependency added
ruff: PASS — all checks passed
format check: PASS — 154 files formatted
mypy: PASS — 87 source files, no issues
pytest: PASS — 237 tests, 87.20% branch coverage
secret scan: PASS — 228 text files checked
dependency audit: PASS — no known vulnerabilities
official capability refresh: PASS — read-only source review recorded at 2026-08-23T12:23:09.117Z
private schemas: PASS — MyOrder/MyAsset fixtures preserve Decimal and reject malformed input
journal persistence: PASS — reopen/state/hash identity verified; tampering rejected
idempotency: PASS — repeated successful submit makes one fake create call
timeout/restart: PASS — identifier lookup only; unresolved outcome stays UNKNOWN; create not retried
reconciliation: PASS — exact balance mismatch and unsafe resume verified
network isolation: PASS — private/auth/coordinator/live modules contain no network client import
disabled live: PASS — raises after all six gates; image reports live_network_capability=false
container build: PASS — quantforge:phase6 image sha256:55d48899...8e105
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
- Phase 6 has no credential source, JWT signer, authenticated transport, private-stream supervisor,
  REST parser for real responses, or real/test-order endpoint access. Only fixtures and fakes run.
- The execution journal is a single-writer fsynced file proof. Transactional database persistence,
  process locking, backups, and private-stream recovery are not implemented yet.
- Dynamic order chance, fees, ticks, and minimums are fixture contracts in Phase 6, not current live
  account values. The capability snapshot must be refreshed again before any exchange behavior change.
- Cancellation is represented by the port/state contracts, but authenticated cancellation and
  operator controls remain absent. The live adapter cannot submit or cancel under any settings.

## Next milestone

Begin Phase 7 with an authenticated, read-oriented operations/dashboard surface over redacted local
runtime exports, incidents, journal/reconciliation status, audit logs, backup/restore evidence, and
confirmed emergency-control contracts. Do not add an authenticated exchange transport or enable
live trading.

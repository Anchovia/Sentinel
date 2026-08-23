# Known Limitations

## Current implementation status

- A keyless Upbit public WebSocket adapter, append-only Parquet raw store, deterministic replay,
  time bars, and baseline feature pipeline exist. No private adapter, trained model, strategy, risk
  calculation engine, paper broker, ledger, or dashboard exists yet.
- The API exposes health, non-secret safety status, and process metrics. Public collection currently
  runs as a bounded CLI process rather than a supervised long-running Compose service.
- No live adapter or real-order endpoint exists.

## Tooling and deployment

- Local uv was not preinstalled at project start; validation used a project-isolated bootstrap.
- Docker build, application smoke, and Compose rendering passed; the full infrastructure stack has not yet had a sustained health/backup test.
- Container images are pinned to verified manifest digests, but routine digest refresh and SBOM policy are not yet automated.
- Committed PostgreSQL/Grafana credentials are development-only examples.
- GitHub CLI is unavailable; automated PR creation is not configured.
- The repository currently uses a restrictive all-rights-reserved placeholder license pending an owner-selected license.

## Market and research

- Public Upbit capabilities, SDK support, request limits, and stream schemas were snapshotted on
  2026-08-23. There is not yet an automated semantic documentation-diff job; every behavior change
  still requires a fresh official-source review.
- The official Python SDK `0.9.0` was not installed because its declared `websockets <16` constraint
  conflicts with the reviewed transport version. ADR-005 records the isolated direct-transport
  decision.
- The bounded collector does not yet persist continuous `CoverageWindow` records automatically.
  Bar construction therefore requires separately reviewed positive coverage input and safely emits
  data gaps when it is absent.
- Phase 2 implements 1s/5s/15s/1m bars. Longer timeframes and event/volume/imbalance bars remain
  pending.
- Public L2 data does not reveal exact queue position or individual order events. Snapshot-derived
  order-flow imbalance and future fill simulations remain approximations.
- Baseline features are not trading signals and have no profitability claim.
- No strategy/model profitability, capacity, latency, recovery objective, or live readiness is claimed.

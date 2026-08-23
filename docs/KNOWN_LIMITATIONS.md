# Known Limitations

## Foundation status
- No public/private Upbit adapter, event store, replay engine, feature pipeline, model, strategy, risk calculation engine, paper broker, ledger, or dashboard exists yet.
- The current API exposes only health and non-secret safety status.
- No live adapter or real-order endpoint exists.

## Tooling and deployment

- Local uv was not preinstalled at project start; validation used a project-isolated bootstrap.
- Docker build, application smoke, and Compose rendering passed; the full infrastructure stack has not yet had a sustained health/backup test.
- Container images are pinned to verified manifest digests, but routine digest refresh and SBOM policy are not yet automated.
- Committed PostgreSQL/Grafana credentials are development-only examples.
- GitHub CLI is unavailable; automated PR creation is not configured.
- The repository currently uses a restrictive all-rights-reserved placeholder license pending an owner-selected license.

## Market and research

- Upbit capabilities, SDK support, request limits, order policies, and stream schemas have not been snapshotted yet; official documentation synchronization is Phase 1.
- Public L2 data will not reveal exact queue position or individual order events; future fill simulations remain approximations.
- No strategy/model profitability, capacity, latency, recovery objective, or live readiness is claimed.

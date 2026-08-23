# QuantForge Progress

## Current checkpoint

- Phase: 7 — Dashboard and Operations
- Status: `COMPLETE`
- Branch: `main` (explicitly requested by repository owner)
- Trading mode: `paper`
- Live submission: blocked; the live adapter has no network capability
- Actual orders executed: no
- Private/authenticated Upbit calls: no
- Production Secrets accessed: no
- Runtime schema: `operations-dashboard-1` / `operations-backup-1`
- Next phase: 8 — Work/Codex Automation Support (`IN_PROGRESS`)

## Completed in Phase 7

- Added fixed, Decimal-preserving Overview, Markets, Positions, Orders, Strategies, Models, System,
  and Incidents read models plus an atomic operations export. The export rejects credential field
  names, bearer/JWT-shaped text, and full account UUIDs before writing.
- Added `export-operations`; it reports paper mode, no authentication/network use, and no order
  submission capability.
- Added fail-closed dashboard authentication using a separately supplied strong bearer token and
  server-side CSRF Secret. Unconfigured operations endpoints return 503; state-changing requests
  also require a short-lived actor-bound CSRF proof.
- Added authenticated dashboard, incident, and audit JSON APIs plus a dependency-free
  server-rendered read-only dashboard. Added Prometheus operations metrics and a provisioned Grafana
  `QuantForge Health` dashboard.
- Added fsynced hash-chain incident, audit, and emergency-control journals. Audit records contain
  hashed actor/idempotency references rather than credentials or confirmation material.
- Added exact confirmation phrases, idempotency binding, request-before-effect persistence, result
  verification, and interrupted-request `UNKNOWN` recovery. Duplicate requests are not re-executed.
- Local `cancel_only` activation and incident acknowledgement are verified. Strategy pause is only a
  recorded proposal; cancel-all is blocked because authenticated cancellation transport is absent.
- Added explicit-source local backup manifests, per-object/aggregate SHA-256 verification, Secret/
  symlink/path traversal checks, empty-target paper restore drills, and safe CLI commands. Local
  manifests explicitly report external encryption false and recovery objectives unmeasured.
- Added ADR-011 and updated architecture, data, risk, security, operations, recovery, and handoff
  documentation. The public README remained unchanged and minimal.

## Validation evidence

```text
Python: PASS — 3.13.15; no Phase 7 dependency added
ruff: PASS — all checks passed
format check: PASS — 169 files formatted
mypy: PASS — 98 source files, no issues
pytest: PASS — 254 tests, 87.17% branch coverage
secret scan: PASS — 244 text files checked
dependency audit: PASS — no known vulnerabilities
Compose config: PASS — base + paper overlays
operations API: PASS — 503/401 fail-closed auth, CSRF rejection, authenticated read views
control safety: PASS — confirmation, idempotency, audit, blocked transport, interrupted UNKNOWN
runtime export: PASS — atomic round trip and Secret/account-UUID rejection
backup/restore: PASS — checksum round trip, paper marker, Secret and tamper rejection
container build: PASS — quantforge:phase7 sha256:c52ccccf...5ae6a
container safety: PASS — paper, live=false, all six gates failed closed
container operations: PASS — auth default false; control/live network capability false
container export: PASS — operations-dashboard-1, network/order/authentication use false
```

## Known constraints

- The dashboard is an initial internal server-rendered view. It has one bearer-authenticated operator
  role, no user database/RBAC/SSO, no hardened TLS reverse proxy, and no application rate limiter.
- Dashboard Secrets must be delivered externally. The Docker development stack does not configure
  them by default, so operations endpoints remain closed.
- Incident, audit, and control persistence is a single-writer fsynced file proof without database
  transactions, process locking, retention, or multi-host replication.
- The operations snapshot supports every major screen but remains empty/default until runtime
  producers populate markets, positions, models, strategy, reconciliation, and backup health.
- The local backup proof is unencrypted and not off-host. It does not back up/restore PostgreSQL,
  credentials, full raw ticks, or Grafana's runtime database; RPO/RTO targets are not measured.
- Cancel-all has no executor, strategy pause does not mutate runtime state, and there is deliberately
  no kill-switch release, flatten, risk/model edit, live activation, or order endpoint.
- The Grafana and PostgreSQL credentials in Compose are localhost development defaults, not
  production credentials. Production ingress, Secret delivery, and database security are absent.
- Phase 6 still has no credential provider, JWT signer, authenticated HTTP/WebSocket client, private
  stream supervisor, or real/test-order endpoint access. No private exchange network path exists.
- Research models and strategies remain synthetic-fixture baselines, not profitability evidence or
  promotion candidates. The conservative public-L2 fill model remains uncalibrated.
- No Work/Codex skills or schedules have been registered. Scheduled jobs remain forbidden until
  Phase 8 schemas, allowlists, manual dry runs, and worktree/no-op proofs pass.

## Next milestone

Implement Phase 8 repository-local Work/Codex skills, automation prompt files, report/trigger
schemas, strict write allowlists, dedicated-worktree instructions, and manual no-op dry runs. Work
must remain report-only; Codex may create PR candidates only in scheduled dedicated worktrees. Do not
register schedules until exports and every manual trial pass, and never auto-merge, deploy, promote,
change risk, access Secrets, or call an order path.

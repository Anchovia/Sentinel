# Known Limitations

## Trading and exchange boundary

- Default mode is paper. There is no credential provider, JWT signer, authenticated exchange
  transport, real/test order call, real cancellation, or usable live adapter.
- Private order/asset and order-policy behavior is fixture/fake-port evidence only. Public WebSocket
  collection now has a supervised burn-in service, but its sustained uptime/retention evidence has
  not yet accumulated.
- Upbit capability observations were reviewed on 2026-08-23 and are not an automatic semantic diff.
  The official Python SDK remains excluded because its declared WebSocket constraint conflicts with
  the reviewed direct transport.
- Public L2 snapshots cannot reveal exact queue position or hidden liquidity. Paper fills, slippage,
  and adverse-selection estimates are conservative approximations and remain uncalibrated.

## Research and readiness

- Baselines and positive readiness fixtures use synthetic/fixture-scale evidence. The implemented
  validator truthfully returns `NOT_READY`; no strategy/model profitability, capacity, production
  latency, promotion, canary eligibility, or live readiness is claimed.
- Continuous coverage records, longer/event/volume/imbalance bars, full production feature/model
  families, sustained paper history, and representative performance/model exports are incomplete.
- The supervised public burn-in writes raw events and operations health only. Real-time feature,
  model, strategy, risk, paper-broker, ledger, and performance orchestration remains incomplete.
- Final-holdout controls and experiment retention exist, but they do not remove selection bias,
  multiple testing, regime change, or limited sample risk.
- Readiness policy thresholds are configurable governance defaults, not guarantees. The validator
  does not collect evidence or provide any activation/order mechanism.

## Operations and recovery

- The dashboard has one bearer-authenticated operator role and no RBAC/SSO/TLS ingress/application
  rate limiter. Runtime producers do not yet populate every read view.
- The existing server-rendered dashboard and Grafana views are developer/operations skeletons, not a
  polished Korean end-user GUI.
- Incident, control, order, experiment, risk, and attribution journals are local single-writer proofs,
  not transactional replicated production storage.
- Backups are unencrypted, local development restore proofs with no PostgreSQL/off-host/raw-tick/
  credential recovery and no measured RPO/RTO. Production recovery is unimplemented.
- Cancel-only and incident acknowledgement are local. Strategy pause is proposal-only, and
  cancel-all is blocked because no authenticated cancellation transport exists.

## Automation and delivery

- Repository skills, prompts, schemas, allowlists, and an RRULE catalog exist, but no Work/Codex
  scheduled task is registered. Missing representative exports should return `BLOCKED`.
- The write allowlist and validator are repository controls, not operating-system path ACLs. Work
  requires before/after Git evidence; every Codex candidate still needs human diff/PR review.
- Only a detached no-op background worktree was exercised. No automated branch, PR, merge, deploy,
  model promotion, risk change, live activation, or order path exists.
- Local-file schedules require the computer and desktop app to remain running. The catalog does not
  claim account-specific task capacity or next-run calculations.
- Docker/Compose validation passes, but the full stack has no sustained production health or backup
  test. Development credentials and the restrictive placeholder license are not production choices.

# Known Limitations

## Trading and exchange boundary

- Default mode is paper. There is no credential provider, JWT signer, authenticated exchange
  transport, real/test order call, real cancellation, or usable live adapter.
- Private order/asset and order-policy behavior is fixture/fake-port evidence only. Public WebSocket
  collection now has a supervised burn-in service, but its sustained uptime/retention evidence has
  not yet accumulated.
- Upbit capability observations were reviewed on 2026-08-24 and are not an automatic semantic diff.
  The official Python SDK remains excluded because its declared WebSocket constraint conflicts with
  the reviewed direct transport.
- The live Korean ticker feed returned `PREDELISTING` for three scheduled-removal pairs although the
  reviewed ticker page did not enumerate that state. It is accepted only as non-active public data
  and can never enter the focused universe; future undocumented states still fail schema validation.
- Public L2 snapshots cannot reveal exact queue position or hidden liquidity. Paper fills, slippage,
  and adverse-selection estimates are conservative approximations and remain uncalibrated.

## Research and readiness

- Baselines and positive readiness fixtures use synthetic/fixture-scale evidence. The implemented
  validator truthfully returns `NOT_READY`; no strategy/model profitability, capacity, production
  latency, promotion, canary eligibility, or live readiness is claimed.
- Continuous coverage records, longer/event/volume/imbalance bars, full production feature/model
  families, sustained paper history, and representative performance/model exports are incomplete.
- The supervised public burn-in now calculates causal incremental features and publishes processing
  latency and runs the always-neutral inference/strategy/risk/paper-broker/ledger composition, but no
  alpha artifact has human paper approval. Every deployed real-time decision therefore remains
  `HOLD`, with zero strategy proposal, risk approval, simulated order, and fill.
- A separate paper-order simulation gate defaults closed. Model approval alone cannot enable even
  simulated orders, and no runtime activation interface is provided.
- Phase 11.1 latency measures event validation and feature calculation only. It excludes future
  inference, strategy, risk, simulated execution, ledger, network, and exchange latency and is not a
  profitability, fill-speed, capacity, or high-frequency-trading claim. Python on a retail Upbit
  connection is not a colocated HFT system.
- All-KRW mode monitors every current KRW ticker but reserves trade and five-level orderbook streams
  for 20 rotating candidates. It is not full-depth capture for all pairs, and the activity/move
  ranking is a data-allocation policy rather than validated alpha.
- The approved alpha used by the end-to-end paper fill test is a deterministic fixture, not a
  registered research result, profitability claim, or deployable artifact. No production alpha,
  automated approval, exit controller, round-trip lifecycle, sustained paper performance, or
  representative performance export exists yet.
- Final-holdout controls and experiment retention exist, but they do not remove selection bias,
  multiple testing, regime change, or limited sample risk.
- Readiness policy thresholds are configurable governance defaults, not guarantees. The validator
  does not collect evidence or provide any activation/order mechanism.

## Operations and recovery

- The dashboard has one bearer-authenticated operator role and no RBAC/SSO/TLS ingress/application
  rate limiter. Runtime producers do not yet populate every read view.
- The Korean local monitor covers public feed/storage, universe coverage, and neutral paper counters.
  The authenticated server-rendered dashboard and Grafana views are still developer/operations
  skeletons; representative strategy, position, and paper-performance views do not exist.
- Incident, control, order, experiment, risk, and attribution journals are local single-writer proofs,
  not transactional replicated production storage.
- Backups are unencrypted, local development restore proofs with no PostgreSQL/off-host/raw-tick/
  credential recovery and no measured RPO/RTO. Production recovery is unimplemented.
- Cancel-only and incident acknowledgement are local. Strategy pause is proposal-only, and
  cancel-all is blocked because no authenticated cancellation transport exists.
- Paper broker, reservation, fill, lot, and portfolio state now have verified clean-restart recovery.
  An economically active unclean restart cancels open paper orders and releases locks but permanently
  blocks new simulation pending a separately reviewed operator acknowledgement workflow, which is
  not yet implemented. The interrupted session cannot be used as performance evidence. Only a
  disabled, provably empty economic state may clear an unclean marker automatically.
- Recovery checkpoints rewrite the complete local ledger on consequential state changes. This is
  bounded by paper trade count rather than public event count but has not been load-tested for long
  simulated histories or compacted into production storage.
- Raw paper data now has ZSTD compaction, 30-day retention, a 50GiB active-data cap, and a 20GiB
  free-space stop. The cap may shorten the effective time window during high activity, retirement
  tombstones add small uncapped metadata, and the first migration compaction is not long-duration
  capacity evidence.
- `D:/Sentinel-Data` and the preserved Docker named volume are on the same computer. Neither is an
  encrypted off-host backup; drive failure, local deletion, ransomware, or host loss can remove both.
  Pruned payloads are intentionally unrecoverable without a separate backup.
- Compaction runs outside the event hot path but can temporarily use material CPU and memory. Replay
  or other storage readers are not coordinated by a cross-process lock and should not run during a
  maintenance window.

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

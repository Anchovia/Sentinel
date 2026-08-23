# ADR-019: Tiered All-KRW Paper Universe

- Status: accepted
- Date: 2026-08-24
- Scope: credential-free public paper runtime only

## Context

The supervised runtime observed only `KRW-BTC`, while the intended short-horizon research scope is
every currently listed Upbit KRW pair. Subscribing every pair to full ticker, trade, and 30-level
orderbook streams would spend storage and CPU on illiquid or warned markets and make the compact
operator view unusable. A static repository list would also become stale when Upbit lists, warns,
or removes a pair.

## Decision

At every `ALL-KRW` paper-runtime start, fetch the unauthenticated official pair catalog with details
and the KRW quote ticker snapshot. Fail startup if either public response is unavailable, oversized,
malformed, non-KRW-empty, or schema-invalid. Never fall back to an old hard-coded universe.

Use two processing tiers on one public WebSocket connection:

1. Subscribe every current KRW pair to ticker data for broad, event-driven monitoring.
2. Subscribe only 20 focused pairs to trade data and five-level orderbook data.

Official warning pairs remain monitored but cannot enter the focused set. Suspended, inactive,
stale, or sub-KRW-1-billion 24-hour-turnover pairs are also ineligible for focus. Rank eligible
pairs from the latest 60-second ticker window by deterministic `activity × (absolute move + 1)`
score, then 24-hour KRW turnover and market code. Re-evaluate on the existing heartbeat, but allow
at most one focus replacement per 60 seconds. A replacement sends one validated subscription
message through the existing per-connection limiter.

The full market-set hash namespaces paper recovery state. A listing-set change starts a separate
checkpoint instead of restoring accounting state created for another universe. Broad events enter
the immutable raw stream and incremental feature path; neutral inference/strategy/risk/paper
composition runs only for the focused set. Focus rotation is disabled if the independent paper-order
simulation gate is ever enabled.

## Consequences

- All current KRW-listed assets are observable without API keys or polling every asset.
- Dense microstructure cost scales with 20 focused markets rather than all pairs.
- The exact focused set changes with public activity and is exported as
  `realtime-universe-1`; research must bind this evidence.
- Storage grows materially faster than the former single-pair runtime and requires measured
  compaction, retention, and disk-watermark work. The first short sample projects an activity-
  dependent planning range of roughly 20–70GB per 30 days before those controls.
- BTC- and USDT-quoted pairs are outside this decision. Adding them would require separately
  reviewed quote-currency accounting, conversion, liquidity, risk, and execution contracts.
- This decision adds no credentials, private endpoint, model approval, paper-order permission, or
  real-order capability.

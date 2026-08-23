# ADR-017: Neutral-by-Default Real-Time Paper Composition

- Status: accepted
- Date: 2026-08-24

## Context

The low-latency feature path had no model, strategy, risk, broker, or accounting composition. Those
existing offline components need an event-driven connection before paper candidates can be studied,
but composing them must not silently approve a model or create an order-capable live path.

## Decision

Run a deterministic always-neutral alpha baseline on every ready feature frame. It emits `ABSTAIN`
with `NO_APPROVED_ALPHA_MODEL`, so proposal-only strategies cannot create an intent. Still construct
versioned regime, execution-cost, market, portfolio, and risk inputs so the complete downstream data
contract and latency are continuously exercised.

Permit an actionable alpha model only when an injected artifact exactly matches a separate human
paper approval by model version, SHA-256, market scope, approval time, validity window, and `PAPER`
status. Even then, require a second disabled-by-default paper-order simulation gate before creating
an intent. No approval, enabled gate, or actionable artifact is checked into or loaded by the
supervised runtime. A test-only fixture crosses the strategy router, independent risk engine,
conservative paper broker, cash reservation, simulated fill, and verified Decimal ledger.

Keep all authenticated, private-network, real-order, and live capabilities false. Publish only an
atomic Secret-free decision snapshot. Use a read-only portfolio valuation in the hot path; append
only consequential intent, risk, order, fill, fee, attribution, lock, and release records.

## Consequences

- The deployed service measures real inference and routing overhead without pretending an alpha is
  approved or profitable.
- Model approval cannot be inferred from configuration presence, strategy status, or code execution.
- Model approval and paper-order simulation permission are independent fail-closed controls.
- The broker and ledger integration is regression-tested before any paper candidate is reviewed.
- Broker and ledger state remain process-local; the simulation gate stays closed until deterministic
  restart recovery is implemented and tested.
- There are no simulated trades or paper performance results until a preregistered challenger and
  complete exit lifecycle receive separate human review.
- The Python retail path remains an event-driven paper research system, not a colocated HFT system.

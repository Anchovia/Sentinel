# ADR-003: Six independent live gates

- Status: Accepted
- Date: 2026-08-23

## Context

A single environment flag, CLI confirmation, or UI control is too easy to misconfigure. Research, tests, scheduled work, and paper processes must be unable to submit a real order through accidental configuration drift.

## Decision

Require trading mode, submission permission, release manifest, risk policy approval, model release approval, and operator unlock simultaneously. Evaluate them at the execution boundary and fail closed. A future live adapter additionally requires explicit dependency injection, external credentials, preflight, current reconciliation, and network policy.

Foundation settings make all gates false and provide no live adapter.

## Consequences

- More operational steps before a manual canary.
- Clear, testable failure evidence for each gate.
- No component, model, scheduled task, or single operator action can enable live submission alone.

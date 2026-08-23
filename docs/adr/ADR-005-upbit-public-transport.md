# ADR-005: Isolate the Phase 1 Upbit Public Transport

- Status: Accepted
- Date: 2026-08-23

## Context

Upbit publishes an official Python SDK. The verified `0.9.0` package supports Python 3.13 but
declares `websockets >=13,<16`; QuantForge already resolves `websockets 17`. Phase 1 requires only
the unauthenticated public WebSocket endpoint and must preserve raw messages for replay and schema
change analysis.

## Decision

Implement a minimal, keyless `websockets 17` transport behind QuantForge-owned protocols. Keep the
wire models in the Upbit adapter, map them into versioned domain envelopes, and store the exact raw
text and SHA-256 digest. Do not install or fork the official SDK to bypass its declared constraints.

The capability snapshot records the official SDK version and constraint. Every later Upbit phase
must re-fetch official documentation and package metadata and reconsider this decision.

## Consequences

- No exchange transport type leaks into the domain.
- The public collector has no credential or order-submission path.
- QuantForge owns reconnect, heartbeat, malformed-message isolation, and message throttling tests.
- SDK adoption remains possible after a compatible official release, without changing domain or
  storage contracts.

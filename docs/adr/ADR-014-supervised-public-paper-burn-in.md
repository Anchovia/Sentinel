# ADR-014: Supervise public paper burn-in before strategy execution

- Status: Accepted
- Date: 2026-08-24

## Context

The finite Phase 1 collector proved the public Upbit trust boundary but could not accumulate
sustained operational evidence. Starting strategy, risk, broker, and ledger orchestration before the
public feed and storage path have survived a representative burn-in would mix data-plane failures
with trading-logic failures and weaken attribution.

The current official Upbit documentation still identifies the unauthenticated public WebSocket,
120-second idle timeout, ping/pong connection maintenance, reconnection, and connection/message rate
limits. It also keeps private asset/order streams on an authenticated private endpoint. QuantForge
must preserve that separation.

## Decision

Add a dedicated supervised public burn-in runtime before real-time simulated execution:

- accept only uppercase KRW markets and public ticker, trade, and orderbook subscriptions;
- refuse production mode, any configured Upbit credential, any non-paper trading mode, or even a
  partially opened set of the six live gates;
- reuse the reviewed TLS WebSocket, ping/pong, throttling, and bounded exponential reconnect policy;
- atomically persist immutable raw Parquet files, manifests, lifecycle heartbeats, and a redacted
  operations snapshot;
- periodically flush buffered rows and persist parser/reconnect/duplicate/latency evidence;
- support duration/message bounds and graceful cancellation without an order, private, or
  authentication port;
- run as a separate read-only-container service with only data and runtime-export write mounts.

The Phase 10 runtime is an observation and storage burn-in. It does not yet generate strategy
signals, simulated orders, fills, portfolio PnL, model evidence, or profitability claims. Those enter
only after this path is stable and receive their own validation milestone.

## Consequences

Repeated runs can build continuous, checksummed public evidence and expose fresh health data to the
existing operations plane. A clean 30-message smoke is useful transport evidence but not sustained
paper history or readiness evidence. The full user-facing Korean GUI remains separate from the
existing developer/operations dashboard skeleton.

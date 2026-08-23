# ADR-015: Generate a local read-only public-data monitor

- Status: Accepted
- Date: 2026-08-24

## Context

The supervised public collector persists raw events inside a Docker volume and writes Secret-free
JSON heartbeats to the host. Those files are auditable but do not give a non-technical operator a
clear view of whether data is arriving and accumulating. Starting the authenticated operations API,
Grafana, and their credentials solely to inspect a keyless public feed adds unnecessary moving parts.

The paper runtime still has no strategy, model, risk, broker, ledger, account, private endpoint, or
order capability. A monitor must not imply that these later systems exist or weaken the authenticated
operations/control boundary.

## Decision

Generate `runtime_exports/ops/paper-monitor.html` atomically with every runtime heartbeat:

- make the HTML self-contained and reload it every five seconds so it opens directly from disk;
- show only public-market observations, collection freshness/health, error/reconnect/duplicate
  counts, remaining disk, and current-run plus retained storage totals;
- reconstruct retained row/file/byte totals from validated immutable manifests on every runtime
  start and increase them only after a successful commit;
- fail startup on malformed, duplicate, escaping, missing, or size-damaged retained files rather
  than displaying an untrusted accumulation total;
- exclude raw payloads/paths, policy hashes, run identifiers, credentials, account data, controls,
  positions, orders, and any action that could affect trading;
- preserve bearer/CSRF protection and fail-closed behavior for the separate operations dashboard.

The additive retained fields create `paper-runtime-2`; the reader accepts version 1 with zero-valued
retained defaults only for transition compatibility. New writers always emit version 2.

## Consequences

The owner can inspect live public collection without an API key, web server, or terminal. Persistent
volume growth remains visible across supervised restarts without exposing the raw dataset. The file
is local evidence, not a production monitoring, availability, profitability, or trading claim.

The monitor intentionally has no strategy, risk, simulated-order, portfolio, or performance panel.
Those views may be added only after Phase 11 produces stable, versioned, representative exports.

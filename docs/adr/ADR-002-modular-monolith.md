# ADR-002: Modular monolith first

- Status: Accepted
- Date: 2026-08-23

## Context

The target system has many logical domains, but premature service boundaries add distributed failure modes, duplicated schemas, network latency, and operational burden before throughput and isolation needs are measured.

## Decision

Build one Python package with strict domain interfaces and separable entry points. PostgreSQL, Prometheus, and Grafana are external infrastructure. Add Redis/NATS, separate deployable services, MinIO, MLflow, or Rust only after profiling or security/fault-isolation evidence and an ADR.

## Consequences

- Faster invariant development and deterministic replay sharing.
- Logical boundaries must be enforced by imports/interfaces and tests rather than network boundaries.
- Later separation remains possible because exchange/transport/storage implementations stay behind domain interfaces.

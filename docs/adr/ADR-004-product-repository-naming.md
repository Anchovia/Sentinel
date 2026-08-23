# ADR-004: Sentinel repository, QuantForge product

- Status: Accepted
- Date: 2026-08-23

## Context

The GitHub repository was created as `Anchovia/Sentinel`, while the supplied product specification consistently names the platform QuantForge.

## Decision

Keep the existing repository and local folder name `Sentinel`. Name the product, Python distribution, import package, services, metrics, and user-facing documentation `QuantForge` / `quantforge`.

## Consequences

- Existing Git remote links remain stable.
- Documentation must state the distinction to avoid package/repository confusion.
- A future repository rename is an owner action and does not require a Python package rename.

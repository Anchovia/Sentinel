# ADR-001: Python 3.13.15 with uv

- Status: Accepted
- Date: 2026-08-23

## Context

Python 3.14.7 is the current stable feature release, while Python 3.13.15 is the immediately previous maintained release. QuantForge depends on numerical, ML, database, WebSocket, and operations libraries where compiled-wheel and tooling maturity matter more than using the newest language feature.

The project host also has a Python 3.13 installation registered, while Codex's bundled fallback is Python 3.12.13. The master contract permits using one stable version behind when compatibility justifies it.

## Decision

Target Python 3.13.15 and declare `>=3.13,<3.15`. Use uv 0.12.5 for Python acquisition, environments, locking, and command execution. Commit `.python-version` and `uv.lock`; use the same Python line in CI and containers.

## Consequences

- Better probability of complete binary-wheel support than Python 3.14 across the full future ML stack.
- Python 3.14-specific features are unavailable.
- Upgrading to 3.14 requires a compatibility matrix, full replay/accounting tests, performance comparison, and a superseding ADR.

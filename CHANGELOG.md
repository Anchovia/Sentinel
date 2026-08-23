# Changelog

All notable changes are recorded here. The project follows semantic versioning once a public API is declared stable.

## [Unreleased]

### Added

- Phase 0 product, architecture, risk, research, data, security, threat, runbook, and recovery contracts.
- Python 3.13 uv project and developer/CI/container skeleton.
- Fail-closed typed settings and six-gate live submission guard.
- Decimal monetary boundary, initial order intent/state machine, risk decision contract, Secret redaction, CLI, health/safety API, and unit tests.

### Security

- Paper mode and all live approvals default to disabled.
- No live exchange adapter or real order endpoint exists.
- Repository-local Secret guard and structured redaction added.
- Updated pytest from the vulnerable 8.4.2 resolution to 9.1.1 after `PYSEC-2026-1845`; the repeated audit reported no known vulnerabilities.
- Pinned container images and CI actions to immutable digests/commits.

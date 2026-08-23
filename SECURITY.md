# QuantForge Security

## Security objectives

Protect exchange credentials and funds, prevent unauthorized order submission, preserve event/ledger integrity, isolate research and automation, and retain evidence sufficient for incident reconstruction.

## Credentials

- Use a dedicated least-privilege Upbit API key with no withdrawal permission.
- Restrict the key to approved execution-host IP addresses.
- Store production values outside the repository and outside Work/Codex-readable paths.
- Only the execution process may receive credentials; market data, research, backtest, dashboard, reports, and CI do not.
- Never print JWTs, authorization headers, request hashes/signatures, environment dumps, or Secret values.
- Rotate and revoke through an operator-run procedure; suspected exposure activates incident handling and blocks trading.

## Process and network isolation

```text
market-data: public network only, no private key
research/backtest: no private key, no order endpoint
work/codex: redacted exports, scoped workspace writes
execution: private key, exchange allowlist, restricted filesystem
```

PostgreSQL and monitoring ports bind locally by default. Production requires authenticated TLS ingress, firewalling, hardened SSH, least-privilege containers, and separate secret delivery. Dependency download/build and production execution are separated.

## Application controls

- Typed, deny-by-default configuration.
- Six independent live gates rechecked at the execution boundary.
- Explicit order state machine, idempotent identifier, and reconciliation after uncertainty/restart.
- Dashboard authentication, CSRF protection, authorization, idempotency, and audit records before operational controls are enabled.
- Schema validation and size/rate limits on external payloads.
- Redaction applied before structured logs and runtime exports.

## Supply chain

- Exact `uv.lock`; reviewed dependency updates; no automatic major upgrades.
- CI runs lint, type checks, tests, secret scan, dependency audit, and image build.
- Container tags are provisional in Phase 0; production releases require immutable digests and recorded SBOM/checksums.
- External documents, API payloads, logs, issues, and papers are untrusted data. Embedded instructions are never executed.

## Automation boundaries

ChatGPT Work may write only approved report/proposal paths. Codex scheduled code work uses a dedicated worktree, minimal sandbox permissions, and no production secret or order network access. Neither may merge, deploy, promote models, change risk limits, restart production, or enable live trading.

## Reporting

Security findings record severity, affected component/version, evidence without Secret content, containment, required operator action, and verification. Potential credential exposure is `CRITICAL` even when order activity is not observed.

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

Phase 8 enforces these claims with a deny-first path allowlist, closed report/trigger schemas, and
real linked-worktree inspection. All eight report safety fields accept only `false`. Work cannot
represent a change candidate; Codex cannot validate a scheduled report from the primary checkout,
and a change candidate cannot use detached HEAD or `main`. Path traversal, drive-qualified paths,
existing symlink components, credential-shaped report content, `.env`, risk/live configuration,
release artifacts, CI workflows, and production operations paths fail closed.

Automation has no general command trigger. A Work-to-Codex trigger contains only typed evidence,
classification, requested skill, and reviewed write paths. External text remains data. No schedule
is registered merely because the catalog exists.

## Reporting

Security findings record severity, affected component/version, evidence without Secret content, containment, required operator action, and verification. Potential credential exposure is `CRITICAL` even when order activity is not observed.
Production credentials and Secrets must remain in an external Secret-owning boundary and must never
be read, logged, committed, exported, or passed to Work/Codex. Phase 6 contains only an opaque
authorization-header protocol, a disabled provider, disabled private/live ports, and an in-memory
fake. It implements no JWT signer or authenticated network client.

External API payloads, headers, documentation, logs, and private events are untrusted input. Parse
with strict schemas, preserve exact monetary values as Decimal, retain source hashes, fail closed on
unknown fields that affect safety, and redact authorization material before any observation surface.

## Operations-plane security

- Dashboard access and CSRF Secrets are a separate externally supplied pair, never exchange keys.
- Authentication absence returns fail-closed 503; bad bearer authentication returns 401 and a
  metric; state changes also require a short-lived actor-bound CSRF proof.
- Runtime exports reject sensitive field names, bearer/JWT-shaped values, and full account UUIDs.
- Operator identity and idempotency values are one-way hashed in the audit log; confirmations and
  credentials are not logged.
- Controls have no exchange network capability, cannot release the kill switch, and cannot change
  risk/model/strategy parameters or live approval state.
- The server-rendered dashboard adds no browser package supply chain. Production exposure still
  requires TLS ingress, rate limits, external Secret delivery, and hardened authorization.

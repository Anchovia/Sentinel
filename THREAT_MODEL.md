# QuantForge Threat Model

## Protected assets

- Exchange credentials and account authority.
- Funds, balances, positions, orders, and risk-policy state.
- Raw event history, derived datasets, model artifacts, trial ledger, and audit evidence.
- Source, release manifests, deployment configuration, backups, and operator identities.

## Adversaries and failures

- External attacker targeting dashboard, API, host, dependencies, or credentials.
- Malicious or malformed exchange payload, research document, log, issue, or model artifact.
- Compromised dependency/container/action or poisoned research dataset.
- Accidental operator configuration, stale data, clock drift, network partition, disk/DB failure, process crash, or duplicate request.
- Faulty strategy/model producing excessive, correlated, stale, or cost-negative intents.
- Scheduled AI task exceeding its file or action scope.

## High-priority abuse cases

| Threat | Primary controls | Failure response |
| --- | --- | --- |
| Credential theft/logging | external secret store, process isolation, redaction, least privilege | revoke, block trading, audit |
| Unauthorized live activation | six gates, explicit injection, operator approval, audit | fail closed, incident |
| Duplicate/ambiguous order | unique identifier, lookup before retry, UNKNOWN state | market block, reconcile |
| Balance/ledger divergence | independent ledger and periodic reconciliation | global order block |
| Stale/corrupt market data | freshness/schema/gap/clock health gates | affected-market block |
| Prompt injection | external content treated as data, command/URL allowlists | stop task, report evidence |
| Supply-chain compromise | lockfile, audit, review, pinned release artifacts | quarantine build/release |
| Model/feature drift | range/missingness/drift/calibration monitoring | abstain, reduce/pause, experiment |
| Dashboard control abuse | authentication, authorization, CSRF, confirmation, idempotency | reject, audit, incident |
| Scheduled task code drift | report path allowlist or isolated worktree, no merge/deploy | preserve evidence, human review |

## Trust-boundary validation

Each boundary receives schema validation, bounded resource use, structured error handling, Secret filtering, and auditable identifiers. Data or model uncertainty cannot be coerced into an approval. A missing security control is treated as unavailable functionality.

## Residual risks

L2 public data cannot establish exact queue position; exchange/API behavior and rate limits can change; cloud/host compromise may bypass application controls; backtests cannot prove future performance. These risks require conservative assumptions, capability synchronization, monitoring, backups, human approvals, and limited manual canaries—not stronger profit claims.

# ADR-022: Bounded Work Audit Exports

- Status: accepted
- Date: 2026-08-24
- Scope: report-only local Work evidence

## Context

The supervised public paper runtime already emitted fresh Secret-free JSON, but those generated
files are intentionally ignored by Git. The first Work manual audit used ignore-aware discovery,
saw only tracked `.gitkeep` files, and incorrectly concluded that no runtime evidence existed.
Direct filesystem access then verified all six generated files. The existing names and shapes also
did not provide the stable `ops/latest`, incident, performance, model, and multi-window baseline
contracts expected by the scheduled audit prompts.

## Decision

Keep every generated export ignored and local. On each 15-second public-paper heartbeat, derive five
small versioned audit inputs at fixed paths:

- `runtime_exports/ops/latest.json`
- `runtime_exports/data_quality/latest.json`
- `runtime_exports/incidents/open.json`
- `runtime_exports/performance/latest.json`
- `runtime_exports/models/latest.json`

The producer uses only in-memory public-paper state and existing Secret-rejecting atomic writes. It
does not query an account, private endpoint, order service, production database, model registry, or
external network. Missing capability is explicit: incident, private-stream, reconciliation,
database, backup, model-drift, and representative performance evidence is marked
`NOT_CONFIGURED`, `PARTIAL`, or `INSUFFICIENT_SAMPLE`, never silently converted to a healthy zero.

Every 15 minutes, retain one combined immutable baseline under `runtime_exports/baselines/**`.
Prune baseline files after 30 days and cap them at 100MiB, oldest first. Current files continue to
update atomically. Work must open these generated files by exact filesystem path instead of relying
on Git-index or ignore-aware search.

Do not register an unattended task until a manual trial proves that the current Work surface can
access the same local files during scheduled execution. A missing scheduled local-file capability
is a valid blocking result.

## Consequences

- Work can distinguish a genuinely missing producer from a Git discovery limitation.
- Fresh operational health can be reviewed while representative strategy performance and model
  drift remain honestly unavailable.
- The 24-hour and 7-day comparisons can accumulate without committing runtime data to the public
  repository or materially growing C-drive usage.
- The first baseline after a restart may describe startup state; later samples preserve the
  chronological transition without rewriting history.
- These exports and baselines are audit evidence only. They cannot approve a model, change risk,
  activate paper orders, enable live trading, or submit an order.

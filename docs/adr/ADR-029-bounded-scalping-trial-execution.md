# ADR-029: Bounded Scalping Trial Execution

- Status: accepted
- Date: 2026-08-27
- Scope: offline public-data research and paper simulation only

## Context

The eligible short-horizon dataset contains more than nine million detailed events across fifteen
markets. Running all registered combinations in one process would make interruption recovery,
memory use, and durable failure retention unnecessarily fragile. The existing raw reader also
materialized every selected row, and the experiment ledger could not safely resume from a persisted
snapshot.

The registration-only `qf-scalp-20260827-v2` ledger exposed another fail-closed issue before any
trial: its metric list omitted the plan's primary median closed-trade return plus closed-trade and
non-fill counts. Executing v2 would therefore either compute undeclared ledger metrics or omit
preregistered evidence. Both outcomes violate the research contract. V2 remains immutable with zero
trials and is not repaired in place.

## Decision

Introduce `scalping-trial-execution-plan-1` after the bounded runner is committed and before any
trial. It binds the exact experiment/registration/data hashes, runner revision, eligible markets,
three deterministic chronological windows, all eighteen trial UUIDs, and fixed operational limits.
The common eligible-market availability span reserves its final 20 percent without reading holdout
event content. The preceding 80 percent is divided into four blocks: one initial history block and
three expanding walk-forward evaluation blocks. Folds one and two are validation; fold three is
test. Registered purge, embargo, and warmup intervals remain explicit in each partition hash.

Run only the next unrecorded trial in registered order. Each work unit is bounded to 500,000 events
per market, 3,000,000 total events, and 900 wall-clock seconds. Raw reads use Arrow batch filters and
fail rather than truncate on either limit. The backtest checks the same event/time bounds while it
runs. Candidate and always-neutral baseline consume identical market inputs and cost assumptions.
There is no approved champion, so artifacts record that comparison as unavailable rather than
inventing one.

After each work unit, atomically write the deterministic artifact and append a succeeded, null, or
failed `TrialResult` to a report-path working ledger. Resume verifies and exactly replays the entire
hash chain, requires completed trials to be a prefix of the registered order, and never overwrites
the committed registration seed. A failure consumes its registered trial ID and is not retried or
hidden. Decision and multiplicity review remain separate after all planned validation/test trials.

The runner's models exclude `final_holdout`, refuse any ledger containing holdout access or a final
decision, and expose no authentication, private network, order network, model promotion, risk
change, paper-order gate, or live action.

## Consequences

- An interruption or bounded failure cannot silently restart the same trial or erase negative
  evidence.
- Memory is bounded by one market window rather than the complete dataset, and one command performs
  at most one of eighteen registered work units.
- V2 remains valid evidence of a blocked execution contract with zero trials. Its v3 replacement
  preregisters the complete metric list against exact runner revision `a2e2593`; an immutable
  execution plan is still required before any work unit can run.
- The final holdout remains sealed. Opening it still requires a separate reviewed one-shot path and
  is deliberately absent from this runner.

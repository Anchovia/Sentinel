# ADR-006: Availability-Ordered Replay and Explicit Gap Semantics

- Status: Accepted
- Date: 2026-08-23

## Context

Exchange timestamps can arrive late, out of order, or ahead of the local clock. Sorting historical
inputs only by exchange time would give a replay consumer information before production received it.
An absence of trades is also ambiguous: the market may have been quiet, or collection may have
failed.

## Decision

Replay inputs in `received_at_utc` order, with receive-monotonic time, connection ID, local sequence,
and event ID as deterministic tie-breakers. The virtual clock advances only to input availability;
exchange time remains event metadata and determines trade-bar membership.

No-trade bars require explicit positive `CoverageWindow` evidence for the entire bucket. Any
overlapping `DataGap`, or missing coverage evidence, produces an incomplete data-gap bar whose
prices, volumes, and trade count are `null`. It is forbidden to encode a gap as zero volume. A
healthy no-trade bar has exact zero volume/count but no fabricated price.

Features record both event time and availability time. Calculators reject inputs whose availability
is later than their requested as-of time. Replay checkpoints bind dataset hash, configuration hash,
cursor, virtual time, counters, and a resumable output hash chain.

## Consequences

- Historical execution follows information availability rather than an idealized exchange clock.
- Late/out-of-order inputs remain observable and cannot silently rewrite already available history.
- Coverage must be supplied by trusted collector-health evidence before bar materialization.
- Golden replay can freeze dataset, configuration, and output hashes across changes.

# ADR-028: Dual-Cutoff Growing-Feed Research Selection

- Status: accepted
- Date: 2026-08-27
- Scope: public-data research and paper simulation only

## Context

The first short-horizon plan fixed only a maximum exchange timestamp. The raw public feed is still
growing, and an event can arrive later while carrying an older exchange timestamp. Reconstructing
the same exchange-time selection after such an arrival could therefore add a row and change the
dataset hash even though the visible cutoff did not change. The retained stale duplicate ticker
evidence demonstrates that exchange time alone is not an availability boundary.

## Decision

Add a backward-readable optional `maximum_received_at_utc` to the version-1 scalping experiment plan
and raw research inventory. Every new growing-feed registration must set it at or before the
registration time. Inventory scanning applies the exchange and receive bounds before duplicate
identity checks, then hashes the selected availability-ordered row identities. It also records the
exact active manifest-set hash captured at scan start so plan lineage and scanned files can be
compared without racing a later compaction cycle.

For the new short-horizon experiment, also bind exclusion of rows marked duplicate and rows with
any nonempty ingestion quality flag. Apply identical options during inventory fingerprinting and raw
event loading. Retain the excluded rows unchanged in raw storage for diagnostics and audit.

Implement the fingerprint with bounded Arrow batches and ephemeral fixed-width sorted runs. Merge
event IDs independently for exact duplicate detection, then merge identities in the original tuple
order to preserve the established SHA-256. Require an explicit wall-time budget for operator runs;
timeout cleans scratch state and creates no research result.

Keep historical plans readable without inventing a receive bound for them. Do not mutate or
reinterpret the original blocked experiment. A new eligible experiment uses a new identifier, exact
committed code revision, both UTC cutoffs, manifest-set lineage, and the resulting row-identity hash.

This decision changes only offline public-data selection. It does not run a trial, open the sealed
final holdout, approve a model, enable paper orders, access authentication, or create a live path.

## Consequences

- Later-arriving events cannot silently alter a registered growing-feed selection, even when their
  exchange timestamps precede the fixed exchange cutoff.
- The eligible counts and future replay use the same clean-row rule as the validated 24-hour report.
- Compaction may change manifest lineage, but not the selected row-identity hash when row content is
  preserved.
- Existing version-1 artifacts remain valid and immutable; the additive field is required by policy
  for new registrations rather than retroactively fabricated.
- A new experiment can be fingerprinted reproducibly before any planned trial is executed.
- Large inputs no longer require one Python tuple and set entry per selected row. Temporary runs are
  recoverable scratch only and are removed on normal success, handled failure, or timeout.
- The first eligible application is `qf-scalp-20260827-v2`: 9,157,974 selected rows, 15 eligible
  markets, dataset hash `4002405439cbe4afbedf64ea90a84be486640754a0a2de12a4d726760dae8fd6`,
  and one registration-only ledger record. This records the planned search space but does not count
  as a trial, decision, holdout access, or model approval.

# ADR-023: Incremental Raw Quality and Research-Availability Index

- Status: accepted
- Date: 2026-08-24
- Scope: public paper-data integrity and future research preregistration readiness

## Context

The first fixed-cutoff research inventory correctly verified 430,655 detailed public events, but
materializing every selected row in Python took roughly 11 minutes. Repeating that full scan for
each audit would consume increasing CPU and memory as the bounded D-drive history grows. Runtime
counters alone cannot prove that retained Parquet payloads still match their manifests, and a
research availability count must not silently authorize an existing or future experiment.

## Decision

Maintain `raw-data-quality-index-1` beside the raw store. Enumerate only active immutable manifests.
For a new, changed, or verification-expired file, verify its SHA-256, byte size, Parquet metadata,
row count, constant source/event/schema fields, payload-hash shape, and exchange-time bounds. Use
columnar aggregation for per-market event counts and receive-time intervals, then cache the result
under the manifest fingerprint. Reuse unchanged entries for 24 hours and remove entries whose
manifests have been retired by compaction or retention.

The index is replaced atomically only after every selected file passes. A checksum, size, schema,
path, or contract failure leaves the previous index intact and fails the caller closed. Runtime
storage commits and maintenance refresh the index outside the feature/decision hot path. The
operator command `index-raw-quality` can bootstrap or independently refresh the same contract.

Publish the aggregate through `paper-runtime-6` and version-3 live data-quality exports. The Korean
monitor shows only verification totals and whether enough data exists to create a *new*
preregistration. Readiness requires 24 hours plus at least 20,000 trade and 20,000 orderbook events
in each of three markets. It cannot change the immutable cutoff of the existing experiment, approve
a model, open the independent paper-order gate, or submit an order.

## Consequences

- The first D-drive pass verifies all active files; later passes normally scan only new files.
- The sidecar remains bounded by active retained manifests and contains no raw payload, credential,
  account, private-network, or order capability.
- Within-file duplicate identities, ordering regressions, duplicate-message flags, and quality flags
  are counted. Cross-file event-identity uniqueness, exact public-exchange completeness, and gap
  reconstruction still require a bounded deterministic replay.
- Compaction can replace active manifest identities without changing rows; the next refresh verifies
  replacement files and retires stale cache entries.
- A positive availability result is permission only to preregister a new falsifiable experiment.
  Trial execution and paper model approval remain separate human-reviewed steps.

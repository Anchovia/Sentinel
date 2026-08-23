# QuantForge Data Model

## Versioning

All external and persisted contracts carry a schema version. Breaking changes require a migration, compatibility test, changelog entry, and dataset/model lineage update.

## Event envelope

Every exchange event is wrapped with:

```text
event_id, event_type, schema_version, source, market
exchange_timestamp, received_at_utc, received_monotonic_ns
connection_id, subscription_id, local_sequence
raw_payload, raw_payload_hash, normalization_version
is_snapshot, is_realtime, is_duplicate, quality_flags
```

Raw payloads are append-only. Partitioned files use atomic temporary writes, ZSTD compression, row/time statistics, checksums, and manifests. Raw and derived storage are separate.

## Derived dataset manifest

```text
dataset_id, created_at, source_dataset_ids, code_commit
feature_version, label_version, parameters, row_count
time_range, market_universe, checksum, known_gaps
```

No-trade intervals and data gaps are distinct. A gap is never silently filled as a zero-volume bar.

## Transactional entities

Minimum PostgreSQL entities:

- markets and market-status history;
- orders, order events, fills, balances, balance snapshots, positions, and lots;
- PnL events, risk snapshots/decisions, strategy runs, signals, and feature snapshots;
- regime/alpha/execution predictions, model versions/releases;
- experiments/trials, incidents, deployments, reconciliation runs, and audit log.

Order and ledger events are immutable append records; current views are derived. Monetary columns use exact numeric types with explicit scale and currency/unit metadata.

## Time

- Persist UTC-aware timestamps; reject naive datetimes.
- Keep exchange, receive-wall-clock, and receive-monotonic times separate.
- Use monotonic time only for durations/latency.
- Store availability time for any feature or external dataset to prevent look-ahead.

## Runtime exports

`runtime_exports` contains redacted, review-oriented snapshots for operations, performance, models, data quality, incidents, releases, and research. Exports exclude credentials, authorization material, raw account identifiers, and `.env` content. Schemas and Secret tests are mandatory before scheduled consumers are enabled.

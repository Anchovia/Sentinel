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

## Replay checkpoint

```text
dataset_hash, config_hash, cursor, virtual_time_utc, chain_hash
delivered_events, delivered_gaps, skipped_duplicates
out_of_order_events, reconnect_boundaries
```

Replay order follows input availability (`received_at_utc`), not idealized exchange time. The
checkpoint hash chain can resume without changing the final golden output hash.

## Time bars

Phase 2 bar intervals are 1s, 5s, 15s, and 1m. A traded bar carries Decimal OHLC, base/quote volume,
trade count, aggressive buy/sell volume, VWAP, trade timestamps, source hash, and availability.

- `no_trade=true`: complete collector coverage, exact zero volume/count, and null prices.
- `data_gap=true`: incomplete or explicit gap; prices, volume, and count are null.

No-trade status requires positive collector-health coverage for the full bucket. A gap always wins
over observed partial trades.

## Feature snapshot

```text
feature_set, feature_version, market
event_time_utc, available_at_utc, computed_at_utc
values, input_hash, quality_flags
```

Feature values may use binary floating point as analytical model inputs; money, orders, bars,
accounting, and risk limits remain Decimal. Every feature calculator filters by availability and
fails on future inputs.

## Paper execution

```text
PaperOrder:
order_id, intent_id, decision_id, market, side, order_type, time_in_force
limit_price, original_quantity, remaining_quantity, reference_mid
submitted_at, arrival_at, status, policy_hash, cancel timestamps, reject_reason

PaperFill:
fill_id, order_id, sequence, market, side, quantity, price, notional, fee, fee_rate
liquidity_role, filled_at, source_event_id, reference_mid
spread_cost, slippage_cost, adverse_selection_cost, model
```

Paper order and fill IDs are derived from replay lineage. `conservative_l2` is the default;
`naive` is comparison-only and `calibrated_l2` requires a calibration identifier.

## Portfolio ledger

Each immutable ledger record carries a sequence, deterministic record ID, event kind, time,
order/fill references, amount/quantity, post-event balances and locks, realized gross PnL,
cumulative fees, sorted details, previous hash, and record hash. FIFO lots retain source fill,
opening time/price, and original/remaining quantity.

Valuation snapshots reconcile all of the following exactly:

```text
available_cash = cash_balance - locked_cash
market_value = position_quantity * mark_price
gross_pnl = realized_pnl + unrealized_pnl
net_pnl = gross_pnl - fees = equity - initial_cash
equity = cash_balance + market_value
```

Spread, slippage, and adverse-selection fields are execution-cost attribution. Costs embedded in the
fill price are not subtracted a second time.

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

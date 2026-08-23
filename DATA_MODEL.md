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

## Research dataset and labels

```text
FeatureRow:
row_id, market, event_time_utc, available_at_utc
feature_set, feature_version, sorted values, reference_price, source_snapshot_hash

LabeledExample:
example_id, source_row_id, event_time_utc, features_available_at_utc
label_end_utc, label_available_at_utc, sorted values
alpha_class, future_return_bps, current/future reference prices
```

Forward labels cannot become available before both the feature and future reference observation.
The label specification hashes horizon, reference, round-trip cost, and safety margin. Splits retain
source/plan/partition hashes and the fixed role order train, validation, test, final holdout.

## Experiment ledger

Preregistration stores hypothesis, researcher, code/dataset/feature/label lineage, model family,
complete hyperparameter space, planned metrics/splits, cost model, and explicit holdout plan. Trial
records retain parameters, seed, split/artifact hashes, metrics or failure, and holdout review. Close
records reconcile trial/failure/holdout counts. All records form an append-only SHA-256 chain.

## Model artifacts and predictions

Model metadata records model/family/version, training code, dataset/features/labels, chronological
train/validation/test periods, parameters, seed, metrics, calibration, market/regime scope, inference
schema, artifact hash, creator time, approver, and release state. Registered artifact bytes,
metadata, and manifest are independently checksummed and verified on load.

Prediction contracts cover regime probabilities, alpha class probabilities/net edge/uncertainty/
abstention, and execution fill/cost estimates. Analytical probabilities and features may use finite
binary floats; order, fee, return/cost boundary, and accounting values remain Decimal.

## Strategy, risk, and attribution

`StrategyInput` binds one market's market/feature/regime/alpha/execution/portfolio snapshots and a
read-only risk context to a UTC decision time. `StrategyDecision` records action, side, exact target,
order preference, gross/cost/net edge, confidence, uncertainty, validity, invalidation, exit plan,
reasons, strategy, and version. It is a proposal, not an order.

`RiskSnapshot` records market and system health, freshness, model release, edge/cost, depth,
portfolio/exposure, loss/drawdown, turnover, rate, lock, and unknown-order state. A `RiskDecision`
binds its intent and policy version to the immutable snapshot ID.

Kill-switch and attribution events are independently sequenced SHA-256 chains. Attribution uses:

```text
net_pnl = gross_edge_pnl - fees - spread_cost - slippage_cost - adverse_selection_cost
```

The formula describes analytical strategy attribution; actual portfolio equity remains reconciled
from fill prices and does not subtract embedded costs twice.

## Authenticated execution safety

`ExchangeOrderRequest` binds an intent and risk decision to one market, documented order shape,
exact Decimal price/volume, time-in-force, SMP mode, expiry, and a mandatory client identifier. Its
ordered body is also the input to the reviewed authentication query hash.

Each persistent execution journal event carries sequence, intent/risk IDs, burned identifier,
market, local order state, event time/source, optional exchange UUID, sorted details, previous hash,
and event hash. Reload verifies the full chain and every state transition before exposing current
state.

Private `MyOrder` and `MyAsset` wire values are decoded with Decimal-preserving JSON and mapped to
exchange-neutral immutable observations. Reconciliation compares identifier-indexed remote orders
and exact available/locked balances, emitting an immutable report hash and `safe_to_resume=false` on
any uncertainty, unknown/missing order, state mismatch, or balance mismatch.

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

Phase 7 defines `operations-dashboard-1`, containing UTC generation time and fixed Overview,
Markets, Positions, Orders, Strategies, Models, System, and Incidents views. Decimal is retained for
assets, balances, prices, quantities, fees, exposure, and PnL. Exchange order UUIDs are represented
only by a short one-way reference hash; account UUIDs are forbidden.

Incident, emergency-control, and audit histories are append-only JSONL chains with sequence,
previous hash, and record hash. Control records bind a hashed idempotency key to one request
fingerprint and record status, result code, verified-effect flag, and `network_used=false`.

The `operations-backup-1` manifest records creation time, source revision, paper mode, unmeasured
RPO/RTO targets, external-encryption status, canonical relative paths, byte counts, per-object
SHA-256, and an aggregate hash. A local manifest with encryption false is restore-drill evidence,
not a production backup claim.

# QuantForge Operator Runbook

## Safety first

QuantForge is paper-only. Phase 1 public collection does not need credentials. If any command or
screen suggests live submission is possible, stop and open a `CRITICAL` incident.

## Developer start

```text
uv sync --all-groups
uv run quantforge safety-status
uv run uvicorn quantforge.api.app:create_app --factory
```

Expected safety output: trading mode `paper`, live submission `false`, and all live gates listed as failed.

## Finite public-data collection

Collect a bounded API-key-free sample:

```text
uv run quantforge collect-public \
  --markets KRW-BTC \
  --streams ticker,trade,orderbook \
  --max-messages 100 \
  --output data/raw
```

The command writes immutable ZSTD Parquet files and adjacent JSON manifests below
`source=upbit/event_type=.../date=.../hour=...`. It reports `authentication_used=false` and
`order_submission_available=false`. A collector failure must not be worked around by adding keys.
Review rejected-message and reconnect metrics, preserve the malformed raw input outside logs if
needed for incident analysis, and refresh official capability documentation before schema changes.

## Offline verified replay

Verify all manifests and raw-payload digests, replay by availability time, and write a redacted data
quality snapshot:

```text
uv run quantforge replay-raw \
  --input-root data/raw \
  --output-root runtime_exports/data_quality
```

Repeating the command over unchanged files must return identical dataset and output hashes. A
checksum, row-count, schema, raw-payload, latency, or event-contract mismatch stops replay. Never
skip integrity checks to recover a dataset; preserve the file and open a data incident.

Bar materialization requires explicit `CoverageWindow` evidence. Missing coverage becomes
`data_gap`, not `no_trade`. Features may use only events/bars whose `available_at_utc` is no later
than the requested as-of time.

Infrastructure, when Docker Compose is available:

```text
docker compose -f docker-compose.yml -f docker-compose.paper.yml up -d
docker compose ps
```

Default endpoints bind to localhost: API 8000, Grafana 3000, Prometheus 9090, PostgreSQL 5432. The committed Grafana/PostgreSQL passwords are development-only and must not be used in production.

## Validation

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest --cov=quantforge --cov-report=term-missing
uv run python scripts/check_no_secrets.py
uv run pip-audit --progress-spinner off --cache-dir .tools/pip-audit-cache
```

Do not continue a milestone with failed validation. Record failures and fixes in `PROGRESS.md` and `docs/HANDOFF.md`.

## Incident priorities

- `CRITICAL`: Secret exposure, unknown/unresolved order, balance mismatch, live-lock/kill-switch failure, unauthorized source modification.
- `HIGH`: repeated rate-limit errors, major data gap/clock skew, overdue reconciliation, abnormal slippage, repeated restarts.
- `WARNING`: mild drift/degradation, sample insufficiency, rising latency, minor data-quality issue.

## Immediate response

1. Preserve logs, event IDs, code/config/model versions, and timestamps without copying Secrets.
2. Block new orders; use `cancel_only` only through an implemented, authenticated, audited operator path.
3. Classify affected services/markets and whether account state may differ from the internal ledger.
4. Reconcile before any restart or re-enable action.
5. Revoke credentials for suspected exposure.
6. Create an incident record and require operator approval to close critical events.

## UNKNOWN order

Never repeat the POST because a response timed out. Query by unique identifier and UUID across open/closed states, preserve the intent and request evidence, block that market, and reconcile. If state remains uncertain, maintain the block and escalate.

## Shutdown

Stop new intents, drain bounded work, persist checkpoints/manifests, record a clean-shutdown marker, close streams, and then stop services. On next start, reconciliation precedes order eligibility.

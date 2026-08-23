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

## Supervised public paper burn-in

Start a foreground burn-in that runs until explicitly stopped:

```text
uv run quantforge run-paper \
  --markets KRW-BTC \
  --streams ticker,trade,orderbook \
  --raw-output data/paper/raw \
  --output-root runtime_exports
```

For a bounded smoke, add both `--duration-seconds 30` and `--max-messages 30`. Inspect the latest
heartbeat without using the network:

```text
uv run quantforge paper-status \
  --snapshot runtime_exports/ops/paper-runtime.json \
  --require-fresh-seconds 90
```

Startup must fail if an Upbit key is configured, any live gate is partially opened, the mode is not
paper, or the environment is production. The status must always report authentication/private
network/order/live submission false. Stop the process normally so buffered rows and the terminal
heartbeat are committed. After an abnormal stop, verify manifests and replay before trusting new
coverage. Phase 10 observes and stores public data only; zero paper fills is expected.

While the supervisor is running, open the generated local file directly in a browser:

```text
runtime_exports/ops/paper-monitor.html
```

The Korean read-only monitor reloads every five seconds. It shows public price, latest event age,
connection/errors/reconnects, current-run counts, and manifest-backed retained rows/files/bytes.
It needs no server or token and exposes no raw payload, account, credential, strategy control, or
order action. Retained totals are reconstructed from immutable manifests after each restart; a
storage integrity error blocks startup instead of showing an untrusted total.

The same page includes the Phase 11.1 feature-processing latency. To reproduce the measurement from
verified retained data without network or order access:

```text
uv run quantforge benchmark-realtime \
  --input-root data/paper/raw \
  --max-events 10000 \
  --processing-budget-ms 5
```

This is a feature-core benchmark, not end-to-end decision or order latency. It must report `HOLD`,
no approved model, and every private/order/live capability false. Review
`runtime_exports/ops/realtime-pipeline.json` together with `paper-runtime.json`; any storage queue
overflow is a runtime failure, not a permissible loss counter.

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
## Uncertain order recovery

1. Stop new submissions and activate `cancel_only` when runtime controls are available.
2. Reload and verify the append-only execution journal. Do not continue if the chain, identity, time,
   or state transition validation fails.
3. For `SUBMISSION_PENDING`, `UNKNOWN`, or interrupted `RECONCILING`, query the exact burned client
   identifier. Never call create again.
4. Compare all local nonterminal orders with remote order state and compare exact available/locked
   balances by currency.
5. Keep trading blocked while any order is unknown/missing/mismatched or any balance differs.
6. Release only after successful reconciliation and explicit human approval.

Phase 6 provides mock-only proof of this flow. It has no authenticated exchange transport.

## Operations export and dashboard

Generate the Secret-free read model before opening the operations view:

```text
uv run quantforge export-operations --output-root runtime_exports
```

The command must report `paper`, `live_submission_allowed=false`, `network_used=false`, and
`order_submission_available=false`. It writes `runtime_exports/ops/dashboard.json` atomically and
rejects credential/authorization fields, bearer/JWT-shaped text, and full account UUIDs.

Dashboard access is disabled until both `QF_DASHBOARD_ACCESS_TOKEN` and
`QF_DASHBOARD_CSRF_SECRET` are supplied from an external Secret boundary. Do not store either in the
repository or a runtime export. After starting the API, authenticated operators may read:

```text
GET /dashboard
GET /api/v1/dashboard
GET /api/v1/incidents
GET /api/v1/audit
```

Grafana's `QuantForge Health` dashboard shows paper safety, unknown orders, balance mismatch, kill
switch, incidents, disk, reconciliation age, and market-data connection. A zero or empty metric is
not proof of health unless its source snapshot is fresh.

## Emergency control requests

State-changing requests require bearer authentication, a fresh CSRF proof from
`GET /api/v1/session`, a unique `Idempotency-Key`, and the exact confirmation phrase. Reuse the same
key only for the exact same request. A conflicting key is rejected; a request interrupted after its
durable `REQUESTED` record becomes `UNKNOWN` and must be reconciled, not executed again.

Allowed Phase 7 outcomes:

- `activate_cancel_only`: activates and verifies the local new-order block.
- `acknowledge_incident`: updates and verifies a local incident record.
- `pause_strategy_request`: records a proposal but does not mutate strategy runtime state.
- `cancel_all_orders_request`: returns `BLOCKED`; no authenticated cancellation transport exists.

There is no dashboard action for kill-switch release, flattening, risk/model/strategy parameter
changes, live activation, or order submission. Treat any claim otherwise as a critical incident.

## Local backup and restore drill

Create a local checksummed proof only from explicit non-Secret workspace paths:

```text
uv run quantforge backup-local \
  --source runtime_exports \
  --source configs \
  --source ops \
  --source-revision <reviewed-commit>

uv run quantforge verify-backup --backup data/backups/<backup-id>
uv run quantforge restore-drill \
  --backup data/backups/<backup-id> \
  --target data/restore-drill/<backup-id>
```

The restore target must be new or empty. The drill writes `RESTORE_PAPER_ONLY` and contains no
credential or order capability. The manifest deliberately reports external encryption false and
RPO/RTO unmeasured, so this artifact is not a production backup. A checksum failure, extra file,
symlink, Secret-shaped file, or non-paper manifest invalidates the entire proof.

## Work and Codex scheduled-task setup

Follow `automation/SCHEDULED_TASK_SETUP.md`; the catalog is `not_registered` by default. Manually run
the exact prompt before scheduling it, inspect its report, validate the matching JSON manifest, and
confirm the write boundary:

```text
uv run quantforge validate-automation-report \
  --report <same-stem-report.json> \
  --workspace-root <checkout> \
  --allowlist automation/write-allowlist.yaml

uv run quantforge validate-automation-trigger \
  --trigger <trigger.json> \
  --allowlist automation/write-allowlist.yaml
```

Work local-file tasks must be created from the desktop project and may write only report/proposal
paths. Record `git diff -- src configs ops migrations dashboard` before and after. Do not undo an
unexpected change; preserve and report it as a critical boundary violation.

Codex code tasks must use the dedicated background worktree option. A no-finding result writes only
its report. Reproduce before editing; add regression evidence; run all checks; stop without a PR on
failure. A passing result may create a draft non-main candidate, but never merge, deploy, promote,
change risk/live state, or call an order path. Review or archive the task before deliberately
cleaning its worktree.

## Live-readiness validation

Use only a reviewed, Secret-free evidence bundle. This command reads evidence/policy and writes an
atomic report; it does not load runtime settings, connect to Upbit, or change live state:

```text
uv run quantforge validate-live-readiness \
  --evidence <reviewed-evidence.json> \
  --policy configs/readiness.default.yaml \
  --output-root runtime_exports
```

Review every failed/conditional gate and both input hashes. `READY_FOR_MANUAL_CANARY_REVIEW` is not an
activation instruction. Keep paper mode, order submission false, and operator unlock absent until a
separate human-governed implementation and approval process exists. See
`docs/readiness/LIVE_READINESS.md`.

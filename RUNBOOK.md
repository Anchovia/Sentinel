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

Replay the same verified data through features, neutral inference, strategy routing, paper risk,
broker state, and read-only portfolio accounting:

```text
uv run quantforge benchmark-paper-decision \
  --input-root data/paper/raw \
  --max-events 10000
```

Until a separately reviewed artifact and human paper approval exist, the output must show
`EXPERIMENTAL`, approval false, `HOLD`, and zero strategy proposals, risk approvals, paper orders,
and fills. It must also show `paper_order_simulation_enabled: false`. A matching model approval is
insufficient on its own: the independent paper-order simulation gate defaults closed and must remain
closed unless recovery is `VERIFIED_CLEAN`; an unclean recovery block requires a future reviewed
operator acknowledgement. The matching live shadow snapshot is
`runtime_exports/ops/realtime-paper-decision.json`. Do not create or edit approval or gate data
merely to make these counters nonzero. The fixture exercising a simulated fill exists only in tests
and is not market or performance evidence.

### Paper recovery checkpoint

The supervised service writes `data/paper/state/realtime-paper-recovery.json` in its durable paper
volume. The outer checkpoint hash, execution-policy hash, every portfolio-state hash, broker fill
sequence, and ledger chain must validate before restore. A clean restart reports
`VERIFIED_CLEAN`; a first run reports `NEW`. `EMPTY_UNCLEAN_RECOVERED` is allowed only when simulation
was disabled and the checkpoint proves there was no order, fill, lock, lot, ledger record, cost,
turnover, or balance change.

If the monitor reports `UNCLEAN_RECONCILED` or `재시작 복구: 확인 필요`:

1. Keep the paper-order simulation gate closed; do not edit the checkpoint or approval files.
2. Confirm every recovered non-terminal paper order was canceled and every cash/position lock is 0.
3. Preserve the checkpoint, runtime snapshot, raw-data manifests, and logs as incident evidence.
4. Mark the interrupted paper session invalid for performance claims.
5. Continue keyless public collection only. A future reviewed operator workflow is required to clear
   the persistent recovery block; restarting again does not clear it.

The checkpoint deliberately excludes orderbooks. A new verified public L2 snapshot is required after
every restart. `SIGTERM` and `SIGINT` request a clean supervisor stop and close the active public
socket before storage/checkpoint cleanup. Checkpoint I/O on consequential order/accounting changes is
part of decision latency.

### Bounded paper-data storage

The current Windows host stores bulk paper data at `D:/Sentinel-Data`. The machine-specific path is
kept only in ignored `compose.paper.local.env`:

```text
QF_PAPER_DATA_HOST_PATH=D:/Sentinel-Data
QF_PAPER_DATA_LABEL=D:/Sentinel-Data
```

Never commit that local file and do not use it for credentials. The committed example falls back to
`./data/paper`. Start or recreate the paper service with the explicit local environment file:

```text
docker compose --env-file compose.paper.local.env -f docker-compose.yml -f docker-compose.paper.yml up -d paper-runtime
```

The active policy is ZSTD Parquet, completed-hour compaction every 15 minutes, 30-day retention,
50GiB maximum active raw data, and a 20GiB minimum free-space floor. `paper-runtime-6` and the Korean
monitor show the effective path, bounds, reclaimed bytes, verified rows/files, and actual free
space. The 50GiB cap may
delete data before 30 days during high activity. A file is retired by renaming its manifest to a
reason-specific marker before its payload is removed.

Bootstrap or independently refresh the verified incremental index with no exchange network or
authentication:

```text
uv run quantforge index-raw-quality \
  --input-root <paper-data-root>/raw \
  --index <paper-data-root>/index/raw-data-quality-index.json \
  --storage-label <non-secret-label>
```

The first run verifies every active file. Later runs reuse unchanged entries for 24 hours and scan
new/changed files; `--reverify-after-seconds 0` forces a full checksum pass. Any size, checksum,
schema, row, path, or contract mismatch must fail without replacing the prior valid index. Pause a
manual replay if compaction is active and retry only after maintenance completes. A research-ready
result allows drafting a new preregistration only; never edit the existing experiment cutoff or
open a model/paper-order gate from this signal.

If free space crosses the floor, the service must enter `FAILED` and close the public socket. Do not
lower the floor merely to restart. Free space on the configured data drive, preserve the runtime and
retirement evidence, then recreate the service and verify `VERIFIED_CLEAN`, full ticker coverage,
zero queue overflows, and a healthy container.

For a host-path migration, stop the service and require a clean recovery checkpoint before copying
`/app/data/paper`. Compare manifest count, Parquet count, Parquet byte total, and retained rows before
recreating the container. Keep the prior volume until the new path passes checksum replay and restart
verification. A same-host copy is rollback convenience, not an encrypted off-host backup.

Infrastructure, when Docker Compose is available:

```text
docker compose --env-file compose.paper.local.env -f docker-compose.yml -f docker-compose.paper.yml up -d
docker compose --env-file compose.paper.local.env -f docker-compose.yml -f docker-compose.paper.yml ps
```

Default endpoints bind to localhost: API 8000, Grafana 3000, Prometheus 9090, PostgreSQL 5432. The committed Grafana/PostgreSQL passwords are development-only and must not be used in production.

The paper Compose service resolves `ALL-KRW` at startup without credentials. It monitors every
current KRW pair by ticker and assigns trade/five-level-orderbook processing to 20 focused pairs.
Confirm `runtime_exports/ops/realtime-universe.json` reports full ticker coverage, a nonempty focus,
and no order capability. A catalog/schema failure must stop startup; do not replace it with a stale
hard-coded list. Watch raw-volume growth and disk free space before increasing the focus limit.

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

## Short-horizon research assessment

The experiment plan is already committed and must not be edited after seeing a result. Assess the
registered public-data cutoff with an exact committed implementation revision:

```text
uv run quantforge assess-scalping-research \
  --source-revision <exact-commit> \
  --plan-path research/experiments/2026-08-24-scalping-challenger-v1.json \
  --input-root <paper-data-root>/raw \
  --output-root reports/codex/research
```

The command verifies detailed raw-file checksums, hashes selected row identities, and checks the
per-market 24-hour/20,000-trade/20,000-orderbook minimum. If fewer than three markets qualify, it
writes a `BLOCKED` Markdown report, JSON manifest, and hash-chained experiment ledger with zero
trials and no final-holdout access. Do not shorten the threshold, move the cutoff, or select a more
favorable subinterval. A checksum or concurrent-compaction failure invalidates the assessment;
wait for storage maintenance to finish and start a new explicitly recorded attempt.

This command has no authentication or exchange-order network. It cannot approve a model, enable
the independent paper-order gate, change risk/live state, or send any order. A later qualifying
trial result remains research evidence and requires separate human paper review.

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
unexpected change; preserve and report it as a critical boundary violation. A one-time unattended
read/write test passed on this host; its execution timing still depends on the computer and desktop
app being available. Treat stale runtime input as an operations result, separately from filesystem
access success.

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

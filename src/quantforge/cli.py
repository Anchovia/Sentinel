"""Operator-safe command line interface."""

import asyncio
import json
import math
import shutil
import signal
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Annotated, cast

import typer

from quantforge.automation import (
    AutomationActor,
    assert_paths_allowed,
    assert_report_boundary,
    load_report,
    load_trigger,
    load_write_allowlist,
)
from quantforge.config import get_settings
from quantforge.domain import DataGap, EventEnvelope
from quantforge.exchange.upbit.errors import UpbitAdapterError
from quantforge.exchange.upbit.market_catalog import (
    UpbitMarketCatalogError,
    UpbitPublicMarketCatalog,
)
from quantforge.exchange.upbit.public_ws import UpbitPublicWebSocketClient
from quantforge.exchange.upbit.subscriptions import (
    PublicStreamType,
    UpbitSubscription,
    build_tiered_public_subscriptions,
)
from quantforge.operations import (
    LocalBackupManager,
    create_operations_context,
    write_dashboard_snapshot,
)
from quantforge.readiness import (
    ReadinessEvaluator,
    load_readiness_evidence,
    load_readiness_policy,
    write_readiness_report,
)
from quantforge.replay import ReplayEngine, VirtualClock
from quantforge.research import TrialStatus, read_experiment_ledger
from quantforge.research.scalping import (
    ScalpingResearchError,
    blocked_experiment_ledger,
    create_blocked_scalping_report,
    evaluate_scalping_data_sufficiency,
    load_scalping_experiment_plan,
    write_scalping_research_bundle,
)
from quantforge.research.scalping_finalization import finalize_scalping_trial_experiment
from quantforge.research.scalping_trials import (
    create_scalping_trial_execution_plan,
    load_scalping_trial_execution_plan,
    run_next_scalping_trial,
    validate_scalping_trial_registration_seed,
    write_scalping_trial_execution_plan,
)
from quantforge.runtime import (
    PAPER_RECOVERY_CONFIRMATION,
    DataQualitySnapshot,
    LiveSubmissionGuard,
    PaperRecoveryIntegrityError,
    PaperRecoveryReviewError,
    RealtimePaperOrchestrator,
    RealtimePaperPipeline,
    RealtimeUniversePolicy,
    RealtimeUniverseScanner,
    create_paper_recovery_acknowledgement,
    pending_paper_recovery_acknowledgement_path,
    read_realtime_paper_recovery_checkpoint,
    validate_paper_recovery_clearance,
    write_data_quality_snapshot,
    write_paper_recovery_acknowledgement,
)
from quantforge.runtime.paper_supervisor import (
    PaperRuntimePolicy,
    PaperRuntimeSnapshot,
    PaperRuntimeState,
    PaperRuntimeSupervisor,
    read_paper_runtime_snapshot,
)
from quantforge.storage import (
    ParquetRawEventWriter,
    RawResearchInventoryProgress,
    RawResearchInventoryTimeout,
    RawStoragePolicy,
    cleanup_orphan_temp_files,
    read_raw_events,
    scan_raw_event_research_inventory,
    update_raw_data_quality_index,
)

app = typer.Typer(no_args_is_help=True, help="QuantForge research and operations CLI")
DEFAULT_RAW_OUTPUT = Path("data/raw")
DEFAULT_PAPER_RAW_OUTPUT = Path("data/paper/raw")
DEFAULT_RAW_QUALITY_INDEX = Path("data/paper/index/raw-data-quality-index.json")
DEFAULT_REPLAY_INPUT = Path("data/raw")
DEFAULT_DATA_QUALITY_OUTPUT = Path("runtime_exports/data_quality")
DEFAULT_OPERATIONS_OUTPUT = Path("runtime_exports")
DEFAULT_BACKUP_ROOT = Path("data/backups")
DEFAULT_AUTOMATION_ALLOWLIST = Path("automation/write-allowlist.yaml")
DEFAULT_READINESS_POLICY = Path("configs/readiness.default.yaml")
DEFAULT_PAPER_RUNTIME_SNAPSHOT = Path("runtime_exports/ops/paper-runtime.json")
DEFAULT_SCALPING_PLAN = Path("research/experiments/2026-08-24-scalping-challenger-v1.json")
DEFAULT_SCALPING_CURRENT_PLAN = Path("research/experiments/2026-08-28-scalping-challenger-v4.json")
DEFAULT_SCALPING_CURRENT_LEDGER = DEFAULT_SCALPING_CURRENT_PLAN.with_suffix(".ledger.json")
DEFAULT_CODEX_RESEARCH_OUTPUT = Path("reports/codex/research")


async def _run_paper_with_signals(
    supervisor: PaperRuntimeSupervisor,
) -> PaperRuntimeSnapshot:
    """Translate container termination signals into the supervisor's clean shutdown path."""

    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    stop_tasks: set[asyncio.Task[None]] = set()

    def request_stop(selected: signal.Signals) -> None:
        task = asyncio.create_task(
            supervisor.request_stop(reason=f"signal_{selected.name.lower()}")
        )
        stop_tasks.add(task)
        task.add_done_callback(stop_tasks.discard)

    for selected in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(selected, request_stop, selected)
            installed.append(selected)
        except (NotImplementedError, RuntimeError, ValueError):
            continue
    try:
        return await supervisor.run()
    finally:
        for selected in installed:
            loop.remove_signal_handler(selected)


@app.callback()
def main() -> None:
    """QuantForge commands remain non-ordering unless a future audited boundary says otherwise."""


@app.command("safety-status")
def safety_status(as_json: bool = typer.Option(False, "--json")) -> None:
    """Print non-secret trading safety state."""

    settings = get_settings()
    result = LiveSubmissionGuard.evaluate(settings)
    payload = {
        "trading_mode": settings.trading_mode.value,
        "live_submission_allowed": result.allowed,
        "failed_live_gates": list(result.failures),
        "credentials_configured": settings.upbit_access_key is not None,
    }
    if as_json:
        typer.echo(json.dumps(payload, sort_keys=True))
        return
    typer.echo(f"Trading mode: {payload['trading_mode']}")
    typer.echo(f"Live submission allowed: {payload['live_submission_allowed']}")
    typer.echo(f"Failed live gates: {', '.join(result.failures) or 'none'}")


@app.command("paper-recovery-status")
def paper_recovery_status(
    checkpoint: Annotated[Path, typer.Option(help="Paper recovery checkpoint JSON")],
) -> None:
    """Inspect whether a stopped paper checkpoint is eligible for human review."""

    try:
        parsed = read_realtime_paper_recovery_checkpoint(checkpoint)
    except (PaperRecoveryIntegrityError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="--checkpoint") from exc
    eligible = parsed.clean_shutdown and parsed.recovery_blocked
    review_error = None
    clearance = None
    if eligible:
        try:
            clearance = validate_paper_recovery_clearance(
                parsed,
                verified_at_utc=datetime.now(UTC),
            )
        except (PaperRecoveryReviewError, ValueError) as exc:
            eligible = False
            review_error = str(exc)

    pending = pending_paper_recovery_acknowledgement_path(
        checkpoint,
        parsed.checkpoint_hash,
    )
    typer.echo(
        json.dumps(
            {
                "schema_version": parsed.schema_version,
                "checkpoint": str(checkpoint.resolve()),
                "checkpoint_hash": parsed.checkpoint_hash,
                "clean_shutdown": parsed.clean_shutdown,
                "recovery_blocked": parsed.recovery_blocked,
                "eligible_for_acknowledgement": eligible,
                "review_error": review_error,
                "broker_orders": len(parsed.broker.orders),
                "broker_fills": len(parsed.broker.fills),
                "verified_ledgers": (
                    clearance.verified_ledger_count if clearance is not None else None
                ),
                "pending_acknowledgement": str(pending.resolve()),
                "pending_acknowledgement_exists": pending.exists(),
                "paper_only": True,
                "network_used": False,
                "order_submission_available": False,
                "block_cleared": False,
            },
            sort_keys=True,
        )
    )


@app.command("approve-paper-recovery")
def approve_paper_recovery(
    checkpoint: Annotated[Path, typer.Option(help="Clean, blocked paper checkpoint JSON")],
    reviewer_ref: Annotated[
        str,
        typer.Option(help="Pseudonymous 16-character lowercase hexadecimal reviewer reference"),
    ],
    approval_reference: Annotated[
        str,
        typer.Option(help="Reviewed ticket or local approval reference"),
    ],
    reason: Annotated[str, typer.Option(help="Non-secret human review rationale")],
    confirmation: Annotated[
        str,
        typer.Option(help=f"Exact phrase: {PAPER_RECOVERY_CONFIRMATION}"),
    ],
    valid_for_minutes: int = typer.Option(60, min=1, max=1440),
) -> None:
    """Approve one paper-only recovery; the runtime must still revalidate it on restart."""

    try:
        parsed = read_realtime_paper_recovery_checkpoint(checkpoint)
        acknowledgement = create_paper_recovery_acknowledgement(
            parsed,
            reviewer_ref=reviewer_ref,
            approval_reference=approval_reference,
            reason=reason,
            confirmation=confirmation,
            created_at_utc=datetime.now(UTC),
            valid_for=timedelta(minutes=valid_for_minutes),
        )
        destination = pending_paper_recovery_acknowledgement_path(
            checkpoint,
            parsed.checkpoint_hash,
        )
        write_paper_recovery_acknowledgement(acknowledgement, destination)
    except (PaperRecoveryIntegrityError, PaperRecoveryReviewError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="--checkpoint") from exc

    typer.echo(
        json.dumps(
            {
                "schema_version": acknowledgement.schema_version,
                "acknowledgement": str(destination.resolve()),
                "acknowledgement_hash": acknowledgement.acknowledgement_hash,
                "checkpoint_hash": acknowledgement.checkpoint_hash,
                "valid_until_utc": acknowledgement.valid_until_utc.isoformat(),
                "human_reviewed": True,
                "paper_only": True,
                "network_used": False,
                "order_submission_available": False,
                "block_cleared": False,
                "next_runtime_start_must_revalidate": True,
            },
            sort_keys=True,
        )
    )


@app.command("collect-public")
def collect_public(
    markets: str = typer.Option("KRW-BTC", help="Comma-separated uppercase market codes"),
    streams: str = typer.Option("ticker,trade,orderbook", help="Public stream names"),
    max_messages: int = typer.Option(100, min=1, help="Stop after this many valid messages"),
    output: Annotated[Path, typer.Option(help="Append-only raw Parquet root")] = DEFAULT_RAW_OUTPUT,
) -> None:
    """Collect a finite keyless public sample; this command has no order or auth path."""

    selected_markets = tuple(item.strip() for item in markets.split(",") if item.strip())
    selected_streams = tuple(item.strip() for item in streams.split(",") if item.strip())
    allowed_streams = {"ticker", "trade", "orderbook"}
    if not selected_markets:
        raise typer.BadParameter("at least one market is required", param_hint="--markets")
    if not selected_streams or any(item not in allowed_streams for item in selected_streams):
        raise typer.BadParameter(
            "streams must contain only ticker, trade, or orderbook", param_hint="--streams"
        )
    subscriptions = tuple(
        UpbitSubscription(cast(PublicStreamType, stream), selected_markets)
        for stream in selected_streams
    )
    writer = ParquetRawEventWriter(output)
    removed_orphans = cleanup_orphan_temp_files(output)
    manifests = []

    async def on_event(event: EventEnvelope) -> None:
        manifests.extend(writer.append(event))

    async def run_collection() -> int:
        client = UpbitPublicWebSocketClient(subscriptions, on_event)
        return await client.run(max_messages=max_messages)

    try:
        accepted = asyncio.run(run_collection())
    finally:
        manifests.extend(writer.close())
    typer.echo(
        json.dumps(
            {
                "accepted_messages": accepted,
                "parquet_files": len(manifests),
                "orphan_temp_files_removed": removed_orphans,
                "output": str(output.resolve()),
                "authentication_used": False,
                "order_submission_available": False,
            },
            sort_keys=True,
        )
    )


@app.command("index-raw-quality")
def index_raw_quality(
    input_root: Annotated[
        Path, typer.Option(help="Active public raw Parquet root")
    ] = DEFAULT_PAPER_RAW_OUTPUT,
    index: Annotated[
        Path, typer.Option(help="Bounded incremental quality index output")
    ] = DEFAULT_RAW_QUALITY_INDEX,
    storage_label: str = typer.Option(
        "local-paper-data", help="Non-secret display label for the paper-data filesystem"
    ),
    reverify_after_seconds: int = typer.Option(
        86_400,
        min=0,
        max=31_536_000,
        help="Re-check cached file checksums after this many seconds",
    ),
) -> None:
    """Incrementally verify public raw files; no authentication or order path exists."""

    result = update_raw_data_quality_index(
        input_root,
        index,
        storage_label=storage_label,
        reverify_after_seconds=reverify_after_seconds,
    )
    typer.echo(
        json.dumps(
            {
                "schema_version": result.schema_version,
                "measurement_status": result.measurement_status,
                "active_files": result.active_file_count,
                "active_rows": result.active_row_count,
                "active_bytes": result.active_byte_size,
                "scanned_files": result.scanned_file_count,
                "reused_files": result.reused_file_count,
                "retired_cache_entries": result.retired_cache_entry_count,
                "manifest_set_sha256": result.manifest_set_sha256,
                "observed_markets": len(result.markets),
                "research_eligible_markets": len(result.research_readiness.eligible_markets),
                "ready_for_new_preregistration": (
                    result.research_readiness.ready_for_new_preregistration
                ),
                "current_experiment_authorized": False,
                "authentication_used": False,
                "order_submission_available": False,
                "index": str(index.resolve()),
            },
            sort_keys=True,
        )
    )


@app.command("run-paper")
def run_paper(
    markets: str = typer.Option(
        "KRW-BTC", help="Comma-separated uppercase KRW market codes or ALL-KRW"
    ),
    streams: str = typer.Option("ticker,trade,orderbook", help="Public stream names"),
    focus_markets: int = typer.Option(
        20,
        min=1,
        max=100,
        help="Detailed trade/orderbook markets when ALL-KRW is selected",
    ),
    duration_seconds: int = typer.Option(
        0,
        min=0,
        max=604_800,
        help="Stop after this many seconds; zero runs until stopped",
    ),
    max_messages: int = typer.Option(
        0,
        min=0,
        help="Stop after this many valid messages; zero is unlimited",
    ),
    heartbeat_seconds: int = typer.Option(15, min=1, max=300),
    flush_seconds: int = typer.Option(60, min=1, max=3600),
    storage_label: str = typer.Option(
        "local-paper-data", help="Non-secret display label for the paper-data filesystem"
    ),
    storage_retention_days: int = typer.Option(30, min=1, max=3650),
    storage_max_gib: int = typer.Option(50, min=1, max=10_000),
    storage_min_free_gib: int = typer.Option(20, min=1, max=10_000),
    storage_maintenance_seconds: int = typer.Option(900, min=60, max=86_400),
    storage_compaction_min_files: int = typer.Option(4, min=2, max=1000),
    storage_compaction_target_rows: int = typer.Option(250_000, min=1000),
    raw_output: Annotated[
        Path, typer.Option(help="Append-only public raw Parquet root")
    ] = DEFAULT_PAPER_RAW_OUTPUT,
    output_root: Annotated[
        Path, typer.Option(help="Secret-free runtime export root")
    ] = DEFAULT_OPERATIONS_OUTPUT,
) -> None:
    """Run supervised keyless public collection with every live/order gate closed."""

    dynamic_all_krw = markets.strip().upper() == "ALL-KRW"
    selected_markets = tuple(item.strip() for item in markets.split(",") if item.strip())
    selected_streams = tuple(item.strip() for item in streams.split(",") if item.strip())
    allowed_streams = {"ticker", "trade", "orderbook"}
    if not dynamic_all_krw and (
        not selected_markets or any(not market.startswith("KRW-") for market in selected_markets)
    ):
        raise typer.BadParameter(
            "paper runtime accepts uppercase KRW market codes only", param_hint="--markets"
        )
    if not selected_streams or any(item not in allowed_streams for item in selected_streams):
        raise typer.BadParameter(
            "streams must contain only ticker, trade, or orderbook", param_hint="--streams"
        )
    universe = None
    scanner = None
    subscription_builder = None
    recovery_path = None
    if dynamic_all_krw:
        try:
            universe = UpbitPublicMarketCatalog().fetch_krw_universe(focus_limit=focus_markets)
        except UpbitMarketCatalogError as exc:
            raise typer.BadParameter(str(exc), param_hint="--markets") from exc
        selected_markets = universe.monitored_markets
        scanner = RealtimeUniverseScanner(
            selected_markets,
            eligible_markets=universe.eligible_markets,
            initial_focus_markets=universe.initial_focus_markets,
            warning_markets=universe.warning_markets,
            caution_markets=universe.caution_markets,
            market_set_hash=universe.market_set_hash,
            policy=RealtimeUniversePolicy(focus_limit=focus_markets),
        )

        def build_dynamic_subscriptions(
            selected_focus: Sequence[str],
        ) -> tuple[UpbitSubscription, ...]:
            return build_tiered_public_subscriptions(
                selected_markets,
                selected_focus,
                selected_streams,
                orderbook_depth=5,
            )

        subscription_builder = build_dynamic_subscriptions
        subscriptions = subscription_builder(universe.initial_focus_markets)
        recovery_path = (
            raw_output.parent
            / "state"
            / f"realtime-paper-recovery-{universe.market_set_hash[:16]}.json"
        )
    else:
        subscriptions = tuple(
            UpbitSubscription(cast(PublicStreamType, stream), selected_markets)
            for stream in selected_streams
        )

    def client_factory(
        on_event: Callable[[EventEnvelope], Awaitable[None]],
        on_error: Callable[[UpbitAdapterError], Awaitable[None]],
    ) -> UpbitPublicWebSocketClient:
        return UpbitPublicWebSocketClient(subscriptions, on_event, on_error=on_error)

    policy = PaperRuntimePolicy(
        heartbeat_seconds=float(heartbeat_seconds),
        flush_seconds=float(flush_seconds),
        storage_label=storage_label,
        storage_policy=RawStoragePolicy(
            retention_days=storage_retention_days,
            max_bytes=storage_max_gib * 1024**3,
            min_free_bytes=storage_min_free_gib * 1024**3,
            maintenance_interval_seconds=float(storage_maintenance_seconds),
            compaction_min_files=storage_compaction_min_files,
            compaction_target_rows=storage_compaction_target_rows,
        ),
        duration_seconds=float(duration_seconds) if duration_seconds else None,
        max_messages=max_messages or None,
    )
    supervisor = PaperRuntimeSupervisor(
        settings=get_settings(),
        markets=selected_markets,
        streams=selected_streams,
        raw_output=raw_output,
        output_root=output_root,
        policy=policy,
        client_factory=client_factory,
        universe_scanner=scanner,
        subscription_builder=subscription_builder,
        recovery_path=recovery_path,
    )
    snapshot = asyncio.run(_run_paper_with_signals(supervisor))
    typer.echo(
        json.dumps(
            {
                "state": snapshot.state,
                "run_id": str(snapshot.run_id),
                "accepted_messages": snapshot.accepted_messages,
                "committed_rows": snapshot.committed_rows,
                "retained_rows": snapshot.retained_rows,
                "retained_files": snapshot.retained_files,
                "retained_bytes": snapshot.retained_bytes,
                "storage_label": snapshot.storage_label,
                "storage_retention_days": snapshot.storage_retention_days,
                "storage_max_bytes": snapshot.storage_max_bytes,
                "storage_reclaimed_bytes": snapshot.storage_reclaimed_bytes,
                "disk_free_bytes": snapshot.disk_free_bytes,
                "market_scope": snapshot.market_scope,
                "monitored_market_count": len(snapshot.markets),
                "focused_market_count": len(snapshot.focused_markets),
                "warning_market_count": snapshot.warning_market_count,
                "parser_errors": snapshot.parser_errors,
                "reconnects": snapshot.reconnects,
                "runtime_snapshot": str((output_root / "ops" / "paper-runtime.json").resolve()),
                "paper_monitor": str((output_root / "ops" / "paper-monitor.html").resolve()),
                "authentication_used": snapshot.authentication_used,
                "private_network_used": snapshot.private_network_used,
                "order_submission_available": snapshot.order_submission_available,
                "live_submission_allowed": snapshot.live_submission_allowed,
            },
            sort_keys=True,
        )
    )


@app.command("paper-status")
def paper_status(
    snapshot: Annotated[
        Path, typer.Option(help="Paper runtime snapshot JSON")
    ] = DEFAULT_PAPER_RUNTIME_SNAPSHOT,
    require_fresh_seconds: int | None = typer.Option(
        None,
        min=1,
        help="Exit nonzero unless a running heartbeat is this fresh",
    ),
) -> None:
    """Read the latest Secret-free paper runtime heartbeat without network access."""

    if not snapshot.is_file():
        raise typer.BadParameter("paper runtime snapshot was not found", param_hint="--snapshot")
    parsed = read_paper_runtime_snapshot(snapshot)
    now_utc = datetime.now(UTC)
    age_seconds = max(0.0, (now_utc - parsed.updated_at_utc).total_seconds())
    event_age_seconds = (
        max(0.0, (now_utc - parsed.last_event_at_utc).total_seconds())
        if parsed.last_event_at_utc is not None
        else None
    )
    healthy = (
        parsed.state is PaperRuntimeState.RUNNING
        and parsed.websocket_connected
        and event_age_seconds is not None
        and (
            parsed.disk_free_bytes is None
            or parsed.storage_min_free_bytes == 0
            or parsed.disk_free_bytes >= parsed.storage_min_free_bytes
        )
    )
    if require_fresh_seconds is not None:
        healthy = (
            healthy
            and age_seconds <= require_fresh_seconds
            and event_age_seconds is not None
            and event_age_seconds <= require_fresh_seconds
        )
    typer.echo(
        json.dumps(
            {
                "state": parsed.state,
                "run_id": str(parsed.run_id),
                "heartbeat_age_seconds": round(age_seconds, 3),
                "market_event_age_seconds": (
                    round(event_age_seconds, 3) if event_age_seconds is not None else None
                ),
                "accepted_messages": parsed.accepted_messages,
                "committed_rows": parsed.committed_rows,
                "retained_rows": parsed.retained_rows,
                "retained_files": parsed.retained_files,
                "retained_bytes": parsed.retained_bytes,
                "storage_label": parsed.storage_label,
                "storage_retention_days": parsed.storage_retention_days,
                "storage_max_bytes": parsed.storage_max_bytes,
                "storage_reclaimed_bytes": parsed.storage_reclaimed_bytes,
                "disk_free_bytes": parsed.disk_free_bytes,
                "parser_errors": parsed.parser_errors,
                "reconnects": parsed.reconnects,
                "websocket_connected": parsed.websocket_connected,
                "healthy": healthy,
                "authentication_used": parsed.authentication_used,
                "order_submission_available": parsed.order_submission_available,
                "live_submission_allowed": parsed.live_submission_allowed,
            },
            sort_keys=True,
        )
    )
    if require_fresh_seconds is not None and not healthy:
        raise typer.Exit(code=1)


@app.command("benchmark-realtime")
def benchmark_realtime(
    input_root: Annotated[
        Path, typer.Option(help="Checksummed raw Parquet root to replay without network access")
    ] = DEFAULT_PAPER_RAW_OUTPUT,
    max_events: Annotated[int, typer.Option(min=1)] = 10_000,
    processing_budget_ms: Annotated[float, typer.Option(min=0.001)] = 5.0,
) -> None:
    """Benchmark the HOLD-only incremental path over verified retained public events."""

    events = sorted(
        read_raw_events(input_root),
        key=lambda event: (
            event.received_at_utc,
            str(event.connection_id),
            event.local_sequence,
            str(event.event_id),
        ),
    )
    if not events:
        raise typer.BadParameter("no verified raw events were found", param_hint="--input-root")
    selected = events[:max_events]
    markets = tuple(sorted({event.market for event in selected}))
    pipeline = RealtimePaperPipeline(
        markets,
        processing_budget_ms=processing_budget_ms,
    )
    started = perf_counter()
    for event in selected:
        pipeline.process(event)
    elapsed_seconds = max(perf_counter() - started, 1e-12)
    snapshot = pipeline.snapshot(generated_at_utc=datetime.now(UTC))
    typer.echo(
        json.dumps(
            {
                "processed_events": snapshot.processed_events,
                "feature_frames": snapshot.feature_frames,
                "inference_ready_frames": snapshot.inference_ready_frames,
                "processing_latency_p50_ms": snapshot.processing_latency_p50_ms,
                "processing_latency_p95_ms": snapshot.processing_latency_p95_ms,
                "processing_latency_p99_ms": snapshot.processing_latency_p99_ms,
                "processing_latency_max_ms": snapshot.processing_latency_max_ms,
                "processing_budget_ms": snapshot.processing_budget_ms,
                "processing_budget_breaches": snapshot.processing_budget_breaches,
                "replay_events_per_second": len(selected) / elapsed_seconds,
                "decision_state": snapshot.decision_state,
                "decision_reason": snapshot.decision_reason,
                "approved_model_available": snapshot.approved_model_available,
                "strategy_order_capability": snapshot.strategy_order_capability,
                "private_network_used": snapshot.private_network_used,
                "order_submission_available": snapshot.order_submission_available,
                "live_submission_allowed": snapshot.live_submission_allowed,
            },
            sort_keys=True,
        )
    )


@app.command("benchmark-paper-decision")
def benchmark_paper_decision(
    input_root: Annotated[
        Path, typer.Option(help="Checksummed raw Parquet root to replay without network access")
    ] = DEFAULT_PAPER_RAW_OUTPUT,
    max_events: Annotated[int, typer.Option(min=1)] = 10_000,
) -> None:
    """Benchmark the unapproved neutral model through the complete paper decision boundary."""

    events = sorted(
        read_raw_events(input_root),
        key=lambda event: (
            event.received_at_utc,
            str(event.connection_id),
            event.local_sequence,
            str(event.event_id),
        ),
    )
    if not events:
        raise typer.BadParameter("no verified raw events were found", param_hint="--input-root")
    selected = events[:max_events]
    markets = tuple(sorted({event.market for event in selected}))
    features = RealtimePaperPipeline(markets)
    decision = RealtimePaperOrchestrator(markets)
    event_latencies_ms: list[float] = []
    started = perf_counter()
    for event in selected:
        event_started = perf_counter()
        frame = features.process(event)
        decision.process(event, frame)
        event_latencies_ms.append((perf_counter() - event_started) * 1_000)
    elapsed_seconds = max(perf_counter() - started, 1e-12)
    feature_snapshot = features.snapshot(generated_at_utc=selected[-1].received_at_utc)
    decision_snapshot = decision.snapshot(generated_at_utc=selected[-1].received_at_utc)
    ordered = sorted(event_latencies_ms)
    p99_index = min(len(ordered) - 1, math.ceil(len(ordered) * 0.99) - 1)
    typer.echo(
        json.dumps(
            {
                "processed_events": decision_snapshot.processed_events,
                "feature_ready_frames": decision_snapshot.feature_ready_frames,
                "inference_frames": decision_snapshot.inference_frames,
                "feature_latency_p99_ms": feature_snapshot.processing_latency_p99_ms,
                "decision_latency_p99_ms": decision_snapshot.decision_latency_p99_ms,
                "end_to_end_latency_p99_ms": ordered[p99_index],
                "end_to_end_latency_max_ms": max(ordered),
                "replay_events_per_second": len(selected) / elapsed_seconds,
                "model_release_status": decision_snapshot.model_release_status,
                "model_approval_valid": decision_snapshot.model_approval_valid,
                "paper_order_simulation_enabled": (
                    decision_snapshot.paper_order_simulation_enabled
                ),
                "paper_recovery_status": decision_snapshot.recovery_status.value,
                "paper_recovery_blocked": decision_snapshot.recovery_blocked,
                "decision_state": decision_snapshot.decision_state,
                "strategy_trade_proposals": decision_snapshot.strategy_trade_proposals,
                "risk_approvals": decision_snapshot.risk_approvals,
                "paper_orders": decision_snapshot.paper_orders,
                "paper_fills": decision_snapshot.paper_fills,
                "authentication_used": decision_snapshot.authentication_used,
                "private_network_used": decision_snapshot.private_network_used,
                "real_order_submission_available": (
                    decision_snapshot.real_order_submission_available
                ),
                "live_submission_allowed": decision_snapshot.live_submission_allowed,
            },
            sort_keys=True,
        )
    )


@app.command("replay-raw")
def replay_raw(
    input_root: Annotated[
        Path, typer.Option(help="Checksummed raw Parquet root")
    ] = DEFAULT_REPLAY_INPUT,
    output_root: Annotated[
        Path, typer.Option(help="Redacted data-quality snapshot directory")
    ] = DEFAULT_DATA_QUALITY_OUTPUT,
) -> None:
    """Verify and deterministically replay stored public events without network access."""

    events = read_raw_events(input_root)
    if not events:
        raise typer.BadParameter("no verified raw events were found", param_hint="--input-root")

    def fingerprint_output(item: EventEnvelope | DataGap, clock: VirtualClock) -> str:
        del clock
        return item.fingerprint() if isinstance(item, DataGap) else item.raw_payload_hash

    replay = ReplayEngine().run(events, fingerprint_output)
    snapshot = DataQualitySnapshot.from_phase2(replay, [], [])
    snapshot_path = write_data_quality_snapshot(snapshot, output_root)
    typer.echo(
        json.dumps(
            {
                "dataset_hash": replay.dataset_hash,
                "output_hash": replay.output_hash,
                "verified_inputs": replay.total_inputs,
                "delivered_events": replay.delivered_events,
                "skipped_duplicates": replay.skipped_duplicates,
                "snapshot": str(snapshot_path.resolve()),
                "network_used": False,
                "authentication_used": False,
                "order_submission_available": False,
            },
            sort_keys=True,
        )
    )


@app.command("assess-scalping-research")
def assess_scalping_research(
    source_revision: Annotated[
        str,
        typer.Option(help="Exact committed source revision used for the research assessment"),
    ],
    plan_path: Annotated[
        Path, typer.Option(help="Committed preregistered scalping experiment plan")
    ] = DEFAULT_SCALPING_PLAN,
    input_root: Annotated[
        Path, typer.Option(help="Checksummed public raw Parquet root")
    ] = DEFAULT_PAPER_RAW_OUTPUT,
    output_root: Annotated[
        Path, typer.Option(help="Codex research report root")
    ] = DEFAULT_CODEX_RESEARCH_OUTPUT,
    scratch_root: Annotated[
        Path | None,
        typer.Option(help="Temporary external-sort root; runs are removed on exit"),
    ] = None,
    maximum_elapsed_seconds: Annotated[
        float,
        typer.Option(min=1.0, help="Fail-closed inventory wall-time budget"),
    ] = 900.0,
) -> None:
    """Fingerprint detailed public data and retain an insufficient-data result."""

    def report_progress(item: RawResearchInventoryProgress) -> None:
        if (
            item.phase == "scan"
            and item.completed_units not in {1, item.total_units}
            and item.completed_units % 10 != 0
        ):
            return
        typer.echo(
            json.dumps(
                {
                    "phase": item.phase,
                    "completed_units": item.completed_units,
                    "total_units": item.total_units,
                    "selected_event_count": item.selected_event_count,
                },
                sort_keys=True,
            ),
            err=True,
        )

    plan = load_scalping_experiment_plan(plan_path)
    try:
        inventory = scan_raw_event_research_inventory(
            input_root,
            maximum_exchange_timestamp_utc=(plan.dataset_selection.maximum_exchange_timestamp_utc),
            maximum_received_at_utc=plan.dataset_selection.maximum_received_at_utc,
            exclude_marked_duplicates=plan.dataset_selection.exclude_marked_duplicates,
            exclude_quality_flagged_events=(plan.dataset_selection.exclude_quality_flagged_events),
            scratch_root=scratch_root,
            maximum_elapsed_seconds=maximum_elapsed_seconds,
            progress=report_progress,
        )
    except RawResearchInventoryTimeout as exc:
        typer.echo(
            json.dumps(
                {
                    "status": "TIMEOUT",
                    "reason": str(exc),
                    "report_written": False,
                    "trial_count": 0,
                    "final_holdout_used": False,
                    "authentication_used": False,
                    "order_network_used": False,
                    "real_orders_executed": False,
                },
                sort_keys=True,
            ),
            err=True,
        )
        raise typer.Exit(code=2) from exc
    sufficiency = evaluate_scalping_data_sufficiency(plan, inventory)
    if sufficiency.meets_requirements:
        typer.echo(
            json.dumps(
                {
                    "dataset_hash": inventory.dataset_hash,
                    "detailed_public_events": inventory.selected_event_count,
                    "eligible_markets": list(sufficiency.eligible_markets),
                    "meets_preregistered_minimum": True,
                    "report_written": False,
                    "final_holdout_used": False,
                    "authentication_used": False,
                    "order_network_used": False,
                    "real_orders_executed": False,
                },
                sort_keys=True,
            )
        )
        return

    generated_at_utc = datetime.now(UTC)
    report = create_blocked_scalping_report(
        plan,
        inventory,
        sufficiency,
        source_revision=source_revision,
        generated_at_utc=generated_at_utc,
    )
    ledger = blocked_experiment_ledger(
        plan,
        inventory,
        sufficiency,
        source_revision=source_revision,
        generated_at_utc=generated_at_utc,
    )
    markdown_path, json_path, ledger_path = write_scalping_research_bundle(
        report, ledger, output_root
    )
    typer.echo(
        json.dumps(
            {
                "decision": report.decision,
                "dataset_hash": inventory.dataset_hash,
                "detailed_public_events": inventory.selected_event_count,
                "eligible_markets": list(sufficiency.eligible_markets),
                "meets_preregistered_minimum": False,
                "report": str(markdown_path.resolve()),
                "manifest": str(json_path.resolve()),
                "ledger": str(ledger_path.resolve()),
                "trial_count": 0,
                "final_holdout_used": False,
                "authentication_used": False,
                "order_network_used": False,
                "real_orders_executed": False,
            },
            sort_keys=True,
        )
    )


@app.command("plan-scalping-trials")
def plan_scalping_trials(
    source_revision: Annotated[
        str,
        typer.Option(help="Exact committed bounded-runner revision"),
    ],
    output_path: Annotated[
        Path,
        typer.Option(help="New immutable preregistered trial execution plan"),
    ],
    plan_path: Annotated[
        Path,
        typer.Option(help="Committed scalping experiment plan"),
    ] = DEFAULT_SCALPING_CURRENT_PLAN,
    registration_ledger_path: Annotated[
        Path,
        typer.Option(help="Committed registration-only experiment ledger"),
    ] = DEFAULT_SCALPING_CURRENT_LEDGER,
    input_root: Annotated[
        Path,
        typer.Option(help="Checksummed public raw Parquet root"),
    ] = DEFAULT_PAPER_RAW_OUTPUT,
    scratch_root: Annotated[
        Path | None,
        typer.Option(help="Temporary external-sort root; runs are removed on exit"),
    ] = None,
    maximum_elapsed_seconds: Annotated[
        float,
        typer.Option(min=1.0, help="Fail-closed inventory wall-time budget"),
    ] = 900.0,
) -> None:
    """Fingerprint data and close every preregistered non-holdout work unit."""

    plan = load_scalping_experiment_plan(plan_path)
    registration_snapshot = read_experiment_ledger(registration_ledger_path)
    try:
        validate_scalping_trial_registration_seed(plan, registration_snapshot)
    except (ScalpingResearchError, ValueError) as exc:
        typer.echo(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": str(exc),
                    "inventory_scanned": False,
                    "execution_plan_written": False,
                    "trial_count": 0,
                    "final_holdout_used": False,
                    "authentication_used": False,
                    "order_network_used": False,
                    "real_orders_executed": False,
                },
                sort_keys=True,
            ),
            err=True,
        )
        raise typer.Exit(code=2) from exc

    def report_progress(item: RawResearchInventoryProgress) -> None:
        if (
            item.phase == "scan"
            and item.completed_units not in {1, item.total_units}
            and item.completed_units % 10 != 0
        ):
            return
        typer.echo(
            json.dumps(
                {
                    "phase": item.phase,
                    "completed_units": item.completed_units,
                    "total_units": item.total_units,
                    "selected_event_count": item.selected_event_count,
                },
                sort_keys=True,
            ),
            err=True,
        )

    try:
        inventory = scan_raw_event_research_inventory(
            input_root,
            maximum_exchange_timestamp_utc=(plan.dataset_selection.maximum_exchange_timestamp_utc),
            maximum_received_at_utc=plan.dataset_selection.maximum_received_at_utc,
            exclude_marked_duplicates=plan.dataset_selection.exclude_marked_duplicates,
            exclude_quality_flagged_events=(plan.dataset_selection.exclude_quality_flagged_events),
            scratch_root=scratch_root,
            maximum_elapsed_seconds=maximum_elapsed_seconds,
            progress=report_progress,
        )
        execution_plan = create_scalping_trial_execution_plan(
            plan,
            registration_snapshot,
            inventory,
            source_revision=source_revision,
            created_at_utc=datetime.now(UTC),
        )
        write_scalping_trial_execution_plan(execution_plan, output_path)
    except (RawResearchInventoryTimeout, ScalpingResearchError, ValueError) as exc:
        typer.echo(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": str(exc),
                    "execution_plan_written": False,
                    "trial_count": 0,
                    "final_holdout_used": False,
                    "authentication_used": False,
                    "order_network_used": False,
                    "real_orders_executed": False,
                },
                sort_keys=True,
            ),
            err=True,
        )
        raise typer.Exit(code=2) from exc
    typer.echo(
        json.dumps(
            {
                "status": "PREREGISTERED",
                "execution_plan": str(output_path.resolve()),
                "execution_plan_sha256": execution_plan.digest,
                "dataset_hash": execution_plan.dataset_hash,
                "eligible_markets": list(execution_plan.eligible_markets),
                "planned_trial_count": len(execution_plan.trials),
                "final_holdout_used": False,
                "authentication_used": False,
                "order_network_used": False,
                "real_orders_executed": False,
            },
            sort_keys=True,
        )
    )


@app.command("run-next-scalping-trial")
def run_next_scalping_trial_command(
    execution_plan_path: Annotated[
        Path,
        typer.Option(help="Committed immutable trial execution plan"),
    ],
    working_ledger_path: Annotated[
        Path,
        typer.Option(help="Durable Codex report ledger; never the registration seed"),
    ],
    plan_path: Annotated[
        Path,
        typer.Option(help="Committed scalping experiment plan"),
    ] = DEFAULT_SCALPING_CURRENT_PLAN,
    registration_ledger_path: Annotated[
        Path,
        typer.Option(help="Committed registration-only experiment ledger"),
    ] = DEFAULT_SCALPING_CURRENT_LEDGER,
    input_root: Annotated[
        Path,
        typer.Option(help="Checksummed public raw Parquet root"),
    ] = DEFAULT_PAPER_RAW_OUTPUT,
    artifact_root: Annotated[
        Path,
        typer.Option(help="Codex research trial artifact root"),
    ] = DEFAULT_CODEX_RESEARCH_OUTPUT,
) -> None:
    """Run exactly one next registered validation/test work unit and checkpoint it."""

    if working_ledger_path.resolve() == registration_ledger_path.resolve():
        raise typer.BadParameter("working ledger must not overwrite the registration seed")
    plan = load_scalping_experiment_plan(plan_path)
    execution_plan = load_scalping_trial_execution_plan(execution_plan_path)
    registration_snapshot = read_experiment_ledger(registration_ledger_path)
    outcome = run_next_scalping_trial(
        plan,
        execution_plan,
        registration_snapshot,
        working_ledger_path=working_ledger_path,
        artifact_root=artifact_root,
        input_root=input_root,
    )
    typer.echo(
        json.dumps(
            {
                "status": outcome.trial.status,
                "trial_id": str(outcome.trial.trial_id),
                "failure_reason": outcome.trial.failure_reason,
                "artifact": str(outcome.artifact_path.resolve())
                if outcome.artifact_path is not None
                else None,
                "ledger": str(outcome.ledger_path.resolve()),
                "completed_trial_count": outcome.completed_trial_count,
                "planned_trial_count": outcome.planned_trial_count,
                "final_holdout_used": False,
                "authentication_used": False,
                "order_network_used": False,
                "real_orders_executed": False,
            },
            sort_keys=True,
        )
    )
    if outcome.trial.status is TrialStatus.FAILED:
        raise typer.Exit(code=2)


@app.command("finalize-scalping-trials")
def finalize_scalping_trials_command(
    execution_plan_path: Annotated[
        Path,
        typer.Option(help="Committed immutable trial execution plan"),
    ],
    working_ledger_path: Annotated[
        Path,
        typer.Option(help="Completed Codex trial ledger to close"),
    ],
    closed_at_utc: Annotated[
        str,
        typer.Option(help="Explicit reproducible ISO-8601 UTC decision timestamp"),
    ],
    plan_path: Annotated[
        Path,
        typer.Option(help="Committed scalping experiment plan"),
    ] = DEFAULT_SCALPING_CURRENT_PLAN,
    registration_ledger_path: Annotated[
        Path,
        typer.Option(help="Committed registration-only experiment ledger"),
    ] = DEFAULT_SCALPING_CURRENT_LEDGER,
    artifact_root: Annotated[
        Path,
        typer.Option(help="Codex research trial artifact root"),
    ] = DEFAULT_CODEX_RESEARCH_OUTPUT,
    report_root: Annotated[
        Path,
        typer.Option(help="Codex final research report root"),
    ] = DEFAULT_CODEX_RESEARCH_OUTPUT,
) -> None:
    """Validate all registered units, retain REJECT, and close the experiment ledger."""

    if working_ledger_path.resolve() == registration_ledger_path.resolve():
        raise typer.BadParameter("working ledger must not overwrite the registration seed")
    try:
        decision_time = datetime.fromisoformat(closed_at_utc.replace("Z", "+00:00"))
    except ValueError as error:
        raise typer.BadParameter("closed-at-utc must be an ISO-8601 UTC timestamp") from error
    if decision_time.tzinfo is None or decision_time.utcoffset() != UTC.utcoffset(decision_time):
        raise typer.BadParameter("closed-at-utc must be an ISO-8601 UTC timestamp")
    plan = load_scalping_experiment_plan(plan_path)
    execution_plan = load_scalping_trial_execution_plan(execution_plan_path)
    registration_snapshot = read_experiment_ledger(registration_ledger_path)
    outcome = finalize_scalping_trial_experiment(
        plan,
        execution_plan,
        registration_snapshot,
        working_ledger_path=working_ledger_path,
        artifact_root=artifact_root,
        report_root=report_root,
        closed_at_utc=decision_time,
    )
    typer.echo(
        json.dumps(
            {
                "status": outcome.report.decision,
                "report_digest": outcome.report.digest,
                "report_json": str(outcome.report_json_path.resolve()),
                "report_markdown": str(outcome.report_markdown_path.resolve()),
                "ledger": str(outcome.ledger_path.resolve()),
                "ledger_chain_hash": outcome.ledger.chain_hash,
                "planned_trial_count": outcome.report.planned_trial_count,
                "succeeded_trial_count": outcome.report.succeeded_trial_count,
                "failed_trial_count": outcome.report.failed_trial_count,
                "final_holdout_used": False,
                "authentication_used": False,
                "order_network_used": False,
                "real_orders_executed": False,
                "automatic_promotion": False,
            },
            sort_keys=True,
        )
    )


@app.command("export-operations")
def export_operations(
    output_root: Annotated[
        Path, typer.Option(help="Secret-free operations export root")
    ] = DEFAULT_OPERATIONS_OUTPUT,
) -> None:
    """Write a redacted paper-operations snapshot without exchange or order access."""

    settings = get_settings()
    now_utc = datetime.now(UTC)
    output_root.mkdir(parents=True, exist_ok=True)
    context = create_operations_context(settings, now_utc=now_utc, export_root=output_root)
    snapshot = context.snapshot()
    disk_free = shutil.disk_usage(output_root.parent.resolve()).free
    snapshot = snapshot.model_copy(
        update={
            "generated_at_utc": now_utc,
            "system": snapshot.system.model_copy(update={"disk_free_bytes": disk_free}),
        }
    )
    destination = write_dashboard_snapshot(snapshot, output_root)
    typer.echo(
        json.dumps(
            {
                "snapshot": str(destination.resolve()),
                "schema_version": snapshot.schema_version,
                "trading_mode": snapshot.overview.trading_mode,
                "live_submission_allowed": snapshot.overview.live_submission_allowed,
                "authentication_used": False,
                "network_used": False,
                "order_submission_available": False,
            },
            sort_keys=True,
        )
    )


@app.command("backup-local")
def backup_local(
    sources: Annotated[
        list[Path], typer.Option("--source", help="Explicit workspace file or directory")
    ],
    source_revision: Annotated[
        str, typer.Option(help="Reviewed source revision recorded in the manifest")
    ],
    backup_root: Annotated[
        Path, typer.Option(help="Local development backup root")
    ] = DEFAULT_BACKUP_ROOT,
) -> None:
    """Create a checksummed local paper restore proof; this is not an encrypted backup."""

    manager = LocalBackupManager(Path.cwd())
    destination = manager.create(
        tuple(sources),
        backup_root,
        source_revision=source_revision,
        created_at_utc=datetime.now(UTC),
    )
    manifest = manager.verify(destination)
    typer.echo(
        json.dumps(
            {
                "backup": str(destination.resolve()),
                "backup_id": manifest.backup_id,
                "object_count": len(manifest.objects),
                "verified": True,
                "trading_mode": manifest.trading_mode,
                "encrypted_by_external_storage": manifest.encrypted_by_external_storage,
                "production_ready": False,
            },
            sort_keys=True,
        )
    )


@app.command("verify-backup")
def verify_backup(
    backup: Annotated[Path, typer.Option(help="Backup directory containing manifest.json")],
) -> None:
    """Verify every object and aggregate hash in a local backup proof."""

    manifest = LocalBackupManager(Path.cwd()).verify(backup)
    typer.echo(
        json.dumps(
            {
                "backup_id": manifest.backup_id,
                "object_count": len(manifest.objects),
                "verified": True,
                "objectives_measured": manifest.objectives_measured,
                "production_ready": False,
            },
            sort_keys=True,
        )
    )


@app.command("restore-drill")
def restore_drill(
    backup: Annotated[Path, typer.Option(help="Verified local backup directory")],
    target: Annotated[Path, typer.Option(help="New or empty isolated restore directory")],
) -> None:
    """Restore into an empty paper-only directory without credentials or network access."""

    manifest = LocalBackupManager(Path.cwd()).restore_drill(backup, target)
    typer.echo(
        json.dumps(
            {
                "backup_id": manifest.backup_id,
                "target": str(target.resolve()),
                "paper_only_marker": str((target / "RESTORE_PAPER_ONLY").resolve()),
                "network_used": False,
                "order_submission_available": False,
            },
            sort_keys=True,
        )
    )


@app.command("validate-automation-report")
def validate_automation_report(
    report: Annotated[Path, typer.Option(help="Automation report manifest JSON")],
    workspace_root: Annotated[
        Path, typer.Option(help="Checkout root used for worktree verification")
    ] = Path("."),
    allowlist: Annotated[
        Path, typer.Option(help="Reviewed automation write allowlist")
    ] = DEFAULT_AUTOMATION_ALLOWLIST,
) -> None:
    """Validate a Secret-free report and its actor/worktree write boundary."""

    parsed = load_report(report)
    contract = load_write_allowlist(allowlist)
    worktree = assert_report_boundary(parsed, contract, workspace_root)
    typer.echo(
        json.dumps(
            {
                "actor": parsed.actor,
                "outcome": parsed.outcome,
                "report": parsed.report_path,
                "schema_version": parsed.schema_version,
                "writes_allowed": True,
                "dedicated_worktree": worktree.dedicated if worktree else False,
                "branch": worktree.branch if worktree else None,
                "network_used": False,
                "order_submission_available": False,
            },
            sort_keys=True,
        )
    )


@app.command("validate-automation-trigger")
def validate_automation_trigger(
    trigger: Annotated[Path, typer.Option(help="Work-to-Codex trigger JSON")],
    allowlist: Annotated[
        Path, typer.Option(help="Reviewed automation write allowlist")
    ] = DEFAULT_AUTOMATION_ALLOWLIST,
) -> None:
    """Validate a structured trigger without executing its untrusted evidence."""

    parsed = load_trigger(trigger)
    contract = load_write_allowlist(allowlist)
    assert_paths_allowed(AutomationActor.CODEX, parsed.requested_write_paths, contract)
    typer.echo(
        json.dumps(
            {
                "schema_version": parsed.schema_version,
                "requested_skill": parsed.requested_skill,
                "requested_writes_allowed": True,
                "operator_approval_required": parsed.operator_approval_required,
                "network_used": False,
                "order_submission_available": False,
            },
            sort_keys=True,
        )
    )


@app.command("validate-live-readiness")
def validate_live_readiness(
    evidence: Annotated[Path, typer.Option(help="Secret-free readiness evidence JSON")],
    policy: Annotated[
        Path, typer.Option(help="Reviewed readiness threshold policy")
    ] = DEFAULT_READINESS_POLICY,
    output_root: Annotated[
        Path, typer.Option(help="Read-only readiness report export root")
    ] = DEFAULT_OPERATIONS_OUTPUT,
    evaluated_at_utc: Annotated[
        str | None,
        typer.Option(help="Optional reproducible UTC ISO-8601 evaluation time"),
    ] = None,
) -> None:
    """Classify manual-canary review readiness without activating or ordering anything."""

    evaluation_time = None
    if evaluated_at_utc is not None:
        try:
            evaluation_time = datetime.fromisoformat(evaluated_at_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            raise typer.BadParameter(
                "evaluated-at-utc must be an ISO-8601 timestamp", param_hint="--evaluated-at-utc"
            ) from exc
    parsed_evidence = load_readiness_evidence(evidence)
    parsed_policy = load_readiness_policy(policy)
    report = ReadinessEvaluator().evaluate(
        parsed_evidence,
        parsed_policy,
        evaluated_at_utc=evaluation_time,
    )
    destination = write_readiness_report(report, output_root)
    typer.echo(
        json.dumps(
            {
                "status": report.status,
                "report": str(destination.resolve()),
                "human_approval_required": report.human_approval_required,
                "activation_performed": report.activation_performed,
                "network_used": report.safety.order_network_used,
                "order_submission_available": False,
                "runtime_settings_changed": report.safety.runtime_settings_changed,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    app()

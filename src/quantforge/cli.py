"""Operator-safe command line interface."""

import asyncio
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
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
from quantforge.exchange.upbit.public_ws import UpbitPublicWebSocketClient
from quantforge.exchange.upbit.subscriptions import PublicStreamType, UpbitSubscription
from quantforge.operations import (
    LocalBackupManager,
    create_operations_context,
    write_dashboard_snapshot,
)
from quantforge.replay import ReplayEngine, VirtualClock
from quantforge.runtime import DataQualitySnapshot, LiveSubmissionGuard, write_data_quality_snapshot
from quantforge.storage import (
    ParquetRawEventWriter,
    cleanup_orphan_temp_files,
    read_raw_events,
)

app = typer.Typer(no_args_is_help=True, help="QuantForge research and operations CLI")
DEFAULT_RAW_OUTPUT = Path("data/raw")
DEFAULT_REPLAY_INPUT = Path("data/raw")
DEFAULT_DATA_QUALITY_OUTPUT = Path("runtime_exports/data_quality")
DEFAULT_OPERATIONS_OUTPUT = Path("runtime_exports")
DEFAULT_BACKUP_ROOT = Path("data/backups")
DEFAULT_AUTOMATION_ALLOWLIST = Path("automation/write-allowlist.yaml")


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


if __name__ == "__main__":
    app()

"""Operator-safe command line interface."""

import asyncio
import json
from pathlib import Path
from typing import Annotated, cast

import typer

from quantforge.config import get_settings
from quantforge.domain import DataGap, EventEnvelope
from quantforge.exchange.upbit.public_ws import UpbitPublicWebSocketClient
from quantforge.exchange.upbit.subscriptions import PublicStreamType, UpbitSubscription
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


if __name__ == "__main__":
    app()

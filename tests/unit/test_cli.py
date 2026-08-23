import json
from pathlib import Path

from typer.testing import CliRunner

from factories import make_trade_event
from quantforge.cli import app
from quantforge.runtime import DataQualitySnapshot
from quantforge.storage import ParquetRawEventWriter

runner = CliRunner()


def test_safety_status_json_is_fail_closed() -> None:
    result = runner.invoke(app, ["safety-status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trading_mode"] == "paper"
    assert payload["live_submission_allowed"] is False
    assert len(payload["failed_live_gates"]) == 6


def test_safety_status_human_output() -> None:
    result = runner.invoke(app, ["safety-status"])

    assert result.exit_code == 0
    assert "Trading mode: paper" in result.stdout
    assert "Live submission allowed: False" in result.stdout


def test_replay_raw_verifies_storage_and_writes_runtime_snapshot(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    writer = ParquetRawEventWriter(raw_root, max_rows=1)
    writer.append(make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=150))
    output_root = tmp_path / "runtime"

    result = runner.invoke(
        app,
        [
            "replay-raw",
            "--input-root",
            str(raw_root),
            "--output-root",
            str(output_root),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["verified_inputs"] == 1
    assert payload["network_used"] is False
    assert payload["authentication_used"] is False
    snapshot = DataQualitySnapshot.model_validate_json((output_root / "latest.json").read_bytes())
    assert snapshot.delivered_events == 1


def test_replay_raw_rejects_empty_input(tmp_path: Path) -> None:
    result = runner.invoke(app, ["replay-raw", "--input-root", str(tmp_path)])
    assert result.exit_code != 0
    assert "no verified raw events" in result.output

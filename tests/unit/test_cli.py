import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from typer.testing import CliRunner

from factories import make_orderbook_event, make_ticker_event, make_trade_event
from quantforge.cli import app
from quantforge.config import get_settings
from quantforge.operations import read_dashboard_snapshot
from quantforge.readiness import ReadinessStatus, read_readiness_report
from quantforge.runtime import DataQualitySnapshot
from quantforge.runtime.paper_supervisor import (
    PaperRuntimeSnapshot,
    PaperRuntimeState,
    write_paper_runtime_snapshot,
)
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


def test_realtime_benchmark_is_verified_hold_only(tmp_path: Path) -> None:
    writer = ParquetRawEventWriter(tmp_path, max_rows=1)
    events = (
        make_ticker_event(sequence=1, received_offset_ms=100),
        make_orderbook_event(sequence=2, received_offset_ms=110),
        make_trade_event(sequence=3, exchange_offset_ms=115, received_offset_ms=120),
        make_trade_event(sequence=4, exchange_offset_ms=125, received_offset_ms=130),
    )
    for event in reversed(events):
        writer.append(event)

    result = runner.invoke(
        app,
        ["benchmark-realtime", "--input-root", str(tmp_path), "--max-events", "4"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["processed_events"] == 4
    assert payload["inference_ready_frames"] == 1
    assert payload["processing_latency_p99_ms"] >= 0
    assert payload["replay_events_per_second"] > 0
    assert payload["decision_state"] == "HOLD"
    assert payload["approved_model_available"] is False
    assert payload["strategy_order_capability"] is False
    assert payload["private_network_used"] is False
    assert payload["order_submission_available"] is False
    assert payload["live_submission_allowed"] is False


def test_realtime_benchmark_rejects_empty_input(tmp_path: Path) -> None:
    result = runner.invoke(app, ["benchmark-realtime", "--input-root", str(tmp_path)])

    assert result.exit_code != 0
    assert "no verified raw events" in result.output


def test_paper_decision_benchmark_is_verified_neutral_and_orderless(tmp_path: Path) -> None:
    writer = ParquetRawEventWriter(tmp_path, max_rows=1)
    events = (
        make_orderbook_event(sequence=1, received_offset_ms=100),
        make_trade_event(sequence=2, exchange_offset_ms=105, received_offset_ms=110),
        make_trade_event(sequence=3, exchange_offset_ms=115, received_offset_ms=120),
    )
    for event in reversed(events):
        writer.append(event)

    result = runner.invoke(
        app,
        ["benchmark-paper-decision", "--input-root", str(tmp_path), "--max-events", "3"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["processed_events"] == 3
    assert payload["inference_frames"] == 1
    assert payload["end_to_end_latency_p99_ms"] >= 0
    assert payload["replay_events_per_second"] > 0
    assert payload["model_release_status"] == "EXPERIMENTAL"
    assert payload["model_approval_valid"] is False
    assert payload["paper_order_simulation_enabled"] is False
    assert payload["paper_recovery_status"] == "NOT_CONFIGURED"
    assert payload["paper_recovery_blocked"] is False
    assert payload["decision_state"] == "HOLD"
    assert payload["strategy_trade_proposals"] == 0
    assert payload["risk_approvals"] == 0
    assert payload["paper_orders"] == 0
    assert payload["paper_fills"] == 0
    assert payload["real_order_submission_available"] is False
    assert payload["live_submission_allowed"] is False


def test_paper_decision_benchmark_rejects_empty_input(tmp_path: Path) -> None:
    result = runner.invoke(app, ["benchmark-paper-decision", "--input-root", str(tmp_path)])

    assert result.exit_code != 0
    assert "no verified raw events" in result.output


def test_paper_status_requires_a_connected_fresh_market_event(tmp_path: Path) -> None:
    now_utc = datetime.now(UTC)
    snapshot = PaperRuntimeSnapshot(
        run_id=UUID(int=1),
        state=PaperRuntimeState.RUNNING,
        started_at_utc=now_utc - timedelta(seconds=1),
        updated_at_utc=now_utc,
        markets=("KRW-BTC",),
        streams=("ticker", "trade", "orderbook"),
        accepted_messages=1,
        event_counts=(("trade", 1),),
        duplicate_messages=0,
        parser_errors=0,
        reconnects=0,
        committed_files=0,
        committed_rows=0,
        heartbeat_sequence=1,
        websocket_connected=True,
        last_event_at_utc=now_utc,
        last_exchange_at_utc=now_utc,
        raw_output="data/paper/raw",
        policy_hash="0" * 64,
    )
    path = write_paper_runtime_snapshot(snapshot, tmp_path)

    result = runner.invoke(
        app,
        ["paper-status", "--snapshot", str(path), "--require-fresh-seconds", "90"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["healthy"] is True
    assert payload["websocket_connected"] is True

    disconnected = snapshot.model_copy(update={"websocket_connected": False})
    write_paper_runtime_snapshot(disconnected, tmp_path)
    disconnected_result = runner.invoke(
        app,
        ["paper-status", "--snapshot", str(path), "--require-fresh-seconds", "90"],
    )
    assert disconnected_result.exit_code == 1
    assert json.loads(disconnected_result.stdout)["healthy"] is False

    stale = snapshot.model_copy(
        update={
            "started_at_utc": now_utc - timedelta(seconds=180),
            "updated_at_utc": now_utc - timedelta(seconds=120),
            "last_event_at_utc": now_utc - timedelta(seconds=120),
        }
    )
    write_paper_runtime_snapshot(stale, tmp_path)
    stale_result = runner.invoke(
        app,
        ["paper-status", "--snapshot", str(path), "--require-fresh-seconds", "90"],
    )
    assert stale_result.exit_code == 1
    assert json.loads(stale_result.stdout)["healthy"] is False


def test_export_operations_is_secret_free_and_non_ordering(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QF_OPERATIONS_STATE_ROOT", str(tmp_path / "state"))
    get_settings.cache_clear()
    output = tmp_path / "exports"
    try:
        result = runner.invoke(app, ["export-operations", "--output-root", str(output)])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trading_mode"] == "paper"
    assert payload["live_submission_allowed"] is False
    assert payload["network_used"] is False
    assert payload["order_submission_available"] is False
    snapshot = read_dashboard_snapshot(output / "ops" / "dashboard.json")
    assert snapshot.system.disk_free_bytes is not None


def test_validate_work_automation_report_is_non_ordering() -> None:
    root = Path(__file__).resolve().parents[2]
    result = runner.invoke(
        app,
        [
            "validate-automation-report",
            "--report",
            str(root / "tests/fixtures/automation/work-noop-report.json"),
            "--workspace-root",
            str(root),
            "--allowlist",
            str(root / "automation/write-allowlist.yaml"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["actor"] == "work"
    assert payload["writes_allowed"] is True
    assert payload["network_used"] is False
    assert payload["order_submission_available"] is False


def test_validate_automation_trigger_is_operator_reviewed() -> None:
    root = Path(__file__).resolve().parents[2]
    result = runner.invoke(
        app,
        [
            "validate-automation-trigger",
            "--trigger",
            str(root / "tests/fixtures/automation/codex-trigger.json"),
            "--allowlist",
            str(root / "automation/write-allowlist.yaml"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operator_approval_required"] is True
    assert payload["requested_writes_allowed"] is True
    assert payload["order_submission_available"] is False


def test_validate_live_readiness_fails_closed_without_evidence(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(
        "quantforge.cli.get_settings",
        lambda: (_ for _ in ()).throw(AssertionError("readiness must not load runtime settings")),
    )
    result = runner.invoke(
        app,
        [
            "validate-live-readiness",
            "--evidence",
            str(root / "tests/fixtures/readiness/not-ready.json"),
            "--policy",
            str(root / "configs/readiness.default.yaml"),
            "--output-root",
            str(tmp_path),
            "--evaluated-at-utc",
            "2026-08-23T00:00:00Z",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "NOT_READY"
    assert payload["human_approval_required"] is True
    assert payload["activation_performed"] is False
    assert payload["network_used"] is False
    assert payload["order_submission_available"] is False
    assert payload["runtime_settings_changed"] is False
    report = read_readiness_report(tmp_path / "readiness/latest.json")
    assert report.status is ReadinessStatus.NOT_READY

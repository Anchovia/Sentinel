import json
from pathlib import Path

from typer.testing import CliRunner

from factories import make_trade_event
from quantforge.cli import app
from quantforge.config import get_settings
from quantforge.operations import read_dashboard_snapshot
from quantforge.readiness import ReadinessStatus, read_readiness_report
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

import json

from typer.testing import CliRunner

from quantforge.cli import app

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

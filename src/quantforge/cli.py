"""Operator-safe command line interface."""

import json

import typer

from quantforge.config import get_settings
from quantforge.runtime import LiveSubmissionGuard

app = typer.Typer(no_args_is_help=True, help="QuantForge research and operations CLI")


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


if __name__ == "__main__":
    app()

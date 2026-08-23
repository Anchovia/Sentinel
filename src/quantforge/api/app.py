"""Read-oriented API exposing health, safety, and process metrics."""

from typing import Any

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from quantforge import __version__
from quantforge.config import QuantForgeSettings, get_settings
from quantforge.monitoring import create_foundation_metrics, create_market_data_metrics
from quantforge.runtime import LiveSubmissionGuard


def create_app(settings: QuantForgeSettings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(title="QuantForge", version=__version__)
    metrics = create_foundation_metrics(active_settings)
    app.state.market_data_metrics = create_market_data_metrics(metrics.registry)
    app.mount("/metrics", make_asgi_app(registry=metrics.registry))

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/safety", tags=["system"])
    async def safety() -> dict[str, Any]:
        gate = LiveSubmissionGuard.evaluate(active_settings)
        return {
            "trading_mode": active_settings.trading_mode.value,
            "live_submission_allowed": gate.allowed,
            "failed_live_gates": list(gate.failures),
            "credentials_configured": active_settings.upbit_access_key is not None,
        }

    return app

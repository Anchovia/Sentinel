"""Authenticated read-oriented operations API with a fail-closed control boundary."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.responses import HTMLResponse
from prometheus_client import make_asgi_app

from quantforge import __version__
from quantforge.config import QuantForgeSettings, get_settings
from quantforge.monitoring import (
    OperationsMetrics,
    create_foundation_metrics,
    create_market_data_metrics,
    create_operations_metrics,
)
from quantforge.operations import (
    AuditEvent,
    ControlRecord,
    ControlRequest,
    CsrfValidationFailed,
    DashboardAuthenticationFailed,
    DashboardAuthUnavailable,
    DashboardSnapshot,
    IncidentView,
    OperationsContext,
    create_operations_context,
    render_dashboard,
)
from quantforge.runtime import LiveSubmissionGuard


def _observe_operations(snapshot: DashboardSnapshot, metrics: OperationsMetrics) -> None:
    metrics.unknown_orders.set(sum(order.state == "UNKNOWN" for order in snapshot.orders))
    metrics.balance_mismatch.set(
        float(any(incident.category == "BALANCE_MISMATCH" for incident in snapshot.incidents))
    )
    metrics.daily_pnl_krw.set(float(snapshot.overview.daily_pnl_krw))
    metrics.drawdown_ratio.set(snapshot.overview.max_drawdown_ratio)
    metrics.exposure_krw.set(float(snapshot.overview.exposure_krw))
    metrics.kill_switch_active.set(float(snapshot.overview.kill_switch_state != "inactive"))
    if snapshot.system.disk_free_bytes is not None:
        metrics.disk_free_bytes.set(snapshot.system.disk_free_bytes)
    if snapshot.system.reconciliation_age_seconds is not None:
        metrics.reconciliation_age_seconds.set(snapshot.system.reconciliation_age_seconds)
    metrics.backup_verified.set(float(snapshot.system.backup_state.value == "healthy"))
    for severity in ("NORMAL", "WARNING", "HIGH", "CRITICAL"):
        metrics.open_incidents.labels(severity=severity).set(
            sum(
                incident.severity.value == severity and incident.status.value != "RESOLVED"
                for incident in snapshot.incidents
            )
        )


def create_app(
    settings: QuantForgeSettings | None = None,
    operations: OperationsContext | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(title="QuantForge", version=__version__)
    metrics = create_foundation_metrics(active_settings)
    app.state.market_data_metrics = create_market_data_metrics(metrics.registry)
    operations_metrics = create_operations_metrics(metrics.registry)
    app.state.operations_metrics = operations_metrics
    operations_context = operations or create_operations_context(active_settings)
    app.state.operations = operations_context
    app.mount("/metrics", make_asgi_app(registry=metrics.registry))

    async def require_actor(
        authorization: Annotated[str | None, Header()] = None,
    ) -> str:
        try:
            return operations_context.authenticator.authenticate(authorization)
        except DashboardAuthUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="dashboard authentication is not configured",
            ) from exc
        except DashboardAuthenticationFailed as exc:
            operations_metrics.unauthorized_requests.inc()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="dashboard authentication failed",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

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

    @app.get("/api/v1/session", tags=["operations"])
    async def session(
        response: Response, actor_ref: Annotated[str, Depends(require_actor)]
    ) -> dict[str, object]:
        response.headers["Cache-Control"] = "no-store"
        csrf_token = operations_context.authenticator.issue_csrf(
            actor_ref, now_utc=datetime.now(UTC)
        )
        return {"csrf_token": csrf_token, "expires_in_seconds": 300, "actor_ref": actor_ref}

    @app.get("/api/v1/dashboard", response_model=DashboardSnapshot, tags=["operations"])
    async def dashboard_data(
        response: Response, actor_ref: Annotated[str, Depends(require_actor)]
    ) -> DashboardSnapshot:
        del actor_ref
        response.headers["Cache-Control"] = "no-store"
        snapshot = operations_context.snapshot()
        _observe_operations(snapshot, operations_metrics)
        return snapshot

    @app.get("/api/v1/incidents", response_model=list[IncidentView], tags=["operations"])
    async def incidents(
        response: Response, actor_ref: Annotated[str, Depends(require_actor)]
    ) -> list[IncidentView]:
        del actor_ref
        response.headers["Cache-Control"] = "no-store"
        return list(operations_context.incidents.list_current())

    @app.get("/api/v1/audit", response_model=list[AuditEvent], tags=["operations"])
    async def audit_log(
        response: Response, actor_ref: Annotated[str, Depends(require_actor)]
    ) -> list[AuditEvent]:
        del actor_ref
        response.headers["Cache-Control"] = "no-store"
        return list(operations_context.audit_log.events)

    @app.post("/api/v1/control-requests", response_model=ControlRecord, tags=["operations"])
    async def control_request(
        request: ControlRequest,
        response: Response,
        actor_ref: Annotated[str, Depends(require_actor)],
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> ControlRecord:
        response.headers["Cache-Control"] = "no-store"
        now_utc = datetime.now(UTC)
        try:
            operations_context.authenticator.verify_csrf(csrf_token, actor_ref, now_utc=now_utc)
            record = operations_context.controls.submit(
                request,
                actor_ref=actor_ref,
                idempotency_key=idempotency_key or "",
                occurred_at_utc=now_utc,
            )
        except CsrfValidationFailed as exc:
            operations_metrics.unauthorized_requests.inc()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        operations_metrics.control_requests.labels(
            action=request.action.value, status=record.status.value
        ).inc()
        _observe_operations(operations_context.snapshot(), operations_metrics)
        return record

    @app.get("/dashboard", response_class=HTMLResponse, tags=["operations"])
    async def dashboard_page(
        actor_ref: Annotated[str, Depends(require_actor)],
    ) -> HTMLResponse:
        del actor_ref
        snapshot = operations_context.snapshot()
        _observe_operations(snapshot, operations_metrics)
        return HTMLResponse(render_dashboard(snapshot), headers={"Cache-Control": "no-store"})

    return app

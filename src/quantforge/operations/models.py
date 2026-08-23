"""Secret-free read models for the operations dashboard and runtime exports."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.security import redact


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class IncidentSeverity(StrEnum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class OperationsModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OverviewView(OperationsModel):
    total_assets_krw: Decimal = Decimal("0")
    krw_available: Decimal = Decimal("0")
    krw_locked: Decimal = Decimal("0")
    realized_pnl_krw: Decimal = Decimal("0")
    unrealized_pnl_krw: Decimal = Decimal("0")
    gross_pnl_krw: Decimal = Decimal("0")
    net_pnl_krw: Decimal = Decimal("0")
    daily_pnl_krw: Decimal = Decimal("0")
    max_drawdown_ratio: float = 0.0
    exposure_krw: Decimal = Decimal("0")
    trading_mode: str = "paper"
    live_submission_allowed: bool = False
    failed_live_gates: tuple[str, ...] = ()
    kill_switch_state: str = "inactive"
    code_version: str
    model_versions: tuple[str, ...] = ()


class MarketView(OperationsModel):
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    price: Decimal
    spread_bps: float
    depth_krw: Decimal
    turnover_24h_krw: Decimal
    trade_intensity: float
    order_flow_imbalance: float
    microprice: Decimal
    volatility: float
    data_quality: HealthState
    alerts: tuple[str, ...] = ()


class PositionView(OperationsModel):
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    quantity: Decimal
    average_price: Decimal
    marked_value_krw: Decimal
    unrealized_pnl_krw: Decimal
    strategy_id: str
    held_seconds: Annotated[int, Field(ge=0)]
    exit_plan: str
    risk_usage_ratio: Annotated[float, Field(ge=0)]


class OrderView(OperationsModel):
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    identifier: str = Field(min_length=1, max_length=64)
    exchange_order_ref_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{16}$")
    state: str
    latency_ms: Annotated[float | None, Field(default=None, ge=0)]
    slippage_bps: float | None = None
    fee_krw: Decimal = Decimal("0")
    reason: str
    risk_decision: str


class StrategyView(OperationsModel):
    strategy_id: str
    state: str
    latest_signal: str
    pnl_krw: Decimal
    trade_count: Annotated[int, Field(ge=0)]
    expectancy_krw: Decimal
    drawdown_ratio: Annotated[float, Field(ge=0)]
    regime_performance: tuple[tuple[str, str], ...] = ()
    confidence_performance: tuple[tuple[str, str], ...] = ()
    cost_contribution_krw: Decimal = Decimal("0")


class ModelView(OperationsModel):
    model_id: str
    regime_probabilities: tuple[tuple[str, float], ...]
    alpha_prediction: float | None
    expected_net_edge_bps: float | None
    uncertainty: float
    calibration_error: float | None
    drift_score: float | None
    artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    release_status: str


class SystemView(OperationsModel):
    websocket_state: HealthState = HealthState.UNKNOWN
    last_pong_age_seconds: float | None = None
    market_event_age_seconds: float | None = None
    queue_depth: Annotated[int, Field(ge=0)] = 0
    dropped_events: Annotated[int, Field(ge=0)] = 0
    parser_errors: Annotated[int, Field(ge=0)] = 0
    rate_limit_remaining: Annotated[int | None, Field(ge=0)] = None
    rest_latency_ms: Annotated[float | None, Field(ge=0)] = None
    order_latency_ms: Annotated[float | None, Field(ge=0)] = None
    clock_skew_ms: float | None = None
    database_state: HealthState = HealthState.UNKNOWN
    disk_free_bytes: Annotated[int | None, Field(ge=0)] = None
    backup_state: HealthState = HealthState.UNKNOWN
    reconciliation_age_seconds: Annotated[float | None, Field(ge=0)] = None


class IncidentView(OperationsModel):
    incident_id: str = Field(min_length=1, max_length=80)
    opened_at_utc: datetime
    severity: IncidentSeverity
    category: str = Field(min_length=1, max_length=80)
    component: str = Field(min_length=1, max_length=80)
    markets: tuple[str, ...] = ()
    summary: str = Field(min_length=1, max_length=500)
    evidence: tuple[tuple[str, str], ...] = ()
    automatic_actions: tuple[str, ...] = ()
    requires_operator: bool = False
    requires_work_review: bool = False
    requires_codex: bool = False
    status: IncidentStatus = IncidentStatus.OPEN
    code_version: str
    model_versions: tuple[tuple[str, str], ...] = ()
    owner: str | None = Field(default=None, max_length=80)
    resolution: str | None = Field(default=None, max_length=500)

    @field_validator("opened_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("incident timestamp must be UTC-aware")
        return value

    @field_validator("evidence")
    @classmethod
    def canonicalize_evidence(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        sanitized = tuple(sorted((str(name)[:80], str(redact(item))[:500]) for name, item in value))
        names = tuple(name for name, _ in sanitized)
        if len(names) != len(set(names)):
            raise ValueError("incident evidence names must be unique")
        return sanitized


class DashboardSnapshot(OperationsModel):
    schema_version: str = "operations-dashboard-1"
    generated_at_utc: datetime
    overview: OverviewView
    markets: tuple[MarketView, ...] = ()
    positions: tuple[PositionView, ...] = ()
    orders: tuple[OrderView, ...] = ()
    strategies: tuple[StrategyView, ...] = ()
    models: tuple[ModelView, ...] = ()
    system: SystemView = SystemView()
    incidents: tuple[IncidentView, ...] = ()

    @field_validator("generated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("dashboard timestamp must be UTC-aware")
        return value

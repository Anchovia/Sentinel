"""Shared strategy input and proposal contracts, intentionally outside execution."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain.money import MonetaryDecimal
from quantforge.features import FeatureSnapshot
from quantforge.models import AlphaPrediction, ExecutionPrediction, RegimePrediction
from quantforge.portfolio import PortfolioSnapshot


class StrategyAction(StrEnum):
    TRADE = "TRADE"
    HOLD = "HOLD"
    ABSTAIN = "ABSTAIN"


class StrategyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SHADOW = "SHADOW"
    PAUSED = "PAUSED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    RETIRED = "RETIRED"


class OrderPreference(StrEnum):
    MARKET = "market"
    BEST = "best"
    LIMIT = "limit"
    POST_ONLY = "post_only"
    IOC = "ioc"
    FOK = "fok"
    NO_ORDER = "no_order"


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: UUID
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    event_time_utc: datetime
    available_at_utc: datetime
    mid_price: MonetaryDecimal = Field(gt=0)
    relative_spread_bps: MonetaryDecimal = Field(ge=0)
    bid_depth: MonetaryDecimal = Field(ge=0)
    ask_depth: MonetaryDecimal = Field(ge=0)
    market_active: bool
    warning_active: bool
    data_gap: bool = False

    @field_validator("event_time_utc", "available_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("market snapshot timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_availability(self) -> "MarketSnapshot":
        if self.available_at_utc < self.event_time_utc:
            raise ValueError("market snapshot cannot be available before its event")
        return self


class RiskContext(BaseModel):
    """Read-only risk context; it cannot approve or construct an order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    context_id: UUID
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    as_of_utc: datetime
    trading_mode: str
    kill_switch_active: bool
    strategy_paused: bool
    daily_loss_capacity_remaining_krw: MonetaryDecimal = Field(ge=0)
    position_capacity_remaining_krw: MonetaryDecimal = Field(ge=0)
    turnover_capacity_remaining_krw: MonetaryDecimal = Field(ge=0)
    drawdown_pct: MonetaryDecimal = Field(ge=0, le=1)

    @field_validator("as_of_utc")
    @classmethod
    def require_risk_context_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("risk context timestamp must be UTC-aware")
        return value


class StrategyInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    decision_at_utc: datetime
    market: MarketSnapshot
    features: FeatureSnapshot
    regime: RegimePrediction
    alpha: AlphaPrediction
    execution: ExecutionPrediction
    portfolio: PortfolioSnapshot
    risk: RiskContext

    @field_validator("decision_at_utc")
    @classmethod
    def require_decision_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("strategy decision timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_causality(self) -> "StrategyInput":
        markets = {
            self.market.market,
            self.features.market,
            self.regime.market,
            self.alpha.market,
            self.execution.market,
            self.portfolio.market,
            self.risk.market,
        }
        if len(markets) != 1:
            raise ValueError("strategy inputs refer to different markets")
        availability = (
            self.market.available_at_utc,
            self.features.available_at_utc,
            self.regime.predicted_at_utc,
            self.alpha.predicted_at_utc,
            self.execution.predicted_at_utc,
            self.portfolio.as_of,
            self.risk.as_of_utc,
        )
        if any(value > self.decision_at_utc for value in availability):
            raise ValueError("strategy input contains future information")
        return self


class StrategyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: UUID
    action: StrategyAction
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    side: str | None = Field(default=None, pattern=r"^(bid|ask)$")
    target_notional: MonetaryDecimal | None = None
    target_quantity: MonetaryDecimal | None = None
    order_preference: OrderPreference
    limit_price: MonetaryDecimal | None = None
    expected_horizon_seconds: int = Field(gt=0)
    expected_gross_edge_bps: MonetaryDecimal
    expected_cost_bps: MonetaryDecimal = Field(ge=0)
    expected_net_edge_bps: MonetaryDecimal
    confidence: float = Field(ge=0, le=1)
    uncertainty: float = Field(ge=0, le=1)
    decided_at_utc: datetime
    valid_until_utc: datetime
    invalidation_conditions: tuple[str, ...]
    exit_plan: str = Field(min_length=1)
    reason_codes: tuple[str, ...] = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)

    @field_validator("decided_at_utc", "valid_until_utc")
    @classmethod
    def require_strategy_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("strategy decision timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_decision(self) -> "StrategyDecision":
        if self.valid_until_utc <= self.decided_at_utc:
            raise ValueError("strategy decision validity is invalid")
        if self.expected_net_edge_bps != self.expected_gross_edge_bps - self.expected_cost_bps:
            raise ValueError("strategy expected net edge does not reconcile")
        amounts = (self.target_notional, self.target_quantity)
        present = sum(value is not None for value in amounts)
        if self.action is StrategyAction.TRADE:
            if (
                self.side is None
                or present != 1
                or self.order_preference is OrderPreference.NO_ORDER
            ):
                raise ValueError(
                    "trade decision requires side, one amount, and an order preference"
                )
            if any(value is not None and value <= 0 for value in amounts):
                raise ValueError("strategy trade amount must be positive")
        elif (
            self.side is not None
            or present
            or self.order_preference is not OrderPreference.NO_ORDER
        ):
            raise ValueError("hold/abstain decision cannot request an order")
        if self.limit_price is not None and self.limit_price <= 0:
            raise ValueError("strategy limit price must be positive")
        return self


class Strategy(Protocol):
    strategy_id: str
    strategy_version: str

    def evaluate(self, inputs: StrategyInput) -> StrategyDecision: ...

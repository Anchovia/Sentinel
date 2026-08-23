"""Immutable contracts for deterministic paper execution."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain.money import MonetaryDecimal
from quantforge.domain.orders import OrderStatus


class PaperFillModel(StrEnum):
    NAIVE = "naive"
    CONSERVATIVE_L2 = "conservative_l2"
    CALIBRATED_L2 = "calibrated_l2"


class PaperOrderType(StrEnum):
    MARKET = "market"
    BEST = "best"
    LIMIT = "limit"


class TimeInForce(StrEnum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    POST_ONLY = "post_only"


class LiquidityRole(StrEnum):
    MAKER = "maker"
    TAKER = "taker"


def deterministic_execution_id(kind: str, *parts: object) -> UUID:
    """Create a stable UUID for a replay-derived execution object."""

    identity = "|".join((kind, *(str(part) for part in parts)))
    return uuid5(NAMESPACE_URL, f"quantforge:{identity}")


class PaperExecutionPolicy(BaseModel):
    """Reviewed paper assumptions; rates are simulations, not exchange facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    model: PaperFillModel = PaperFillModel.CONSERVATIVE_L2
    maker_fee_rate: MonetaryDecimal = Decimal("0.0005")
    taker_fee_rate: MonetaryDecimal = Decimal("0.0005")
    research_allow_zero_fees: bool = False
    order_latency_ms: Annotated[int, Field(ge=0)] = 100
    cancel_latency_ms: Annotated[int, Field(ge=0)] = 100
    max_book_age_ms: Annotated[int, Field(gt=0)] = 2_000
    queue_factor: MonetaryDecimal = Decimal("0.75")
    depth_haircut: MonetaryDecimal = Decimal("0.80")
    snapshot_decrease_fill_fraction: MonetaryDecimal = Decimal("0.25")
    slippage_buffer_bps: MonetaryDecimal = Decimal("1")
    adverse_selection_bps: MonetaryDecimal = Decimal("2")
    market_reserve_buffer_bps: MonetaryDecimal = Decimal("100")
    calibration_id: str | None = None

    @model_validator(mode="after")
    def validate_policy(self) -> "PaperExecutionPolicy":
        rates = (self.maker_fee_rate, self.taker_fee_rate)
        if any(rate < 0 for rate in rates):
            raise ValueError("fee rates cannot be negative")
        if not self.research_allow_zero_fees and any(rate == 0 for rate in rates):
            raise ValueError("zero fees require the explicit research-only override")
        unit_interval = (
            self.queue_factor,
            self.depth_haircut,
            self.snapshot_decrease_fill_fraction,
        )
        if any(value < 0 or value > 1 for value in unit_interval):
            raise ValueError("queue and depth assumptions must be between zero and one")
        if (
            self.slippage_buffer_bps < 0
            or self.adverse_selection_bps < 0
            or self.market_reserve_buffer_bps < 0
        ):
            raise ValueError("execution cost assumptions cannot be negative")
        if self.model is PaperFillModel.CALIBRATED_L2 and not self.calibration_id:
            raise ValueError("calibrated_l2 requires a calibration_id")
        return self

    @property
    def digest(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()

    def arrival_time(self, submitted_at: datetime) -> datetime:
        return submitted_at + timedelta(milliseconds=self.order_latency_ms)

    def cancel_effective_time(self, requested_at: datetime) -> datetime:
        return requested_at + timedelta(milliseconds=self.cancel_latency_ms)


class PaperOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    intent_id: UUID
    decision_id: UUID
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    side: str = Field(pattern=r"^(bid|ask)$")
    order_type: PaperOrderType
    time_in_force: TimeInForce
    limit_price: MonetaryDecimal | None = None
    original_quantity: MonetaryDecimal = Field(gt=0)
    remaining_quantity: MonetaryDecimal = Field(ge=0)
    reference_mid: MonetaryDecimal = Field(gt=0)
    submitted_at: datetime
    arrival_at: datetime
    status: OrderStatus
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reject_reason: str | None = None
    cancel_requested_at: datetime | None = None
    cancel_effective_at: datetime | None = None

    @field_validator("submitted_at", "arrival_at", "cancel_requested_at", "cancel_effective_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError("paper order timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> "PaperOrder":
        if self.remaining_quantity > self.original_quantity:
            raise ValueError("remaining quantity cannot exceed original quantity")
        if self.order_type is PaperOrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit orders require a limit price")
        if self.order_type is not PaperOrderType.LIMIT and self.limit_price is not None:
            raise ValueError("only limit orders may carry a limit price")
        if self.arrival_at < self.submitted_at:
            raise ValueError("arrival cannot precede submission")
        if (self.cancel_requested_at is None) != (self.cancel_effective_at is None):
            raise ValueError("cancel request and effective timestamps must appear together")
        return self


class PaperFill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fill_id: UUID
    order_id: UUID
    sequence: Annotated[int, Field(ge=1)]
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    side: str = Field(pattern=r"^(bid|ask)$")
    quantity: MonetaryDecimal = Field(gt=0)
    price: MonetaryDecimal = Field(gt=0)
    notional: MonetaryDecimal = Field(gt=0)
    fee: MonetaryDecimal = Field(ge=0)
    fee_rate: MonetaryDecimal = Field(ge=0)
    liquidity_role: LiquidityRole
    filled_at: datetime
    source_event_id: UUID
    reference_mid: MonetaryDecimal = Field(gt=0)
    spread_cost: MonetaryDecimal = Field(ge=0)
    slippage_cost: MonetaryDecimal = Field(ge=0)
    adverse_selection_cost: MonetaryDecimal = Field(ge=0)
    model: PaperFillModel

    @field_validator("filled_at")
    @classmethod
    def require_fill_time_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("fill timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_arithmetic(self) -> "PaperFill":
        if self.notional != self.quantity * self.price:
            raise ValueError("fill notional must equal quantity times price")
        if self.fee != self.notional * self.fee_rate:
            raise ValueError("fill fee must equal notional times fee rate")
        return self


class PaperExecutionUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order: PaperOrder
    fills: tuple[PaperFill, ...] = ()
    occurred_at: datetime
    reason: str

    @field_validator("occurred_at")
    @classmethod
    def require_update_time_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("execution update timestamp must be UTC-aware")
        return value

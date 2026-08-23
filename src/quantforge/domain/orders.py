"""Order intent and explicit state transition rules."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantforge.domain.money import MonetaryDecimal


class OrderStatus(StrEnum):
    INTENT_CREATED = "INTENT_CREATED"
    RISK_REJECTED = "RISK_REJECTED"
    RISK_APPROVED = "RISK_APPROVED"
    PREFLIGHT_PENDING = "PREFLIGHT_PENDING"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    PREFLIGHT_OK = "PREFLIGHT_OK"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    PREVENTED = "PREVENTED"
    UNKNOWN = "UNKNOWN"
    RECONCILING = "RECONCILING"


class InvalidOrderTransition(ValueError):
    """Raised when an order attempts an impossible state transition."""


class OrderStateMachine:
    """Pure transition validator shared by paper, replay, and future live adapters."""

    _ALLOWED: ClassVar[dict[OrderStatus, frozenset[OrderStatus]]] = {
        OrderStatus.INTENT_CREATED: frozenset(
            {OrderStatus.RISK_REJECTED, OrderStatus.RISK_APPROVED, OrderStatus.EXPIRED}
        ),
        OrderStatus.RISK_REJECTED: frozenset(),
        OrderStatus.RISK_APPROVED: frozenset(
            {OrderStatus.PREFLIGHT_PENDING, OrderStatus.EXPIRED, OrderStatus.PREVENTED}
        ),
        OrderStatus.PREFLIGHT_PENDING: frozenset(
            {OrderStatus.PREFLIGHT_FAILED, OrderStatus.PREFLIGHT_OK, OrderStatus.UNKNOWN}
        ),
        OrderStatus.PREFLIGHT_FAILED: frozenset(),
        OrderStatus.PREFLIGHT_OK: frozenset(
            {OrderStatus.SUBMISSION_PENDING, OrderStatus.EXPIRED, OrderStatus.PREVENTED}
        ),
        OrderStatus.SUBMISSION_PENDING: frozenset(
            {OrderStatus.SUBMITTED, OrderStatus.REJECTED, OrderStatus.UNKNOWN}
        ),
        OrderStatus.SUBMITTED: frozenset(
            {OrderStatus.ACKNOWLEDGED, OrderStatus.REJECTED, OrderStatus.UNKNOWN}
        ),
        OrderStatus.ACKNOWLEDGED: frozenset(
            {
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCEL_PENDING,
                OrderStatus.CANCELED,
                OrderStatus.EXPIRED,
                OrderStatus.PREVENTED,
                OrderStatus.UNKNOWN,
            }
        ),
        OrderStatus.PARTIALLY_FILLED: frozenset(
            {
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCEL_PENDING,
                OrderStatus.CANCELED,
                OrderStatus.EXPIRED,
                OrderStatus.UNKNOWN,
            }
        ),
        OrderStatus.CANCEL_PENDING: frozenset(
            {
                OrderStatus.CANCEL_REQUESTED,
                OrderStatus.CANCELED,
                OrderStatus.FILLED,
                OrderStatus.UNKNOWN,
            }
        ),
        OrderStatus.CANCEL_REQUESTED: frozenset(
            {OrderStatus.CANCELED, OrderStatus.FILLED, OrderStatus.UNKNOWN}
        ),
        OrderStatus.UNKNOWN: frozenset({OrderStatus.RECONCILING}),
        OrderStatus.RECONCILING: frozenset(
            {
                OrderStatus.ACKNOWLEDGED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCELED,
                OrderStatus.REJECTED,
                OrderStatus.EXPIRED,
                OrderStatus.PREVENTED,
                OrderStatus.UNKNOWN,
            }
        ),
        OrderStatus.FILLED: frozenset(),
        OrderStatus.CANCELED: frozenset(),
        OrderStatus.REJECTED: frozenset(),
        OrderStatus.EXPIRED: frozenset(),
        OrderStatus.PREVENTED: frozenset(),
    }

    @classmethod
    def transition(cls, current: OrderStatus, target: OrderStatus) -> OrderStatus:
        if target not in cls._ALLOWED[current]:
            raise InvalidOrderTransition(f"order transition {current} -> {target} is not allowed")
        return target

    @classmethod
    def can_transition(cls, current: OrderStatus, target: OrderStatus) -> bool:
        return target in cls._ALLOWED[current]


class OrderIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: UUID = Field(default_factory=uuid4)
    strategy_id: str = Field(min_length=1, max_length=128)
    strategy_version: str = Field(min_length=1, max_length=64)
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    side: str = Field(pattern=r"^(bid|ask)$")
    requested_notional: MonetaryDecimal | None = None
    requested_quantity: MonetaryDecimal | None = None
    order_type: str = Field(min_length=1, max_length=32)
    limit_price: MonetaryDecimal | None = None
    signal_timestamp: datetime
    expires_at: datetime
    expected_gross_edge_bps: float
    expected_cost_bps: float
    expected_net_edge_bps: float
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0)
    reason: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_intent(self) -> "OrderIntent":
        if (self.requested_notional is None) == (self.requested_quantity is None):
            raise ValueError("exactly one of requested_notional or requested_quantity is required")
        amount = self.requested_notional or self.requested_quantity
        if amount is None or amount <= 0:
            raise ValueError("requested amount must be positive")
        if self.limit_price is not None and self.limit_price <= 0:
            raise ValueError("limit price must be positive")
        if self.signal_timestamp.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        if self.expires_at <= self.signal_timestamp:
            raise ValueError("expires_at must be later than signal_timestamp")
        return self

    @classmethod
    def paper_example(cls) -> "OrderIntent":
        now = datetime.now(tz=UTC)
        return cls(
            strategy_id="foundation-smoke",
            strategy_version="0.1.0",
            market="KRW-BTC",
            side="bid",
            requested_notional="10000",
            order_type="limit",
            limit_price="100000000",
            signal_timestamp=now,
            expires_at=now + timedelta(seconds=1),
            expected_gross_edge_bps=5.0,
            expected_cost_bps=3.0,
            expected_net_edge_bps=2.0,
            confidence=0.5,
            uncertainty=0.5,
            reason="foundation smoke fixture",
        )

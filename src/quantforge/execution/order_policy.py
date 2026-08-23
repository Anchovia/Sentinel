"""Fail-closed authenticated-order preflight independent from transport."""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.domain import RiskDecision, RiskDecisionType
from quantforge.domain.exchange_orders import ExchangeOrderRequest, OrderChance
from quantforge.domain.money import MonetaryDecimal


class OrderPreflightResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    identifier: str
    checked_at_utc: datetime
    reason_codes: tuple[str, ...] = Field(min_length=1)
    request_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    chance_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_notional: MonetaryDecimal | None = None
    approved_volume: MonetaryDecimal | None = None

    @field_validator("checked_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("order preflight timestamp must be UTC-aware")
        return value


class ExchangeOrderPolicy:
    def __init__(self, *, max_chance_age_seconds: int = 5) -> None:
        if max_chance_age_seconds < 0:
            raise ValueError("chance age limit cannot be negative")
        self.max_chance_age_seconds = max_chance_age_seconds

    def evaluate(
        self,
        request: ExchangeOrderRequest,
        risk: RiskDecision,
        chance: OrderChance,
        *,
        checked_at_utc: datetime,
    ) -> OrderPreflightResult:
        reasons: list[str] = []
        if risk.intent_id != request.intent_id or risk.decision_id != request.risk_decision_id:
            reasons.append("RISK_DECISION_MISMATCH")
        if risk.decision not in {RiskDecisionType.ALLOW, RiskDecisionType.RESIZE}:
            reasons.append("RISK_NOT_APPROVED")
        if request.market != chance.market:
            reasons.append("ORDER_CHANCE_MARKET_MISMATCH")
        if checked_at_utc < chance.observed_at_utc:
            reasons.append("ORDER_CHANCE_FROM_FUTURE")
        elif (
            checked_at_utc - chance.observed_at_utc
        ).total_seconds() > self.max_chance_age_seconds:
            reasons.append("STALE_ORDER_CHANCE")
        if checked_at_utc >= request.expires_at_utc:
            reasons.append("ORDER_REQUEST_EXPIRED")
        supported = chance.bid_types if request.side == "bid" else chance.ask_types
        if request.order_type not in supported:
            reasons.append("ORDER_TYPE_UNSUPPORTED")
        if request.price is not None and request.price % chance.tick_size != 0:
            reasons.append("INVALID_TICK_SIZE")

        notional = self._notional(request, chance)
        minimum = chance.min_bid_notional if request.side == "bid" else chance.min_ask_notional
        if notional < minimum:
            reasons.append("BELOW_MINIMUM_NOTIONAL")
        if notional > chance.max_total_notional:
            reasons.append("ABOVE_MAXIMUM_NOTIONAL")
        if risk.approved_notional is not None and notional > risk.approved_notional:
            reasons.append("RISK_NOTIONAL_EXCEEDED")
        if (
            risk.approved_quantity is not None
            and request.volume is not None
            and request.volume > risk.approved_quantity
        ):
            reasons.append("RISK_VOLUME_EXCEEDED")
        if request.side == "bid":
            required_quote = notional * (Decimal(1) + chance.bid_fee_rate)
            if required_quote > chance.quote_available:
                reasons.append("INSUFFICIENT_QUOTE_BALANCE")
        elif request.volume is None or request.volume > chance.base_available:
            reasons.append("INSUFFICIENT_BASE_BALANCE")

        return OrderPreflightResult(
            allowed=not reasons,
            identifier=request.identifier,
            checked_at_utc=checked_at_utc,
            reason_codes=tuple(reasons) if reasons else ("ALL_PREFLIGHT_CHECKS_PASS",),
            request_hash=self._hash(request),
            chance_hash=self._hash(chance),
            approved_notional=notional if not reasons else None,
            approved_volume=request.volume if not reasons else None,
        )

    @staticmethod
    def _notional(request: ExchangeOrderRequest, chance: OrderChance) -> Decimal:
        if request.order_type.value in {"price", "best"} and request.side == "bid":
            assert request.price is not None
            return request.price
        assert request.volume is not None
        return request.volume * (request.price or chance.reference_price)

    @staticmethod
    def _hash(model: BaseModel) -> str:
        payload = orjson.dumps(model.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()

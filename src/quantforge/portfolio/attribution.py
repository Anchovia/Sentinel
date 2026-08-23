"""Exact, append-only strategy/model/market/regime cost attribution."""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Annotated
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import MonetaryDecimal, as_decimal, deterministic_execution_id

ZERO_HASH = "0" * 64


class AttributionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: Annotated[int, Field(ge=1)]
    event_id: UUID
    attributed_at_utc: datetime
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    regime: str = Field(min_length=1)
    gross_edge_pnl: MonetaryDecimal
    fees: MonetaryDecimal = Field(ge=0)
    spread_cost: MonetaryDecimal = Field(ge=0)
    slippage_cost: MonetaryDecimal = Field(ge=0)
    adverse_selection_cost: MonetaryDecimal = Field(ge=0)
    net_pnl: MonetaryDecimal
    previous_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("attributed_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("attribution timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_cost_reconciliation(self) -> "AttributionEvent":
        expected = self.gross_edge_pnl - (
            self.fees + self.spread_cost + self.slippage_cost + self.adverse_selection_cost
        )
        if self.net_pnl != expected:
            raise ValueError("attribution costs do not reconcile to net PnL")
        return self


class AttributionLedger:
    def __init__(self) -> None:
        self._events: list[AttributionEvent] = []

    @property
    def events(self) -> tuple[AttributionEvent, ...]:
        return tuple(self._events)

    def append(
        self,
        *,
        attributed_at_utc: datetime,
        strategy_id: str,
        strategy_version: str,
        model_version: str,
        market: str,
        regime: str,
        gross_edge_pnl: Decimal | int | str,
        fees: Decimal | int | str,
        spread_cost: Decimal | int | str,
        slippage_cost: Decimal | int | str,
        adverse_selection_cost: Decimal | int | str,
    ) -> AttributionEvent:
        gross_edge_pnl = as_decimal(gross_edge_pnl)
        fees = as_decimal(fees)
        spread_cost = as_decimal(spread_cost)
        slippage_cost = as_decimal(slippage_cost)
        adverse_selection_cost = as_decimal(adverse_selection_cost)
        net_pnl = gross_edge_pnl - (fees + spread_cost + slippage_cost + adverse_selection_cost)
        sequence = len(self._events) + 1
        previous_hash = self._events[-1].event_hash if self._events else ZERO_HASH
        values = {
            "sequence": sequence,
            "event_id": deterministic_execution_id(
                "attribution", sequence, strategy_id, market, attributed_at_utc, previous_hash
            ),
            "attributed_at_utc": attributed_at_utc,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "model_version": model_version,
            "market": market,
            "regime": regime,
            "gross_edge_pnl": gross_edge_pnl,
            "fees": fees,
            "spread_cost": spread_cost,
            "slippage_cost": slippage_cost,
            "adverse_selection_cost": adverse_selection_cost,
            "net_pnl": net_pnl,
            "previous_hash": previous_hash,
        }
        event_hash = self._hash_values(values)
        event = AttributionEvent(**values, event_hash=event_hash)
        self._events.append(event)
        return event

    def totals_by(self, dimension: str) -> dict[str, Decimal]:
        allowed = {"strategy_id", "model_version", "market", "regime"}
        if dimension not in allowed:
            raise ValueError(f"unsupported attribution dimension: {dimension}")
        totals: dict[str, Decimal] = {}
        for event in self._events:
            key = str(getattr(event, dimension))
            totals[key] = totals.get(key, Decimal(0)) + event.net_pnl
        return totals

    def verify_chain(self) -> bool:
        previous_hash = ZERO_HASH
        for sequence, event in enumerate(self._events, start=1):
            if event.sequence != sequence or event.previous_hash != previous_hash:
                return False
            if event.event_hash != self._hash_event(event):
                return False
            previous_hash = event.event_hash
        return True

    @staticmethod
    def _hash_values(values: dict[str, object]) -> str:
        payload = orjson.dumps(values, option=orjson.OPT_SORT_KEYS, default=str)
        return sha256(payload).hexdigest()

    @classmethod
    def _hash_event(cls, event: AttributionEvent) -> str:
        return cls._hash_values(event.model_dump(exclude={"event_hash"}))

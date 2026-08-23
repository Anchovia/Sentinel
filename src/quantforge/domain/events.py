"""Versioned event contracts at the exchange/domain trust boundary."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type JSONScalar = bool | int | str | Decimal | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type EventType = Literal["ticker", "trade", "orderbook"]


class EventEnvelope(BaseModel):
    """Immutable normalized metadata plus an exact copy of the exchange payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    event_type: EventType
    schema_version: Annotated[int, Field(ge=1)] = 1
    source: Literal["upbit"] = "upbit"
    market: str = Field(pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    exchange_timestamp: datetime
    received_at_utc: datetime
    received_monotonic_ns: Annotated[int, Field(ge=0)]
    connection_id: UUID
    subscription_id: str = Field(min_length=1)
    local_sequence: Annotated[int, Field(ge=1)]
    raw_payload: dict[str, JSONValue]
    raw_payload_text: str = Field(min_length=2)
    raw_payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalization_version: str = Field(min_length=1)
    is_snapshot: bool
    is_realtime: bool
    is_duplicate: bool = False
    quality_flags: tuple[str, ...] = ()

    @field_validator("exchange_timestamp", "received_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event timestamps must be timezone-aware")
        if value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("event timestamps must be normalized to UTC")
        return value

    @model_validator(mode="after")
    def require_one_stream_kind(self) -> "EventEnvelope":
        if self.is_snapshot == self.is_realtime:
            raise ValueError("exactly one of is_snapshot and is_realtime must be true")
        if len(set(self.quality_flags)) != len(self.quality_flags):
            raise ValueError("quality flags must be unique")
        return self

    @property
    def ingress_latency_us(self) -> int:
        """Wall-clock receive minus exchange timestamp in integer microseconds."""

        delta = self.received_at_utc - self.exchange_timestamp
        return delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds

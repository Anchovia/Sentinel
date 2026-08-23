"""Exchange-neutral private order and asset observations."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain.money import MonetaryDecimal


class PrivateOrderState(StrEnum):
    WAIT = "wait"
    WATCH = "watch"
    TRADE = "trade"
    DONE = "done"
    CANCEL = "cancel"
    PREVENTED = "prevented"


class PrivateOrderEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    exchange_order_id: UUID
    identifier: str | None = Field(default=None, max_length=64)
    side: str = Field(pattern=r"^(bid|ask)$")
    order_type: str
    state: PrivateOrderState
    trade_id: UUID | None = None
    price: MonetaryDecimal | None = None
    average_price: MonetaryDecimal | None = None
    volume: MonetaryDecimal | None = None
    remaining_volume: MonetaryDecimal = Field(ge=0)
    executed_volume: MonetaryDecimal = Field(ge=0)
    paid_fee: MonetaryDecimal = Field(ge=0)
    locked: MonetaryDecimal = Field(ge=0)
    executed_funds: MonetaryDecimal = Field(ge=0)
    trade_fee: MonetaryDecimal | None = Field(default=None, ge=0)
    is_maker: bool | None = None
    order_time_utc: datetime
    trade_time_utc: datetime | None = None
    exchange_time_utc: datetime
    received_at_utc: datetime
    raw_payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("order_time_utc", "trade_time_utc", "exchange_time_utc", "received_at_utc")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError("private order timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_trade_fields(self) -> "PrivateOrderEvent":
        if self.state is PrivateOrderState.TRADE and (
            self.trade_id is None or self.trade_time_utc is None
        ):
            raise ValueError("trade observations require trade identity and time")
        if self.received_at_utc < self.exchange_time_utc:
            raise ValueError("private order event cannot be received before exchange time")
        return self


class PrivateAssetBalance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: str = Field(pattern=r"^[A-Z0-9]+$")
    balance: MonetaryDecimal = Field(ge=0)
    locked: MonetaryDecimal = Field(ge=0)


class PrivateAssetEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    asset_id: UUID
    balances: tuple[PrivateAssetBalance, ...] = Field(min_length=1)
    asset_time_utc: datetime
    exchange_time_utc: datetime
    received_at_utc: datetime
    raw_payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("asset_time_utc", "exchange_time_utc", "received_at_utc")
    @classmethod
    def require_asset_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("private asset timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_assets(self) -> "PrivateAssetEvent":
        currencies = tuple(balance.currency for balance in self.balances)
        if len(currencies) != len(set(currencies)):
            raise ValueError("private asset currencies must be unique")
        if self.received_at_utc < self.exchange_time_utc:
            raise ValueError("private asset event cannot be received before exchange time")
        return self

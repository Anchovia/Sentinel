"""Exchange-neutral authenticated order contracts; these do not perform I/O."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain.money import MonetaryDecimal


class ExchangeOrderType(StrEnum):
    LIMIT = "limit"
    PRICE = "price"
    MARKET = "market"
    BEST = "best"


class ExchangeTimeInForce(StrEnum):
    IOC = "ioc"
    FOK = "fok"
    POST_ONLY = "post_only"


class SelfMatchPrevention(StrEnum):
    REDUCE = "reduce"
    CANCEL_MAKER = "cancel_maker"
    CANCEL_TAKER = "cancel_taker"


class RemoteOrderState(StrEnum):
    WAIT = "wait"
    WATCH = "watch"
    DONE = "done"
    CANCEL = "cancel"
    PREVENTED = "prevented"


class ExchangeOrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: UUID
    risk_decision_id: UUID
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    side: str = Field(pattern=r"^(bid|ask)$")
    order_type: ExchangeOrderType
    volume: MonetaryDecimal | None = None
    price: MonetaryDecimal | None = None
    time_in_force: ExchangeTimeInForce | None = None
    smp_type: SelfMatchPrevention | None = None
    identifier: str = Field(min_length=1, max_length=64)
    requested_at_utc: datetime
    expires_at_utc: datetime

    @field_validator("requested_at_utc", "expires_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("exchange order timestamps must be UTC-aware")
        return value

    @field_validator("identifier")
    @classmethod
    def require_clean_identifier(cls, value: str) -> str:
        if value != value.strip() or any(character.isspace() for character in value):
            raise ValueError("order identifier cannot contain whitespace")
        return value

    @model_validator(mode="after")
    def validate_order_shape(self) -> "ExchangeOrderRequest":
        if self.expires_at_utc <= self.requested_at_utc:
            raise ValueError("exchange order expiry must follow request time")
        if self.volume is not None and self.volume <= 0:
            raise ValueError("exchange order volume must be positive")
        if self.price is not None and self.price <= 0:
            raise ValueError("exchange order price must be positive")
        if self.time_in_force is ExchangeTimeInForce.POST_ONLY and self.smp_type is not None:
            raise ValueError("post_only and SMP cannot be combined")

        if self.order_type is ExchangeOrderType.LIMIT:
            if self.volume is None or self.price is None:
                raise ValueError("limit order requires volume and price")
        elif self.order_type is ExchangeOrderType.PRICE:
            if (
                self.side != "bid"
                or self.price is None
                or self.volume is not None
                or self.time_in_force
                not in {
                    ExchangeTimeInForce.IOC,
                    ExchangeTimeInForce.FOK,
                }
            ):
                raise ValueError("price order requires bid price and IOC/FOK")
        elif self.order_type is ExchangeOrderType.MARKET:
            if (
                self.side != "ask"
                or self.volume is None
                or self.price is not None
                or self.time_in_force
                not in {
                    ExchangeTimeInForce.IOC,
                    ExchangeTimeInForce.FOK,
                }
            ):
                raise ValueError("market order requires ask volume and IOC/FOK")
        elif self.order_type is ExchangeOrderType.BEST:
            correct_amount = (
                self.price is not None and self.volume is None
                if self.side == "bid"
                else self.volume is not None and self.price is None
            )
            if not correct_amount or self.time_in_force not in {
                ExchangeTimeInForce.IOC,
                ExchangeTimeInForce.FOK,
            }:
                raise ValueError("best order requires side-specific amount and IOC/FOK")
        return self

    @property
    def ordered_body(self) -> tuple[tuple[str, str], ...]:
        values: list[tuple[str, str]] = [
            ("market", self.market),
            ("side", self.side),
        ]
        if self.volume is not None:
            values.append(("volume", str(self.volume)))
        if self.price is not None:
            values.append(("price", str(self.price)))
        values.extend((("ord_type", self.order_type.value), ("identifier", self.identifier)))
        if self.time_in_force is not None:
            values.append(("time_in_force", self.time_in_force.value))
        if self.smp_type is not None:
            values.append(("smp_type", self.smp_type.value))
        return tuple(values)


class RemoteOrderSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_order_id: UUID
    identifier: str = Field(min_length=1, max_length=64)
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    side: str = Field(pattern=r"^(bid|ask)$")
    order_type: ExchangeOrderType
    state: RemoteOrderState
    original_volume: MonetaryDecimal = Field(gt=0)
    remaining_volume: MonetaryDecimal = Field(ge=0)
    executed_volume: MonetaryDecimal = Field(ge=0)
    price: MonetaryDecimal | None = Field(default=None, gt=0)
    paid_fee: MonetaryDecimal = Field(ge=0)
    locked: MonetaryDecimal = Field(ge=0)
    observed_at_utc: datetime

    @field_validator("observed_at_utc")
    @classmethod
    def require_remote_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("remote order timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_volume(self) -> "RemoteOrderSnapshot":
        if self.remaining_volume + self.executed_volume > self.original_volume:
            raise ValueError("remote order volumes exceed original volume")
        return self


class OrderChance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    bid_types: tuple[ExchangeOrderType, ...] = Field(min_length=1)
    ask_types: tuple[ExchangeOrderType, ...] = Field(min_length=1)
    min_bid_notional: MonetaryDecimal = Field(gt=0)
    min_ask_notional: MonetaryDecimal = Field(gt=0)
    max_total_notional: MonetaryDecimal = Field(gt=0)
    tick_size: MonetaryDecimal = Field(gt=0)
    reference_price: MonetaryDecimal = Field(gt=0)
    quote_available: MonetaryDecimal = Field(ge=0)
    quote_locked: MonetaryDecimal = Field(ge=0)
    base_available: MonetaryDecimal = Field(ge=0)
    base_locked: MonetaryDecimal = Field(ge=0)
    bid_fee_rate: MonetaryDecimal = Field(ge=0)
    ask_fee_rate: MonetaryDecimal = Field(ge=0)
    observed_at_utc: datetime
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("observed_at_utc")
    @classmethod
    def require_chance_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("order chance timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_types(self) -> "OrderChance":
        if len(self.bid_types) != len(set(self.bid_types)) or len(self.ask_types) != len(
            set(self.ask_types)
        ):
            raise ValueError("order chance types must be unique")
        return self


class OrderTestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str = Field(min_length=1, max_length=64)
    accepted: bool
    dry_run: bool = True
    checked_at_utc: datetime
    reason_codes: tuple[str, ...] = Field(min_length=1)

    @field_validator("checked_at_utc")
    @classmethod
    def require_test_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("order test timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def require_dry_run(self) -> "OrderTestResult":
        if not self.dry_run:
            raise ValueError("order-test results can never represent a real order")
        return self

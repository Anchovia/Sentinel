"""Reviewed Upbit DEFAULT-format public WebSocket wire schemas."""

import json
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from quantforge.domain import JSONValue, MonetaryDecimal
from quantforge.exchange.upbit.errors import MalformedUpbitPayload, UpbitPayloadError


class StreamType(StrEnum):
    SNAPSHOT = "SNAPSHOT"
    REALTIME = "REALTIME"


class AskBid(StrEnum):
    ASK = "ASK"
    BID = "BID"


class ChangeDirection(StrEnum):
    RISE = "RISE"
    EVEN = "EVEN"
    FALL = "FALL"


class UpbitWireModel(BaseModel):
    """Additive fields are allowed because the exact raw payload is retained."""

    model_config = ConfigDict(frozen=True, extra="allow")

    code: str = Field(pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    timestamp: int = Field(gt=0)
    stream_type: StreamType


class UpbitDelistingDate(BaseModel):
    """Documented object representation used for a scheduled trading-support end date."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int = Field(ge=2000, le=9999)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)

    @model_validator(mode="after")
    def require_calendar_date(self) -> "UpbitDelistingDate":
        self.as_date()
        return self

    def as_date(self) -> date:
        return date(self.year, self.month, self.day)


class UpbitTicker(UpbitWireModel):
    type: Literal["ticker"]
    opening_price: MonetaryDecimal
    high_price: MonetaryDecimal
    low_price: MonetaryDecimal
    trade_price: MonetaryDecimal
    prev_closing_price: MonetaryDecimal
    change: ChangeDirection
    change_price: MonetaryDecimal
    signed_change_price: MonetaryDecimal
    change_rate: MonetaryDecimal
    signed_change_rate: MonetaryDecimal
    trade_volume: MonetaryDecimal
    acc_trade_volume: MonetaryDecimal
    acc_trade_volume_24h: MonetaryDecimal
    acc_trade_price: MonetaryDecimal
    acc_trade_price_24h: MonetaryDecimal
    trade_date: str = Field(pattern=r"^\d{8}$")
    trade_time: str = Field(pattern=r"^\d{6}$")
    trade_timestamp: int = Field(gt=0)
    ask_bid: AskBid
    acc_ask_volume: MonetaryDecimal
    acc_bid_volume: MonetaryDecimal
    highest_52_week_price: MonetaryDecimal
    highest_52_week_date: date
    lowest_52_week_price: MonetaryDecimal
    lowest_52_week_date: date
    market_state: Literal["PREVIEW", "ACTIVE", "PREDELISTING", "DELISTED"]
    delisting_date: date | UpbitDelistingDate | None
    is_trading_suspended: bool | None = None
    market_warning: Literal["NONE", "CAUTION"] | None = None


class UpbitTrade(UpbitWireModel):
    type: Literal["trade"]
    trade_date: date
    trade_time: str = Field(pattern=r"^\d{2}:\d{2}:\d{2}$")
    trade_timestamp: int = Field(gt=0)
    trade_price: MonetaryDecimal = Field(gt=0)
    trade_volume: MonetaryDecimal = Field(gt=0)
    ask_bid: AskBid
    prev_closing_price: MonetaryDecimal
    change: ChangeDirection
    change_price: MonetaryDecimal
    sequential_id: int = Field(gt=0)
    best_ask_price: MonetaryDecimal = Field(gt=0)
    best_ask_size: MonetaryDecimal = Field(ge=0)
    best_bid_price: MonetaryDecimal = Field(gt=0)
    best_bid_size: MonetaryDecimal = Field(ge=0)


class UpbitOrderbookUnit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    ask_price: MonetaryDecimal = Field(gt=0)
    bid_price: MonetaryDecimal = Field(gt=0)
    ask_size: MonetaryDecimal = Field(ge=0)
    bid_size: MonetaryDecimal = Field(ge=0)


class UpbitOrderbook(UpbitWireModel):
    type: Literal["orderbook"]
    total_ask_size: MonetaryDecimal = Field(ge=0)
    total_bid_size: MonetaryDecimal = Field(ge=0)
    orderbook_units: list[UpbitOrderbookUnit] = Field(min_length=1, max_length=30)
    level: MonetaryDecimal = Field(ge=0)


type UpbitPublicMessage = UpbitTicker | UpbitTrade | UpbitOrderbook


def decode_json_object(raw: str | bytes) -> dict[str, JSONValue]:
    """Decode JSON while preserving decimal tokens as Decimal instead of binary float."""

    try:
        parsed = json.loads(raw, parse_float=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MalformedUpbitPayload("payload is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise MalformedUpbitPayload("payload root must be an object")
    return cast(dict[str, JSONValue], parsed)


def parse_public_message(raw: str | bytes) -> tuple[UpbitPublicMessage, dict[str, JSONValue]]:
    payload = decode_json_object(raw)
    error = payload.get("error")
    if isinstance(error, dict):
        name = error.get("name")
        message = error.get("message")
        if isinstance(name, str) and isinstance(message, str):
            raise UpbitPayloadError(name, message)
        raise MalformedUpbitPayload("error payload does not match the documented shape")

    message_type = payload.get("type")
    models: dict[str, type[UpbitWireModel]] = {
        "ticker": UpbitTicker,
        "trade": UpbitTrade,
        "orderbook": UpbitOrderbook,
    }
    model = models.get(message_type) if isinstance(message_type, str) else None
    if model is None:
        raise MalformedUpbitPayload(f"unsupported public payload type: {message_type!r}")
    try:
        parsed = model.model_validate(cast(dict[str, Any], payload))
    except ValidationError as exc:
        raise MalformedUpbitPayload(f"payload failed {message_type} schema validation") from exc
    return cast(UpbitPublicMessage, parsed), payload

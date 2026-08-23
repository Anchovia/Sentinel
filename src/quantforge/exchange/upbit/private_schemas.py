"""Reviewed Upbit DEFAULT-format private WebSocket schemas and domain mappers."""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from quantforge.domain import MonetaryDecimal, deterministic_execution_id
from quantforge.domain.private_events import (
    PrivateAssetBalance,
    PrivateAssetEvent,
    PrivateOrderEvent,
    PrivateOrderState,
)
from quantforge.exchange.upbit.errors import MalformedUpbitPayload, UpbitPayloadError
from quantforge.exchange.upbit.schemas import AskBid, StreamType, decode_json_object


class UpbitPrivateWireModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    timestamp: int = Field(gt=0)
    stream_type: StreamType


class UpbitMyOrder(UpbitPrivateWireModel):
    type: Literal["myOrder"]
    code: str = Field(pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    uuid: UUID
    ask_bid: AskBid
    order_type: Literal["limit", "price", "market", "best"]
    state: PrivateOrderState
    trade_uuid: UUID | None = None
    price: MonetaryDecimal | None = None
    avg_price: MonetaryDecimal | None = None
    volume: MonetaryDecimal | None = None
    remaining_volume: MonetaryDecimal = Field(ge=0)
    executed_volume: MonetaryDecimal = Field(ge=0)
    trades_count: int = Field(ge=0)
    reserved_fee: MonetaryDecimal = Field(ge=0)
    remaining_fee: MonetaryDecimal = Field(ge=0)
    paid_fee: MonetaryDecimal = Field(ge=0)
    locked: MonetaryDecimal = Field(ge=0)
    executed_funds: MonetaryDecimal = Field(ge=0)
    time_in_force: Literal["ioc", "fok", "post_only"] | None = None
    trade_fee: MonetaryDecimal | None = Field(default=None, ge=0)
    is_maker: bool | None = None
    identifier: str | None = Field(default=None, max_length=64)
    smp_type: Literal["reduce", "cancel_maker", "cancel_taker"] | None = None
    prevented_volume: MonetaryDecimal = Field(default=Decimal(0), ge=0)
    prevented_locked: MonetaryDecimal = Field(default=Decimal(0), ge=0)
    trade_timestamp: int | None = Field(default=None, gt=0)
    order_timestamp: int = Field(gt=0)


class UpbitAssetBalance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    currency: str = Field(pattern=r"^[A-Z0-9]+$")
    balance: MonetaryDecimal = Field(ge=0)
    locked: MonetaryDecimal = Field(ge=0)


class UpbitMyAsset(UpbitPrivateWireModel):
    type: Literal["myAsset"]
    asset_uuid: UUID
    assets: tuple[UpbitAssetBalance, ...] = Field(min_length=1)
    asset_timestamp: int = Field(gt=0)


type UpbitPrivateMessage = UpbitMyOrder | UpbitMyAsset


def parse_private_message(raw: str | bytes) -> UpbitPrivateMessage:
    payload = decode_json_object(raw)
    error = payload.get("error")
    if isinstance(error, dict):
        name = error.get("name")
        message = error.get("message")
        if isinstance(name, str) and isinstance(message, str):
            raise UpbitPayloadError(name, message)
        raise MalformedUpbitPayload("private error payload does not match documented shape")
    message_type = payload.get("type")
    models: dict[str, type[UpbitPrivateWireModel]] = {
        "myOrder": UpbitMyOrder,
        "myAsset": UpbitMyAsset,
    }
    model = models.get(message_type) if isinstance(message_type, str) else None
    if model is None:
        raise MalformedUpbitPayload(f"unsupported private payload type: {message_type!r}")
    try:
        return cast(UpbitPrivateMessage, model.model_validate(cast(dict[str, Any], payload)))
    except ValidationError as exc:
        raise MalformedUpbitPayload("private payload failed schema validation") from exc


def _timestamp_ms_to_utc(value: int) -> datetime:
    seconds, milliseconds = divmod(value, 1000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=milliseconds * 1000)


def map_private_message(
    raw: str | bytes, *, received_at_utc: datetime
) -> PrivateOrderEvent | PrivateAssetEvent:
    message = parse_private_message(raw)
    raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    raw_hash = sha256(raw_bytes).hexdigest()
    exchange_time = _timestamp_ms_to_utc(message.timestamp)
    event_id = deterministic_execution_id(
        "upbit-private-event", raw_hash, received_at_utc.isoformat()
    )
    if isinstance(message, UpbitMyOrder):
        return PrivateOrderEvent(
            event_id=event_id,
            market=message.code,
            exchange_order_id=message.uuid,
            identifier=message.identifier,
            side=message.ask_bid.value.lower(),
            order_type=message.order_type,
            state=message.state,
            trade_id=message.trade_uuid,
            price=message.price,
            average_price=message.avg_price,
            volume=message.volume,
            remaining_volume=message.remaining_volume,
            executed_volume=message.executed_volume,
            paid_fee=message.paid_fee,
            locked=message.locked,
            executed_funds=message.executed_funds,
            trade_fee=message.trade_fee,
            is_maker=message.is_maker,
            order_time_utc=_timestamp_ms_to_utc(message.order_timestamp),
            trade_time_utc=(
                _timestamp_ms_to_utc(message.trade_timestamp)
                if message.trade_timestamp is not None
                else None
            ),
            exchange_time_utc=exchange_time,
            received_at_utc=received_at_utc,
            raw_payload_hash=raw_hash,
        )
    return PrivateAssetEvent(
        event_id=event_id,
        asset_id=message.asset_uuid,
        balances=tuple(
            PrivateAssetBalance(
                currency=asset.currency,
                balance=asset.balance,
                locked=asset.locked,
            )
            for asset in message.assets
        ),
        asset_time_utc=_timestamp_ms_to_utc(message.asset_timestamp),
        exchange_time_utc=exchange_time,
        received_at_utc=received_at_utc,
        raw_payload_hash=raw_hash,
    )

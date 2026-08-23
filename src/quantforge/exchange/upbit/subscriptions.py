"""Validated dynamic subscription messages for Upbit public streams."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, cast
from uuid import UUID, uuid4

import orjson

type PublicStreamType = Literal["ticker", "trade", "orderbook"]

MARKET_PATTERN = re.compile(r"^[A-Z0-9]+-[A-Z0-9]+$")
ORDERBOOK_DEPTHS = frozenset({1, 5, 15, 30})


@dataclass(frozen=True, slots=True)
class UpbitSubscription:
    stream: PublicStreamType
    codes: tuple[str, ...]
    only_snapshot: bool = False
    only_realtime: bool = False
    orderbook_depth: int | None = None
    orderbook_level: int = 0

    def __post_init__(self) -> None:
        if not self.codes:
            raise ValueError("subscription requires at least one market code")
        if len(set(self.codes)) != len(self.codes):
            raise ValueError("subscription market codes must be unique")
        if any(MARKET_PATTERN.fullmatch(code) is None for code in self.codes):
            raise ValueError("market codes must be uppercase QUOTE-BASE identifiers")
        if self.only_snapshot and self.only_realtime:
            raise ValueError("snapshot-only and realtime-only are mutually exclusive")
        if self.stream != "orderbook" and (
            self.orderbook_depth is not None or self.orderbook_level != 0
        ):
            raise ValueError("orderbook depth and level are valid only for orderbook streams")
        if self.orderbook_depth is not None and self.orderbook_depth not in ORDERBOOK_DEPTHS:
            raise ValueError("orderbook depth must be one of 1, 5, 15, or 30")
        if self.orderbook_level < 0:
            raise ValueError("orderbook level cannot be negative")
        if self.orderbook_level and any(not code.startswith("KRW-") for code in self.codes):
            raise ValueError("grouped orderbook levels are supported only for KRW markets")

    def as_data_type_object(self) -> dict[str, object]:
        codes = [
            f"{code}.{self.orderbook_depth}"
            if self.stream == "orderbook" and self.orderbook_depth is not None
            else code
            for code in self.codes
        ]
        result: dict[str, object] = {"type": self.stream, "codes": codes}
        if self.only_snapshot:
            result["is_only_snapshot"] = True
        if self.only_realtime:
            result["is_only_realtime"] = True
        if self.stream == "orderbook" and self.orderbook_level:
            result["level"] = self.orderbook_level
        return result


@dataclass(frozen=True, slots=True)
class SubscriptionRequest:
    ticket: UUID
    subscription_id: str
    payload: bytes


def build_subscription_request(
    subscriptions: tuple[UpbitSubscription, ...], *, ticket: UUID | None = None
) -> SubscriptionRequest:
    if not subscriptions:
        raise ValueError("at least one subscription is required")
    selected_ticket = ticket or uuid4()
    data_objects = [subscription.as_data_type_object() for subscription in subscriptions]
    identity_bytes = orjson.dumps(data_objects, option=orjson.OPT_SORT_KEYS)
    subscription_id = sha256(identity_bytes).hexdigest()[:24]
    payload = orjson.dumps([{"ticket": str(selected_ticket)}, *data_objects, {"format": "DEFAULT"}])
    return SubscriptionRequest(
        ticket=selected_ticket,
        subscription_id=subscription_id,
        payload=payload,
    )


def build_tiered_public_subscriptions(
    markets: Sequence[str],
    focused_markets: Sequence[str],
    streams: Sequence[str],
    *,
    orderbook_depth: int = 5,
) -> tuple[UpbitSubscription, ...]:
    """Watch every market by ticker and reserve dense streams for the current focus."""

    monitored = tuple(markets)
    focused = tuple(focused_markets)
    selected_streams = tuple(streams)
    allowed = {"ticker", "trade", "orderbook"}
    if not monitored or not focused:
        raise ValueError("tiered subscriptions require monitored and focused markets")
    if not set(focused).issubset(set(monitored)):
        raise ValueError("focused markets must belong to the monitored universe")
    if not selected_streams or any(stream not in allowed for stream in selected_streams):
        raise ValueError("tiered subscriptions accept ticker, trade, and orderbook only")
    subscriptions: list[UpbitSubscription] = []
    for stream in selected_streams:
        codes = monitored if stream == "ticker" else focused
        subscriptions.append(
            UpbitSubscription(
                cast(PublicStreamType, stream),
                codes,
                orderbook_depth=orderbook_depth if stream == "orderbook" else None,
            )
        )
    return tuple(subscriptions)

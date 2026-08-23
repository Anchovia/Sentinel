"""Pure builders for reviewed private WebSocket subscription messages."""

from collections.abc import Sequence
from uuid import UUID

import orjson


def build_private_subscription(
    *,
    ticket: UUID,
    include_my_order: bool = True,
    include_my_asset: bool = True,
    markets: Sequence[str] = (),
) -> bytes:
    if not include_my_order and not include_my_asset:
        raise ValueError("at least one private stream must be selected")
    normalized = tuple(dict.fromkeys(markets))
    if any(market != market.upper() or not market.startswith("KRW-") for market in normalized):
        raise ValueError("private order markets must be uppercase KRW pairs")
    request: list[dict[str, object]] = [{"ticket": str(ticket)}]
    if include_my_order:
        order_subscription: dict[str, object] = {"type": "myOrder"}
        if normalized:
            order_subscription["codes"] = list(normalized)
        request.append(order_subscription)
    if include_my_asset:
        request.append({"type": "myAsset"})
    request.append({"format": "DEFAULT"})
    return orjson.dumps(request)

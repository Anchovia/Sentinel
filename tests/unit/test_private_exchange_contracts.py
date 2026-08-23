from datetime import timedelta
from decimal import Decimal
from hashlib import sha512
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from factories import BASE_TIME
from quantforge.domain import PrivateAssetEvent, PrivateOrderEvent
from quantforge.exchange.auth import (
    AuthenticatedCapabilityDisabled,
    AuthorizationHeader,
    AuthRequest,
    DisabledAuthorizationProvider,
    build_query_string,
)
from quantforge.exchange.upbit import (
    UpbitMyAsset,
    UpbitMyOrder,
    build_private_subscription,
    map_private_message,
    parse_private_message,
)
from quantforge.exchange.upbit.errors import MalformedUpbitPayload

FIXTURES = Path(__file__).parents[1] / "fixtures" / "upbit"


def test_ordered_query_hash_preserves_order_and_repeated_keys() -> None:
    parameters = (
        ("market", "KRW-BTC"),
        ("states[]", "wait"),
        ("states[]", "watch"),
    )
    query = build_query_string(parameters)
    request = AuthRequest(
        method="GET",
        path="/v1/orders/open",
        nonce=UUID(int=1),
        ordered_parameters=parameters,
    )
    assert query == "market=KRW-BTC&states[]=wait&states[]=watch"
    assert request.query_string == query
    assert request.query_hash == sha512(query.encode()).hexdigest()


@pytest.mark.asyncio
async def test_authorization_is_opaque_and_disabled_by_default() -> None:
    header = AuthorizationHeader(value=SecretStr("non-sensitive-test-placeholder"))
    assert header.redacted == "Bearer ***"
    assert "non-sensitive-test-placeholder" not in repr(header)
    request = AuthRequest(method="GET", path="/v1/order", nonce=UUID(int=2))
    with pytest.raises(AuthenticatedCapabilityDisabled):
        await DisabledAuthorizationProvider().create_header(request)


def test_private_order_and_asset_fixtures_map_with_exact_decimals() -> None:
    order_raw = (FIXTURES / "myorder.synthetic.json").read_bytes()
    asset_raw = (FIXTURES / "myasset.synthetic.json").read_bytes()
    order_wire = parse_private_message(order_raw)
    asset_wire = parse_private_message(asset_raw)
    assert isinstance(order_wire, UpbitMyOrder)
    assert isinstance(asset_wire, UpbitMyAsset)
    assert order_wire.paid_fee == Decimal("0.05")

    order = map_private_message(order_raw, received_at_utc=BASE_TIME + timedelta(seconds=2))
    asset = map_private_message(asset_raw, received_at_utc=BASE_TIME + timedelta(seconds=2))
    assert isinstance(order, PrivateOrderEvent)
    assert order.side == "bid"
    assert order.trade_id == UUID("20000000-0000-0000-0000-000000000001")
    assert order.remaining_volume == Decimal(1)
    assert isinstance(asset, PrivateAssetEvent)
    assert asset.balances[0].balance == Decimal(100000)


def test_private_payload_and_subscription_fail_closed() -> None:
    with pytest.raises(MalformedUpbitPayload):
        parse_private_message(b'{"type":"unknown"}')
    message = build_private_subscription(
        ticket=UUID(int=3), markets=("KRW-BTC",), include_my_asset=True
    )
    assert b'"type":"myOrder"' in message
    assert b'"type":"myAsset"' in message
    assert message.count(b'"codes"') == 1
    with pytest.raises(ValueError, match="uppercase KRW"):
        build_private_subscription(ticket=UUID(int=3), markets=("krw-btc",))


def test_private_domain_rejects_binary_float_boundary() -> None:
    raw = (FIXTURES / "myasset.synthetic.json").read_bytes()
    payload = parse_private_message(raw)
    assert isinstance(payload, UpbitMyAsset)
    values = payload.assets[0].model_dump()
    values["balance"] = 1.5
    with pytest.raises(ValidationError, match="monetary values"):
        type(payload.assets[0])(**values)

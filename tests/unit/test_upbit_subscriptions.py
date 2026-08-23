from uuid import UUID

import orjson
import pytest

from quantforge.exchange.upbit.subscriptions import (
    UpbitSubscription,
    build_subscription_request,
    build_tiered_public_subscriptions,
)


def test_builds_default_format_multi_stream_request() -> None:
    request = build_subscription_request(
        (
            UpbitSubscription("ticker", ("KRW-BTC", "KRW-ETH")),
            UpbitSubscription("trade", ("KRW-BTC",), only_realtime=True),
            UpbitSubscription("orderbook", ("KRW-BTC",), orderbook_depth=5, orderbook_level=10_000),
        ),
        ticket=UUID("0e66c0ac-7e13-43ef-91fb-2a87c2956c49"),
    )
    payload = orjson.loads(request.payload)
    assert payload[0] == {"ticket": "0e66c0ac-7e13-43ef-91fb-2a87c2956c49"}
    assert payload[1] == {"type": "ticker", "codes": ["KRW-BTC", "KRW-ETH"]}
    assert payload[2]["is_only_realtime"] is True
    assert payload[3] == {
        "type": "orderbook",
        "codes": ["KRW-BTC.5"],
        "level": 10_000,
    }
    assert payload[-1] == {"format": "DEFAULT"}
    assert len(request.subscription_id) == 24


def test_subscription_identity_does_not_depend_on_ticket() -> None:
    subscription = (UpbitSubscription("trade", ("KRW-BTC",)),)
    first = build_subscription_request(subscription)
    second = build_subscription_request(subscription)
    assert first.ticket != second.ticket
    assert first.subscription_id == second.subscription_id


@pytest.mark.parametrize(
    "subscription",
    [
        lambda: UpbitSubscription("ticker", ()),
        lambda: UpbitSubscription("ticker", ("krw-btc",)),
        lambda: UpbitSubscription("ticker", ("KRW-BTC", "KRW-BTC")),
        lambda: UpbitSubscription("trade", ("KRW-BTC",), True, True),
        lambda: UpbitSubscription("ticker", ("KRW-BTC",), orderbook_depth=5),
        lambda: UpbitSubscription("orderbook", ("KRW-BTC",), orderbook_depth=7),
        lambda: UpbitSubscription("orderbook", ("KRW-BTC",), orderbook_level=-1),
        lambda: UpbitSubscription("orderbook", ("BTC-ETH",), orderbook_level=10),
    ],
)
def test_invalid_subscription_fails_before_network(subscription: object) -> None:
    with pytest.raises(ValueError):
        subscription()  # type: ignore[operator]


def test_empty_request_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_subscription_request(())


def test_tiered_subscriptions_watch_all_tickers_and_focus_dense_streams() -> None:
    subscriptions = build_tiered_public_subscriptions(
        ("KRW-BTC", "KRW-ETH", "KRW-XRP"),
        ("KRW-ETH",),
        ("ticker", "trade", "orderbook"),
        orderbook_depth=5,
    )

    assert subscriptions[0].codes == ("KRW-BTC", "KRW-ETH", "KRW-XRP")
    assert subscriptions[1].codes == ("KRW-ETH",)
    assert subscriptions[2].as_data_type_object()["codes"] == ["KRW-ETH.5"]

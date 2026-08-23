from collections import deque
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

import orjson
import pytest

from quantforge.domain import EventEnvelope
from quantforge.exchange.upbit.errors import UpbitAdapterError
from quantforge.exchange.upbit.public_ws import (
    PublicWebSocketPolicy,
    UpbitPublicWebSocketClient,
)
from quantforge.exchange.upbit.subscriptions import UpbitSubscription

FIXTURES = Path(__file__).parents[1] / "fixtures" / "upbit"


class FakeWebSocket:
    def __init__(self, messages: list[str | bytes | BaseException]) -> None:
        self.messages = deque(messages)
        self.sent: list[str | bytes] = []

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)

    async def recv(self) -> str | bytes:
        item = self.messages.popleft()
        if isinstance(item, BaseException):
            raise item
        return item


class FakeContext(AbstractAsyncContextManager[FakeWebSocket]):
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self.websocket

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None


class FakeConnector:
    def __init__(self, websockets: list[FakeWebSocket]) -> None:
        self.websockets = deque(websockets)
        self.calls: list[tuple[str, PublicWebSocketPolicy]] = []

    def __call__(self, endpoint: str, policy: PublicWebSocketPolicy) -> FakeContext:
        self.calls.append((endpoint, policy))
        return FakeContext(self.websockets.popleft())


def _wall_clock() -> datetime:
    return datetime(2025, 5, 7, 9, 46, 14, tzinfo=UTC)


@pytest.mark.asyncio
async def test_malformed_message_is_isolated_and_collection_continues() -> None:
    trade = (FIXTURES / "trade.default.json").read_bytes()
    orderbook = (FIXTURES / "orderbook.synthetic.json").read_bytes()
    websocket = FakeWebSocket([b"not-json", trade, orderbook])
    connector = FakeConnector([websocket])
    events: list[EventEnvelope] = []
    errors: list[UpbitAdapterError] = []

    async def on_event(event: EventEnvelope) -> None:
        events.append(event)

    async def on_error(error: UpbitAdapterError) -> None:
        errors.append(error)

    client = UpbitPublicWebSocketClient(
        [UpbitSubscription("trade", ("KRW-BTC",))],
        on_event,
        on_error=on_error,
        connector=connector,
        wall_clock=_wall_clock,
        monotonic_clock_ns=lambda: 100,
    )
    accepted = await client.run(max_messages=2)
    assert accepted == 2
    assert [event.local_sequence for event in events] == [1, 2]
    assert len(errors) == 1
    assert len(websocket.sent) == 1
    request = orjson.loads(websocket.sent[0])
    assert request[-1] == {"format": "DEFAULT"}
    assert connector.calls[0][0] == "wss://api.upbit.com/websocket/v1"
    assert connector.calls[0][1].ping_interval_seconds == 30
    assert connector.calls[0][1].ping_timeout_seconds == 10


@pytest.mark.asyncio
async def test_transport_failure_reconnects_with_bounded_backoff() -> None:
    trade = (FIXTURES / "trade.default.json").read_bytes()
    first = FakeWebSocket([ConnectionError("network down")])
    second = FakeWebSocket([trade])
    connector = FakeConnector([first, second])
    sleeps: list[float] = []
    events: list[EventEnvelope] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def on_event(event: EventEnvelope) -> None:
        events.append(event)

    client = UpbitPublicWebSocketClient(
        [UpbitSubscription("trade", ("KRW-BTC",))],
        on_event,
        connector=connector,
        sleep=sleep,
        random_value=lambda: 0.5,
        wall_clock=_wall_clock,
        max_reconnect_attempts=2,
    )
    assert await client.run(max_messages=1) == 1
    assert sleeps == [1.0]
    assert len(connector.calls) == 2
    assert len(events) == 1
    assert client.reconnect_count == 1
    assert client.connected is False


@pytest.mark.asyncio
async def test_reconnect_limit_surfaces_transport_failure() -> None:
    first = FakeWebSocket([ConnectionError("first")])
    second = FakeWebSocket([ConnectionError("second")])
    connector = FakeConnector([first, second])

    async def ignore_event(event: EventEnvelope) -> None:
        del event

    async def no_sleep(seconds: float) -> None:
        del seconds

    client = UpbitPublicWebSocketClient(
        [UpbitSubscription("ticker", ("KRW-BTC",))],
        ignore_event,
        connector=connector,
        sleep=no_sleep,
        max_reconnect_attempts=1,
    )
    with pytest.raises(ConnectionError, match="second"):
        await client.run(max_messages=1)


@pytest.mark.asyncio
async def test_replace_before_run_sends_new_subscription() -> None:
    trade = (FIXTURES / "trade.default.json").read_bytes()
    websocket = FakeWebSocket([trade])
    connector = FakeConnector([websocket])

    async def ignore_event(event: EventEnvelope) -> None:
        del event

    client = UpbitPublicWebSocketClient(
        [UpbitSubscription("ticker", ("KRW-BTC",))],
        ignore_event,
        connector=connector,
        wall_clock=_wall_clock,
    )
    await client.replace_subscriptions([UpbitSubscription("trade", ("KRW-BTC",))])
    await client.run(max_messages=1)
    request = orjson.loads(websocket.sent[0])
    assert request[1]["type"] == "trade"


@pytest.mark.asyncio
async def test_event_handler_failure_is_not_hidden_as_reconnect() -> None:
    trade = (FIXTURES / "trade.default.json").read_bytes()
    connector = FakeConnector([FakeWebSocket([trade])])

    async def fail_handler(event: EventEnvelope) -> None:
        del event
        raise RuntimeError("storage failed")

    client = UpbitPublicWebSocketClient(
        [UpbitSubscription("trade", ("KRW-BTC",))],
        fail_handler,
        connector=connector,
        wall_clock=_wall_clock,
    )
    with pytest.raises(RuntimeError, match="storage failed"):
        await client.run(max_messages=1)


@pytest.mark.asyncio
async def test_stop_before_run_is_clean() -> None:
    async def ignore_event(event: EventEnvelope) -> None:
        del event

    client = UpbitPublicWebSocketClient([UpbitSubscription("trade", ("KRW-BTC",))], ignore_event)
    await client.stop()
    assert await client.run() == 0


@pytest.mark.parametrize(
    "policy",
    [
        lambda: PublicWebSocketPolicy(endpoint="ws://insecure"),
        lambda: PublicWebSocketPolicy(ping_interval_seconds=0),
        lambda: PublicWebSocketPolicy(backoff_initial_seconds=2, backoff_max_seconds=1),
        lambda: PublicWebSocketPolicy(jitter_ratio=2),
    ],
)
def test_invalid_connection_policy_is_rejected(
    policy: Callable[[], PublicWebSocketPolicy],
) -> None:
    with pytest.raises(ValueError):
        policy()


@pytest.mark.asyncio
async def test_invalid_run_and_reconnect_bounds_are_rejected() -> None:
    async def ignore_event(event: EventEnvelope) -> None:
        del event

    with pytest.raises(ValueError, match="reconnect"):
        UpbitPublicWebSocketClient(
            [UpbitSubscription("trade", ("KRW-BTC",))],
            ignore_event,
            max_reconnect_attempts=-1,
        )
    client = UpbitPublicWebSocketClient([UpbitSubscription("trade", ("KRW-BTC",))], ignore_event)
    with pytest.raises(ValueError, match="max_messages"):
        await client.run(max_messages=0)

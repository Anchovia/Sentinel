"""Credential-free Upbit public WebSocket collector."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import random
from time import monotonic_ns
from typing import Protocol, cast
from uuid import uuid4

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from quantforge.exchange.base import EventHandler
from quantforge.exchange.upbit.errors import UpbitAdapterError
from quantforge.exchange.upbit.mapper import map_public_message
from quantforge.exchange.upbit.rate_limit import WebSocketMessageRateLimiter
from quantforge.exchange.upbit.subscriptions import (
    SubscriptionRequest,
    UpbitSubscription,
    build_subscription_request,
)
from quantforge.market_data import EventDeduplicator
from quantforge.monitoring import MarketDataMetrics, create_market_data_metrics

LIVE_NORMALIZATION_VERSION = "upbit-public-live-v2"


class WebSocketConnection(Protocol):
    async def send(self, message: str | bytes) -> None: ...

    async def recv(self) -> str | bytes: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PublicWebSocketPolicy:
    endpoint: str = "wss://api.upbit.com/websocket/v1"
    ping_interval_seconds: float = 30.0
    ping_timeout_seconds: float = 10.0
    open_timeout_seconds: float = 10.0
    close_timeout_seconds: float = 10.0
    backoff_initial_seconds: float = 1.0
    backoff_max_seconds: float = 60.0
    jitter_ratio: float = 0.20
    max_queue: int = 16_384

    def __post_init__(self) -> None:
        if not self.endpoint.startswith("wss://"):
            raise ValueError("public WebSocket endpoint must use TLS")
        numeric = (
            self.ping_interval_seconds,
            self.ping_timeout_seconds,
            self.open_timeout_seconds,
            self.close_timeout_seconds,
            self.backoff_initial_seconds,
            self.backoff_max_seconds,
        )
        if any(value <= 0 for value in numeric) or self.max_queue < 1:
            raise ValueError("WebSocket policy timings and max_queue must be positive")
        if self.backoff_initial_seconds > self.backoff_max_seconds:
            raise ValueError("initial backoff cannot exceed maximum backoff")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter ratio must be between zero and one")


type Connector = Callable[
    [str, PublicWebSocketPolicy], AbstractAsyncContextManager[WebSocketConnection]
]
type ErrorHandler = Callable[[UpbitAdapterError], Awaitable[None]]


def default_connector(
    endpoint: str, policy: PublicWebSocketPolicy
) -> AbstractAsyncContextManager[WebSocketConnection]:
    connection = connect(
        endpoint,
        ping_interval=policy.ping_interval_seconds,
        ping_timeout=policy.ping_timeout_seconds,
        open_timeout=policy.open_timeout_seconds,
        close_timeout=policy.close_timeout_seconds,
        max_queue=policy.max_queue,
        compression="deflate",
    )
    return cast(AbstractAsyncContextManager[WebSocketConnection], connection)


class UpbitPublicWebSocketClient:
    """A bounded, observable collector with malformed-message isolation."""

    def __init__(
        self,
        subscriptions: Sequence[UpbitSubscription],
        on_event: EventHandler,
        *,
        on_error: ErrorHandler | None = None,
        policy: PublicWebSocketPolicy | None = None,
        connector: Connector = default_connector,
        metrics: MarketDataMetrics | None = None,
        deduplicator: EventDeduplicator | None = None,
        limiter: WebSocketMessageRateLimiter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_value: Callable[[], float] = random,
        wall_clock: Callable[[], datetime] | None = None,
        monotonic_clock_ns: Callable[[], int] = monotonic_ns,
        max_reconnect_attempts: int | None = None,
    ) -> None:
        if not subscriptions:
            raise ValueError("public client requires at least one subscription")
        if max_reconnect_attempts is not None and max_reconnect_attempts < 0:
            raise ValueError("max_reconnect_attempts cannot be negative")
        self._subscriptions = tuple(subscriptions)
        self._on_event = on_event
        self._on_error = on_error
        self._policy = policy or PublicWebSocketPolicy()
        self._connector = connector
        self.metrics = metrics or create_market_data_metrics()
        self._deduplicator = deduplicator or EventDeduplicator()
        self._limiter = limiter or WebSocketMessageRateLimiter()
        self._sleep = sleep
        self._random_value = random_value
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))
        self._monotonic_clock_ns = monotonic_clock_ns
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_count = 0
        self._stop = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._active_connection: WebSocketConnection | None = None
        self._request: SubscriptionRequest = build_subscription_request(self._subscriptions)
        self._last_received_at_utc: datetime | None = None
        self._last_received_monotonic_ns: int | None = None

    @property
    def connected(self) -> bool:
        return self._active_connection is not None

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    async def run(self, *, max_messages: int | None = None) -> int:
        if max_messages is not None and max_messages < 1:
            raise ValueError("max_messages must be positive when provided")
        accepted = 0
        reconnect_attempt = 0
        while not self._stop.is_set():
            connection_id = uuid4()
            try:
                async with self._connector(self._policy.endpoint, self._policy) as websocket:
                    self._active_connection = websocket
                    self.metrics.connected.set(1)
                    await self._send_request(websocket, self._request)
                    while not self._stop.is_set():
                        raw = await websocket.recv()
                        self.metrics.received.inc()
                        try:
                            received_at_utc, received_monotonic_ns, clock_regressed = (
                                self._receive_time()
                            )
                            event = map_public_message(
                                raw,
                                received_at_utc=received_at_utc,
                                received_monotonic_ns=received_monotonic_ns,
                                connection_id=connection_id,
                                subscription_id=self._request.subscription_id,
                                local_sequence=accepted + 1,
                            )
                            updates: dict[str, object] = {
                                "normalization_version": LIVE_NORMALIZATION_VERSION
                            }
                            if clock_regressed:
                                updates["quality_flags"] = (
                                    *event.quality_flags,
                                    "local_clock_regression",
                                )
                            event = event.model_copy(update=updates)
                            event = self._deduplicator.mark(event)
                        except UpbitAdapterError as exc:
                            self.metrics.rejected.labels(reason=type(exc).__name__).inc()
                            if self._on_error is not None:
                                await self._on_error(exc)
                            continue
                        reconnect_attempt = 0
                        self.metrics.record_event(event)
                        await self._on_event(event)
                        accepted += 1
                        if max_messages is not None and accepted >= max_messages:
                            self._stop.set()
                            return accepted
            except asyncio.CancelledError:
                raise
            except (OSError, TimeoutError, ConnectionClosed):
                if self._stop.is_set():
                    break
                reconnect_attempt += 1
                if (
                    self._max_reconnect_attempts is not None
                    and reconnect_attempt > self._max_reconnect_attempts
                ):
                    raise
                self._reconnect_count += 1
                self.metrics.reconnects.inc()
                await self._sleep(self._backoff_seconds(reconnect_attempt))
            finally:
                self.metrics.connected.set(0)
                self._active_connection = None
        return accepted

    def _receive_time(self) -> tuple[datetime, int, bool]:
        wall_time = self._wall_clock()
        monotonic_time_ns = self._monotonic_clock_ns()
        previous_monotonic_ns = self._last_received_monotonic_ns
        if previous_monotonic_ns is not None and monotonic_time_ns < previous_monotonic_ns:
            raise RuntimeError("local monotonic receive clock moved backwards")

        previous_received_at = self._last_received_at_utc
        clock_regressed = previous_received_at is not None and wall_time < previous_received_at
        if clock_regressed:
            assert previous_received_at is not None
            assert previous_monotonic_ns is not None
            elapsed_ns = monotonic_time_ns - previous_monotonic_ns
            wall_time = previous_received_at + timedelta(microseconds=elapsed_ns // 1_000)

        self._last_received_at_utc = wall_time
        self._last_received_monotonic_ns = monotonic_time_ns
        return wall_time, monotonic_time_ns, clock_regressed

    async def replace_subscriptions(self, subscriptions: Sequence[UpbitSubscription]) -> None:
        selected = tuple(subscriptions)
        request = build_subscription_request(selected)
        async with self._send_lock:
            self._subscriptions = selected
            self._request = request
            if self._active_connection is not None:
                await self._limiter.acquire()
                await self._active_connection.send(request.payload)

    async def stop(self) -> None:
        self._stop.set()
        if self._active_connection is not None:
            await self._active_connection.close()

    async def _send_request(
        self, websocket: WebSocketConnection, request: SubscriptionRequest
    ) -> None:
        async with self._send_lock:
            await self._limiter.acquire()
            await websocket.send(request.payload)

    def _backoff_seconds(self, attempt: int) -> float:
        exponent = max(0, attempt - 1)
        base = min(
            self._policy.backoff_initial_seconds * float(2**exponent),
            self._policy.backoff_max_seconds,
        )
        factor = 1 + ((self._random_value() * 2) - 1) * self._policy.jitter_ratio
        return max(0.0, base * factor)

"""Protocols that keep exchange transports outside the domain."""

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from quantforge.domain import EventEnvelope

type EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class PublicMarketDataClient(Protocol):
    """Public market-data lifecycle without credentials or order methods."""

    async def run(self, *, max_messages: int | None = None) -> int:
        """Run until stopped or until the optional accepted-message bound is reached."""
        ...

    async def replace_subscriptions(self, subscriptions: Sequence[object]) -> None:
        """Atomically replace the desired public subscriptions."""
        ...

    async def stop(self) -> None:
        """Request a graceful stop."""
        ...

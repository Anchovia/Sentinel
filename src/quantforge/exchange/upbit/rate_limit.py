"""Connection-local sliding-window limiter for subscription messages."""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from time import monotonic


class WebSocketMessageRateLimiter:
    """Enforce the documented 5/second and 100/minute send limits."""

    def __init__(
        self,
        *,
        per_second: int = 5,
        per_minute: int = 100,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if per_second < 1 or per_minute < 1:
            raise ValueError("rate limits must be positive")
        self._per_second = per_second
        self._per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._second_window: deque[float] = deque()
        self._minute_window: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                self._prune(now)
                waits: list[float] = []
                if len(self._second_window) >= self._per_second:
                    waits.append(1.0 - (now - self._second_window[0]))
                if len(self._minute_window) >= self._per_minute:
                    waits.append(60.0 - (now - self._minute_window[0]))
                if not waits:
                    self._second_window.append(now)
                    self._minute_window.append(now)
                    return
                await self._sleep(max(waits))

    def _prune(self, now: float) -> None:
        while self._second_window and now - self._second_window[0] >= 1.0:
            self._second_window.popleft()
        while self._minute_window and now - self._minute_window[0] >= 60.0:
            self._minute_window.popleft()

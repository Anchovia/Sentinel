import pytest

from quantforge.exchange.upbit.rate_limit import WebSocketMessageRateLimiter


@pytest.mark.asyncio
async def test_second_window_waits_before_sixth_message() -> None:
    now = 0.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    async def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    limiter = WebSocketMessageRateLimiter(clock=clock, sleep=sleep)
    for _ in range(6):
        await limiter.acquire()
    assert sleeps == [1.0]


@pytest.mark.asyncio
async def test_minute_window_is_enforced() -> None:
    now = 0.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    async def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    limiter = WebSocketMessageRateLimiter(
        per_second=1000,
        per_minute=2,
        clock=clock,
        sleep=sleep,
    )
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()
    assert sleeps == [60.0]


@pytest.mark.parametrize(("second", "minute"), [(0, 1), (1, 0)])
def test_invalid_limits_are_rejected(second: int, minute: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        WebSocketMessageRateLimiter(per_second=second, per_minute=minute)

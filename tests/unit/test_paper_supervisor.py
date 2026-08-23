import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

import pytest

from factories import make_orderbook_event, make_trade_event
from quantforge.config import Environment, QuantForgeSettings
from quantforge.domain import EventEnvelope
from quantforge.exchange.upbit.errors import MalformedUpbitPayload, UpbitAdapterError
from quantforge.operations import read_dashboard_snapshot
from quantforge.runtime.paper_supervisor import (
    PaperRuntimeBlocked,
    PaperRuntimePolicy,
    PaperRuntimeState,
    PaperRuntimeSupervisor,
    PublicStreamClient,
    read_paper_runtime_snapshot,
    validate_paper_runtime_settings,
)
from quantforge.storage import read_raw_events


class FakePublicClient:
    def __init__(
        self,
        on_event: Callable[[EventEnvelope], Awaitable[None]],
        on_error: Callable[[UpbitAdapterError], Awaitable[None]],
        *,
        events: Sequence[EventEnvelope] = (),
        errors: Sequence[UpbitAdapterError] = (),
        failure: BaseException | None = None,
        block: bool = False,
    ) -> None:
        self._on_event = on_event
        self._on_error = on_error
        self._events = tuple(events)
        self._errors = tuple(errors)
        self._failure = failure
        self._block = block
        self._connected = False
        self._stop = asyncio.Event()
        self._reconnect_count = 0

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    async def run(self, *, max_messages: int | None = None) -> int:
        self._connected = True
        accepted = 0
        try:
            for error in self._errors:
                await self._on_error(error)
            for event in self._events:
                await self._on_event(event)
                accepted += 1
                if max_messages is not None and accepted >= max_messages:
                    break
            if self._failure is not None:
                raise self._failure
            if self._block:
                await self._stop.wait()
            return accepted
        finally:
            self._connected = False

    async def stop(self) -> None:
        self._stop.set()


def _factory(
    *,
    events: Sequence[EventEnvelope] = (),
    errors: Sequence[UpbitAdapterError] = (),
    failure: BaseException | None = None,
    block: bool = False,
) -> Callable[
    [Callable[[EventEnvelope], Awaitable[None]], Callable[[UpbitAdapterError], Awaitable[None]]],
    PublicStreamClient,
]:
    def build(
        on_event: Callable[[EventEnvelope], Awaitable[None]],
        on_error: Callable[[UpbitAdapterError], Awaitable[None]],
    ) -> PublicStreamClient:
        return FakePublicClient(
            on_event,
            on_error,
            events=events,
            errors=errors,
            failure=failure,
            block=block,
        )

    return build


def _supervisor(
    tmp_path: Path,
    factory: Callable[
        [
            Callable[[EventEnvelope], Awaitable[None]],
            Callable[[UpbitAdapterError], Awaitable[None]],
        ],
        PublicStreamClient,
    ],
    *,
    policy: PaperRuntimePolicy | None = None,
) -> PaperRuntimeSupervisor:
    return PaperRuntimeSupervisor(
        settings=QuantForgeSettings(),
        markets=("KRW-BTC",),
        streams=("ticker", "trade", "orderbook"),
        raw_output=tmp_path / "raw",
        output_root=tmp_path / "runtime",
        policy=policy or PaperRuntimePolicy(max_messages=2),
        client_factory=factory,
    )


@pytest.mark.asyncio
async def test_supervisor_commits_public_events_and_secret_free_status(tmp_path: Path) -> None:
    events = (
        make_orderbook_event(sequence=1, received_offset_ms=100),
        make_trade_event(sequence=2, exchange_offset_ms=200, received_offset_ms=250),
    )
    supervisor = _supervisor(
        tmp_path,
        _factory(
            events=events,
            errors=(MalformedUpbitPayload("isolated malformed payload"),),
        ),
    )

    snapshot = await supervisor.run()

    assert snapshot.state is PaperRuntimeState.STOPPED
    assert snapshot.accepted_messages == 2
    assert snapshot.committed_rows == 2
    assert snapshot.parser_errors == 1
    assert snapshot.last_error_type == "MalformedUpbitPayload"
    assert snapshot.authentication_used is False
    assert snapshot.private_network_used is False
    assert snapshot.order_submission_available is False
    assert snapshot.live_submission_allowed is False
    assert len(read_raw_events(tmp_path / "raw")) == 2
    persisted = read_paper_runtime_snapshot(tmp_path / "runtime/ops/paper-runtime.json")
    assert persisted == snapshot
    dashboard = read_dashboard_snapshot(tmp_path / "runtime/ops/dashboard.json")
    assert dashboard.overview.trading_mode == "paper"
    assert dashboard.overview.live_submission_allowed is False
    assert dashboard.markets[0].market == "KRW-BTC"

    serialized = json.loads((tmp_path / "runtime/ops/paper-runtime.json").read_text())
    forbidden = {"authorization", "access_key", "secret_key", "token", "password"}
    assert forbidden.isdisjoint(serialized)


@pytest.mark.asyncio
async def test_duration_bound_stops_a_blocked_client_cleanly(tmp_path: Path) -> None:
    supervisor = _supervisor(
        tmp_path,
        _factory(block=True),
        policy=PaperRuntimePolicy(
            duration_seconds=0.01,
            heartbeat_seconds=0.002,
            flush_seconds=0.005,
        ),
    )

    snapshot = await supervisor.run()

    assert snapshot.state is PaperRuntimeState.STOPPED
    assert snapshot.shutdown_reason == "duration_elapsed"
    assert snapshot.websocket_connected is False


@pytest.mark.asyncio
async def test_failure_is_persisted_and_propagated(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, _factory(failure=RuntimeError("storage boundary failed")))

    with pytest.raises(RuntimeError, match="storage boundary failed"):
        await supervisor.run()

    snapshot = read_paper_runtime_snapshot(tmp_path / "runtime/ops/paper-runtime.json")
    assert snapshot.state is PaperRuntimeState.FAILED
    assert snapshot.failure_type == "RuntimeError"
    assert snapshot.order_submission_available is False


@pytest.mark.parametrize(
    "settings",
    [
        QuantForgeSettings(environment=Environment.PRODUCTION),
        QuantForgeSettings(trading_mode="replay"),
        QuantForgeSettings(upbit_access_key="access", upbit_secret_key="secret"),
        QuantForgeSettings(live_release_manifest_valid=True),
    ],
)
def test_public_runtime_refuses_non_paper_or_partially_open_settings(
    settings: QuantForgeSettings,
) -> None:
    with pytest.raises(PaperRuntimeBlocked):
        validate_paper_runtime_settings(settings)


def test_policy_rejects_unbounded_values() -> None:
    with pytest.raises(ValueError):
        PaperRuntimePolicy(heartbeat_seconds=0)
    with pytest.raises(ValueError):
        PaperRuntimePolicy(duration_seconds=0)
    with pytest.raises(ValueError):
        PaperRuntimePolicy(max_messages=0)

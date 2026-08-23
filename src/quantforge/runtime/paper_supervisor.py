"""Supervised, credential-free public burn-in runtime for paper operations."""

import asyncio
import math
import os
import shutil
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from statistics import pstdev
from time import monotonic
from typing import Protocol
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge import __version__
from quantforge.config import Environment, QuantForgeSettings, TradingMode
from quantforge.domain import EventEnvelope
from quantforge.exchange.upbit.errors import UpbitAdapterError
from quantforge.exchange.upbit.schemas import AskBid, UpbitOrderbook, UpbitTicker, UpbitTrade
from quantforge.operations.exports import assert_runtime_export_safe, write_dashboard_snapshot
from quantforge.operations.models import (
    DashboardSnapshot,
    HealthState,
    MarketView,
    OverviewView,
    SystemView,
)
from quantforge.runtime.live_guard import LiveSubmissionGuard
from quantforge.storage import ParquetRawEventWriter, RawFileManifest, cleanup_orphan_temp_files


class PaperRuntimeBlocked(RuntimeError):
    """Raised when the public paper runtime is not completely fail-closed."""


class PaperRuntimeState(StrEnum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class PaperRuntimeSnapshot(BaseModel):
    """Secret-free lifecycle and data-quality evidence for one public burn-in run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "paper-runtime-1"
    run_id: UUID
    state: PaperRuntimeState
    started_at_utc: datetime
    updated_at_utc: datetime
    stopped_at_utc: datetime | None = None
    markets: tuple[str, ...] = Field(min_length=1)
    streams: tuple[str, ...] = Field(min_length=1)
    accepted_messages: int = Field(ge=0)
    event_counts: tuple[tuple[str, int], ...]
    duplicate_messages: int = Field(ge=0)
    parser_errors: int = Field(ge=0)
    reconnects: int = Field(ge=0)
    committed_files: int = Field(ge=0)
    committed_rows: int = Field(ge=0)
    heartbeat_sequence: int = Field(ge=0)
    websocket_connected: bool
    last_event_at_utc: datetime | None = None
    last_exchange_at_utc: datetime | None = None
    max_ingress_latency_ms: float | None = None
    last_error_type: str | None = None
    shutdown_reason: str | None = None
    failure_type: str | None = None
    raw_output: str
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    trading_mode: str = "paper"
    credentials_configured: bool = False
    authentication_used: bool = False
    private_network_used: bool = False
    order_submission_available: bool = False
    live_submission_allowed: bool = False

    @field_validator(
        "started_at_utc",
        "updated_at_utc",
        "stopped_at_utc",
        "last_event_at_utc",
        "last_exchange_at_utc",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError("paper runtime timestamps must be UTC-aware")
        return value

    @field_validator("max_ingress_latency_ms")
    @classmethod
    def require_finite_latency(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("paper runtime latency must be finite")
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "PaperRuntimeSnapshot":
        if self.updated_at_utc < self.started_at_utc:
            raise ValueError("runtime update cannot precede its start")
        if self.stopped_at_utc is not None and self.stopped_at_utc < self.started_at_utc:
            raise ValueError("runtime stop cannot precede its start")
        if self.committed_rows > self.accepted_messages:
            raise ValueError("committed rows cannot exceed accepted messages")
        if self.state in {PaperRuntimeState.STOPPED, PaperRuntimeState.FAILED}:
            if self.stopped_at_utc is None or self.websocket_connected:
                raise ValueError("terminal runtime snapshots must be stopped and disconnected")
        elif self.stopped_at_utc is not None:
            raise ValueError("nonterminal runtime snapshot cannot have a stop time")
        if any(
            (
                self.credentials_configured,
                self.authentication_used,
                self.private_network_used,
                self.order_submission_available,
                self.live_submission_allowed,
            )
        ):
            raise ValueError("paper runtime safety flags must remain false")
        return self


@dataclass(frozen=True, slots=True)
class PaperRuntimePolicy:
    heartbeat_seconds: float = 15.0
    flush_seconds: float = 60.0
    stale_after_seconds: float = 90.0
    max_rows_per_file: int = 10_000
    duration_seconds: float | None = None
    max_messages: int | None = None

    def __post_init__(self) -> None:
        numeric = (self.heartbeat_seconds, self.flush_seconds, self.stale_after_seconds)
        if any(value <= 0 for value in numeric) or self.max_rows_per_file < 1:
            raise ValueError("paper runtime timings and row bound must be positive")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise ValueError("paper runtime duration must be positive when supplied")
        if self.max_messages is not None and self.max_messages < 1:
            raise ValueError("paper runtime max_messages must be positive when supplied")

    @property
    def digest(self) -> str:
        payload = orjson.dumps(
            {
                "duration_seconds": self.duration_seconds,
                "flush_seconds": self.flush_seconds,
                "heartbeat_seconds": self.heartbeat_seconds,
                "max_messages": self.max_messages,
                "max_rows_per_file": self.max_rows_per_file,
                "stale_after_seconds": self.stale_after_seconds,
            },
            option=orjson.OPT_SORT_KEYS,
        )
        return sha256(payload).hexdigest()


class PublicStreamClient(Protocol):
    @property
    def connected(self) -> bool: ...

    @property
    def reconnect_count(self) -> int: ...

    async def run(self, *, max_messages: int | None = None) -> int: ...

    async def stop(self) -> None: ...


type PublicClientFactory = Callable[
    [Callable[[EventEnvelope], Awaitable[None]], Callable[[UpbitAdapterError], Awaitable[None]]],
    PublicStreamClient,
]


class _MarketAccumulator:
    def __init__(self, markets: Sequence[str]) -> None:
        self._markets = tuple(markets)
        self._tickers: dict[str, UpbitTicker] = {}
        self._books: dict[str, UpbitOrderbook] = {}
        self._trades: dict[str, deque[tuple[datetime, AskBid, Decimal]]] = {
            market: deque(maxlen=600) for market in self._markets
        }
        self._prices: dict[str, deque[Decimal]] = {
            market: deque(maxlen=120) for market in self._markets
        }
        self._last_event: dict[str, datetime] = {}

    def ingest(self, event: EventEnvelope) -> None:
        self._last_event[event.market] = event.received_at_utc
        if event.event_type == "ticker":
            ticker = UpbitTicker.model_validate(event.raw_payload)
            self._tickers[event.market] = ticker
            self._prices[event.market].append(ticker.trade_price)
            return
        if event.event_type == "trade":
            trade = UpbitTrade.model_validate(event.raw_payload)
            trades = self._trades[event.market]
            trades.append((event.received_at_utc, trade.ask_bid, trade.trade_volume))
            self._prices[event.market].append(trade.trade_price)
            cutoff = event.received_at_utc.timestamp() - 60
            while trades and trades[0][0].timestamp() < cutoff:
                trades.popleft()
            return
        if event.event_type == "orderbook":
            self._books[event.market] = UpbitOrderbook.model_validate(event.raw_payload)

    def market_views(
        self, now_utc: datetime, *, stale_after_seconds: float
    ) -> tuple[MarketView, ...]:
        views: list[MarketView] = []
        for market in self._markets:
            book = self._books.get(market)
            if book is None:
                continue
            asks = sorted(book.orderbook_units, key=lambda unit: unit.ask_price)
            bids = sorted(book.orderbook_units, key=lambda unit: unit.bid_price, reverse=True)
            best_ask = asks[0]
            best_bid = bids[0]
            mid = (best_ask.ask_price + best_bid.bid_price) / Decimal(2)
            ticker = self._tickers.get(market)
            price = ticker.trade_price if ticker is not None else mid
            spread_bps = float((best_ask.ask_price - best_bid.bid_price) / mid * Decimal(10_000))
            depth = sum(
                (
                    unit.ask_price * unit.ask_size + unit.bid_price * unit.bid_size
                    for unit in book.orderbook_units
                ),
                start=Decimal(0),
            )
            top_total = best_bid.bid_size + best_ask.ask_size
            microprice = (
                (best_ask.ask_price * best_bid.bid_size + best_bid.bid_price * best_ask.ask_size)
                / top_total
                if top_total > 0
                else mid
            )
            trades = self._trades[market]
            bid_volume = sum(
                (volume for _, side, volume in trades if side is AskBid.BID), start=Decimal(0)
            )
            ask_volume = sum(
                (volume for _, side, volume in trades if side is AskBid.ASK), start=Decimal(0)
            )
            total_volume = bid_volume + ask_volume
            imbalance = float((bid_volume - ask_volume) / total_volume) if total_volume else 0.0
            prices = self._prices[market]
            returns = [
                float((current - previous) / previous)
                for previous, current in zip(prices, tuple(prices)[1:], strict=False)
                if previous > 0
            ]
            volatility = pstdev(returns) if len(returns) > 1 else 0.0
            last_event = self._last_event.get(market)
            age = (now_utc - last_event).total_seconds() if last_event is not None else math.inf
            alerts: list[str] = []
            quality = HealthState.HEALTHY
            if age > stale_after_seconds:
                quality = HealthState.DEGRADED
                alerts.append("PUBLIC_MARKET_DATA_STALE")
            if ticker is not None and (
                ticker.market_state != "ACTIVE" or ticker.market_warning == "CAUTION"
            ):
                quality = HealthState.BLOCKED
                alerts.append("MARKET_NOT_NORMAL")
            views.append(
                MarketView(
                    market=market,
                    price=price,
                    spread_bps=spread_bps,
                    depth_krw=depth,
                    turnover_24h_krw=(
                        ticker.acc_trade_price_24h if ticker is not None else Decimal(0)
                    ),
                    trade_intensity=float(len(trades)),
                    order_flow_imbalance=imbalance,
                    microprice=microprice,
                    volatility=volatility,
                    data_quality=quality,
                    alerts=tuple(alerts),
                )
            )
        return tuple(views)


def validate_paper_runtime_settings(settings: QuantForgeSettings) -> tuple[str, ...]:
    """Require an entirely closed live configuration before public collection starts."""

    if settings.environment is Environment.PRODUCTION:
        raise PaperRuntimeBlocked("public burn-in runtime refuses the production environment")
    if settings.trading_mode is not TradingMode.PAPER:
        raise PaperRuntimeBlocked("public burn-in runtime requires paper trading mode")
    if settings.upbit_access_key is not None or settings.upbit_secret_key is not None:
        raise PaperRuntimeBlocked("public burn-in runtime refuses configured Upbit credentials")
    gate = LiveSubmissionGuard.evaluate(settings)
    if gate.allowed or len(gate.failures) != 6:
        raise PaperRuntimeBlocked("all six live gates must be closed for public burn-in")
    return gate.failures


def write_paper_runtime_snapshot(snapshot: PaperRuntimeSnapshot, output_root: Path) -> Path:
    payload = snapshot.model_dump(mode="json")
    assert_runtime_export_safe(payload)
    destination_dir = output_root / "ops"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "paper-runtime.json"
    temporary = destination_dir / f".paper-runtime.{uuid4().hex}.tmp"
    encoded = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def read_paper_runtime_snapshot(path: Path) -> PaperRuntimeSnapshot:
    payload = orjson.loads(path.read_bytes())
    assert_runtime_export_safe(payload)
    return PaperRuntimeSnapshot.model_validate(payload)


class PaperRuntimeSupervisor:
    """Own one public connection, append-only storage, heartbeat, and clean shutdown."""

    def __init__(
        self,
        *,
        settings: QuantForgeSettings,
        markets: Sequence[str],
        streams: Sequence[str],
        raw_output: Path,
        output_root: Path,
        policy: PaperRuntimePolicy,
        client_factory: PublicClientFactory,
    ) -> None:
        self.settings = settings
        self.markets = tuple(markets)
        self.streams = tuple(streams)
        self.raw_output = raw_output
        self.output_root = output_root
        self.policy = policy
        self.client_factory = client_factory
        self.failed_live_gates = validate_paper_runtime_settings(settings)
        if not self.markets or not self.streams:
            raise ValueError("paper runtime requires markets and streams")

        self.run_id = uuid4()
        self.started_at_utc = datetime.now(UTC)
        self._event_counts: defaultdict[str, int] = defaultdict(int)
        self._duplicate_messages = 0
        self._parser_errors = 0
        self._committed_files = 0
        self._committed_rows = 0
        self._heartbeat_sequence = 0
        self._last_event_at_utc: datetime | None = None
        self._last_exchange_at_utc: datetime | None = None
        self._max_ingress_latency_ms: float | None = None
        self._last_error_type: str | None = None
        self._market = _MarketAccumulator(self.markets)
        self._writer = ParquetRawEventWriter(
            self.raw_output, max_rows=self.policy.max_rows_per_file
        )
        self._client = self.client_factory(self._on_event, self._on_error)

    async def run(self) -> PaperRuntimeSnapshot:
        self.raw_output.mkdir(parents=True, exist_ok=True)
        cleanup_orphan_temp_files(self.raw_output)
        await self._write_heartbeat(PaperRuntimeState.STARTING)
        task = asyncio.create_task(
            self._client.run(max_messages=self.policy.max_messages),
            name=f"paper-public-stream-{self.run_id}",
        )
        deadline = (
            monotonic() + self.policy.duration_seconds
            if self.policy.duration_seconds is not None
            else None
        )
        next_flush = monotonic() + self.policy.flush_seconds
        shutdown_reason = "client_completed"
        failure: BaseException | None = None
        try:
            while not task.done():
                now = monotonic()
                if deadline is not None and now >= deadline:
                    shutdown_reason = "duration_elapsed"
                    await self._client.stop()
                    task.cancel()
                    break
                timeout = self.policy.heartbeat_seconds
                timeout = min(timeout, max(0.001, next_flush - now))
                if deadline is not None:
                    timeout = min(timeout, max(0.001, deadline - now))
                done, _ = await asyncio.wait({task}, timeout=timeout)
                if done:
                    break
                if monotonic() >= next_flush:
                    self._record_manifests(self._writer.flush())
                    next_flush = monotonic() + self.policy.flush_seconds
                await self._write_heartbeat(PaperRuntimeState.RUNNING)
            if task.cancelled():
                pass
            elif not task.done():
                task.cancel()
            if task.done() and not task.cancelled():
                task.result()
        except asyncio.CancelledError as exc:
            shutdown_reason = "task_cancelled"
            failure = exc
            await self._client.stop()
            task.cancel()
        except Exception as exc:
            shutdown_reason = "runtime_failed"
            failure = exc
            await self._client.stop()
            task.cancel()
        finally:
            if not task.done():
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    if failure is None:
                        failure = exc
                        shutdown_reason = "runtime_failed"
            self._record_manifests(self._writer.close())

        terminal_state = (
            PaperRuntimeState.FAILED
            if failure is not None and not isinstance(failure, asyncio.CancelledError)
            else PaperRuntimeState.STOPPED
        )
        terminal = await self._write_heartbeat(
            terminal_state,
            stopped_at_utc=datetime.now(UTC),
            shutdown_reason=shutdown_reason,
            failure_type=(
                type(failure).__name__
                if failure is not None and not isinstance(failure, asyncio.CancelledError)
                else None
            ),
        )
        if failure is not None:
            raise failure
        return terminal

    async def _on_event(self, event: EventEnvelope) -> None:
        manifests = self._writer.append(event)
        self._record_manifests(manifests)
        self._event_counts[event.event_type] += 1
        if event.is_duplicate:
            self._duplicate_messages += 1
        self._last_event_at_utc = event.received_at_utc
        self._last_exchange_at_utc = event.exchange_timestamp
        latency_ms = event.ingress_latency_us / 1_000
        if self._max_ingress_latency_ms is None or latency_ms > self._max_ingress_latency_ms:
            self._max_ingress_latency_ms = latency_ms
        self._market.ingest(event)

    async def _on_error(self, error: UpbitAdapterError) -> None:
        self._parser_errors += 1
        self._last_error_type = type(error).__name__

    def _record_manifests(self, manifests: Sequence[RawFileManifest]) -> None:
        self._committed_files += len(manifests)
        self._committed_rows += sum(manifest.row_count for manifest in manifests)

    async def _write_heartbeat(
        self,
        state: PaperRuntimeState,
        *,
        stopped_at_utc: datetime | None = None,
        shutdown_reason: str | None = None,
        failure_type: str | None = None,
    ) -> PaperRuntimeSnapshot:
        self._heartbeat_sequence += 1
        now_utc = datetime.now(UTC)
        connected = self._client.connected if stopped_at_utc is None else False
        snapshot = PaperRuntimeSnapshot(
            run_id=self.run_id,
            state=state,
            started_at_utc=self.started_at_utc,
            updated_at_utc=now_utc,
            stopped_at_utc=stopped_at_utc,
            markets=self.markets,
            streams=self.streams,
            accepted_messages=sum(self._event_counts.values()),
            event_counts=tuple(sorted(self._event_counts.items())),
            duplicate_messages=self._duplicate_messages,
            parser_errors=self._parser_errors,
            reconnects=self._client.reconnect_count,
            committed_files=self._committed_files,
            committed_rows=self._committed_rows,
            heartbeat_sequence=self._heartbeat_sequence,
            websocket_connected=connected,
            last_event_at_utc=self._last_event_at_utc,
            last_exchange_at_utc=self._last_exchange_at_utc,
            max_ingress_latency_ms=self._max_ingress_latency_ms,
            last_error_type=self._last_error_type,
            shutdown_reason=shutdown_reason,
            failure_type=failure_type,
            raw_output=self.raw_output.as_posix(),
            policy_hash=self.policy.digest,
        )
        write_paper_runtime_snapshot(snapshot, self.output_root)
        event_age = (
            max(0.0, (now_utc - self._last_event_at_utc).total_seconds())
            if self._last_event_at_utc is not None
            else None
        )
        system_state = HealthState.UNKNOWN
        if connected and event_age is not None and event_age <= self.policy.stale_after_seconds:
            system_state = HealthState.HEALTHY
        elif state is PaperRuntimeState.FAILED or self._parser_errors:
            system_state = HealthState.DEGRADED
        dashboard = DashboardSnapshot(
            generated_at_utc=now_utc,
            overview=OverviewView(
                trading_mode=self.settings.trading_mode.value,
                live_submission_allowed=False,
                failed_live_gates=self.failed_live_gates,
                code_version=__version__,
            ),
            markets=self._market.market_views(
                now_utc, stale_after_seconds=self.policy.stale_after_seconds
            ),
            system=SystemView(
                websocket_state=system_state,
                market_event_age_seconds=event_age,
                parser_errors=self._parser_errors,
                clock_skew_ms=self._max_ingress_latency_ms,
                disk_free_bytes=shutil.disk_usage(self.raw_output.parent.resolve()).free,
            ),
        )
        write_dashboard_snapshot(dashboard, self.output_root)
        return snapshot

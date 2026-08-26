"""Supervised, credential-free public burn-in runtime for paper operations."""

import asyncio
import math
import os
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from statistics import pstdev
from time import monotonic
from typing import Literal, Protocol
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge import __version__
from quantforge.config import Environment, QuantForgeSettings, TradingMode
from quantforge.domain import EventEnvelope
from quantforge.exchange.upbit.errors import UpbitAdapterError
from quantforge.exchange.upbit.schemas import AskBid, UpbitOrderbook, UpbitTicker, UpbitTrade
from quantforge.exchange.upbit.subscriptions import UpbitSubscription
from quantforge.operations.exports import assert_runtime_export_safe, write_dashboard_snapshot
from quantforge.operations.models import (
    DashboardSnapshot,
    HealthState,
    MarketView,
    OverviewView,
    SystemView,
)
from quantforge.runtime.audit_exports import (
    AuditEvidenceState,
    WorkAuditBaseline,
    WorkAuditExportWriter,
    WorkIncidentSnapshot,
    WorkModelSnapshot,
    WorkOperationsSnapshot,
    WorkPerformanceSnapshot,
)
from quantforge.runtime.live_guard import LiveSubmissionGuard
from quantforge.runtime.paper_continuity import (
    PaperRuntimeContinuitySnapshot,
    PaperRuntimeContinuityTracker,
    write_paper_runtime_continuity_snapshot,
)
from quantforge.runtime.paper_monitor import write_paper_monitor
from quantforge.runtime.realtime_decision import (
    RealtimePaperDecisionSnapshot,
    RealtimePaperOrchestrator,
    write_realtime_paper_decision_snapshot,
)
from quantforge.runtime.realtime_pipeline import (
    RealtimePaperPipeline,
    RealtimePipelineSnapshot,
    write_realtime_pipeline_snapshot,
)
from quantforge.runtime.snapshots import DataQualitySnapshot
from quantforge.runtime.universe_scanner import (
    RealtimeUniverseScanner,
    write_realtime_universe_snapshot,
)
from quantforge.storage import (
    ParquetRawEventWriter,
    RawDataQualityIndex,
    RawFileManifest,
    RawStorageCapacityError,
    RawStorageMaintenance,
    RawStoragePolicy,
    cleanup_orphan_temp_files,
    maintain_raw_storage,
    require_raw_storage_capacity,
    update_raw_data_quality_index,
)


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

    schema_version: Literal[
        "paper-runtime-1",
        "paper-runtime-2",
        "paper-runtime-3",
        "paper-runtime-4",
        "paper-runtime-5",
        "paper-runtime-6",
        "paper-runtime-7",
    ] = "paper-runtime-7"
    run_id: UUID
    state: PaperRuntimeState
    started_at_utc: datetime
    updated_at_utc: datetime
    stopped_at_utc: datetime | None = None
    markets: tuple[str, ...] = Field(min_length=1)
    market_scope: Literal["fixed", "all_krw"] = "fixed"
    focused_markets: tuple[str, ...] = ()
    warning_market_count: int = Field(default=0, ge=0)
    caution_market_count: int = Field(default=0, ge=0)
    streams: tuple[str, ...] = Field(min_length=1)
    accepted_messages: int = Field(ge=0)
    event_counts: tuple[tuple[str, int], ...]
    duplicate_messages: int = Field(ge=0)
    parser_errors: int = Field(ge=0)
    reconnects: int = Field(ge=0)
    committed_files: int = Field(ge=0)
    committed_rows: int = Field(ge=0)
    retained_files: int = Field(default=0, ge=0)
    retained_rows: int = Field(default=0, ge=0)
    retained_bytes: int = Field(default=0, ge=0)
    storage_queue_depth: int = Field(default=0, ge=0)
    storage_queue_capacity: int = Field(default=0, ge=0)
    storage_queue_overflows: int = Field(default=0, ge=0)
    storage_label: str = Field(default="local-paper-data", min_length=1, max_length=200)
    storage_retention_days: int = Field(default=0, ge=0)
    storage_max_bytes: int = Field(default=0, ge=0)
    storage_min_free_bytes: int = Field(default=0, ge=0)
    storage_compaction_runs: int = Field(default=0, ge=0)
    storage_compacted_source_files: int = Field(default=0, ge=0)
    storage_retention_deleted_files: int = Field(default=0, ge=0)
    storage_capacity_deleted_files: int = Field(default=0, ge=0)
    storage_reclaimed_bytes: int = Field(default=0, ge=0)
    disk_free_bytes: int | None = Field(default=None, ge=0)
    quality_index_status: Literal["VERIFIED_STORAGE", "INSUFFICIENT_SAMPLE"] = "INSUFFICIENT_SAMPLE"
    verified_manifest_count: int = Field(default=0, ge=0)
    indexed_event_count: int = Field(default=0, ge=0)
    research_eligible_market_count: int = Field(default=0, ge=0)
    research_ready_for_preregistration: bool = False
    heartbeat_sequence: int = Field(ge=0)
    websocket_connected: bool
    last_event_at_utc: datetime | None = None
    last_exchange_at_utc: datetime | None = None
    max_ingress_latency_ms: float | None = None
    latest_ingress_latency_ms: float | None = None
    latest_exchange_clock_ahead_ms: float | None = Field(default=None, ge=0)
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

    @field_validator(
        "max_ingress_latency_ms",
        "latest_ingress_latency_ms",
        "latest_exchange_clock_ahead_ms",
    )
    @classmethod
    def require_finite_latency(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("paper runtime latency must be finite")
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "PaperRuntimeSnapshot":
        if (
            self.schema_version == "paper-runtime-7"
            and self.max_ingress_latency_ms is not None
            and self.max_ingress_latency_ms < 0
        ):
            raise ValueError("version-7 maximum ingress latency must be nonnegative")
        if self.updated_at_utc < self.started_at_utc:
            raise ValueError("runtime update cannot precede its start")
        if self.stopped_at_utc is not None and self.stopped_at_utc < self.started_at_utc:
            raise ValueError("runtime stop cannot precede its start")
        if self.committed_rows > self.accepted_messages:
            raise ValueError("committed rows cannot exceed accepted messages")
        if self.focused_markets and not set(self.focused_markets).issubset(set(self.markets)):
            raise ValueError("focused markets must belong to the monitored market scope")
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
    storage_queue_capacity: int = 65_536
    storage_batch_size: int = 512
    storage_label: str = "local-paper-data"
    storage_policy: RawStoragePolicy = dataclass_field(default_factory=RawStoragePolicy)
    duration_seconds: float | None = None
    max_messages: int | None = None

    def __post_init__(self) -> None:
        numeric = (self.heartbeat_seconds, self.flush_seconds, self.stale_after_seconds)
        if any(value <= 0 for value in numeric) or any(
            value < 1
            for value in (
                self.max_rows_per_file,
                self.storage_queue_capacity,
                self.storage_batch_size,
            )
        ):
            raise ValueError("paper runtime timings and row bound must be positive")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise ValueError("paper runtime duration must be positive when supplied")
        if self.max_messages is not None and self.max_messages < 1:
            raise ValueError("paper runtime max_messages must be positive when supplied")
        if (
            not self.storage_label.strip()
            or len(self.storage_label) > 200
            or any(ord(character) < 32 for character in self.storage_label)
        ):
            raise ValueError("paper runtime storage label is invalid")

    @property
    def digest(self) -> str:
        payload = orjson.dumps(
            {
                "duration_seconds": self.duration_seconds,
                "flush_seconds": self.flush_seconds,
                "heartbeat_seconds": self.heartbeat_seconds,
                "max_messages": self.max_messages,
                "max_rows_per_file": self.max_rows_per_file,
                "storage_batch_size": self.storage_batch_size,
                "storage_queue_capacity": self.storage_queue_capacity,
                "storage_label": self.storage_label,
                "storage_policy": {
                    "compaction_min_files": self.storage_policy.compaction_min_files,
                    "compaction_target_rows": self.storage_policy.compaction_target_rows,
                    "maintenance_interval_seconds": (
                        self.storage_policy.maintenance_interval_seconds
                    ),
                    "max_bytes": self.storage_policy.max_bytes,
                    "min_free_bytes": self.storage_policy.min_free_bytes,
                    "retention_days": self.storage_policy.retention_days,
                },
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

    async def replace_subscriptions(self, subscriptions: Sequence[UpbitSubscription]) -> None: ...

    async def stop(self) -> None: ...


type PublicClientFactory = Callable[
    [Callable[[EventEnvelope], Awaitable[None]], Callable[[UpbitAdapterError], Awaitable[None]]],
    PublicStreamClient,
]
type PublicSubscriptionBuilder = Callable[[Sequence[str]], Sequence[UpbitSubscription]]


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
        self,
        now_utc: datetime,
        *,
        stale_after_seconds: float,
        selected_markets: Sequence[str] | None = None,
    ) -> tuple[MarketView, ...]:
        views: list[MarketView] = []
        for market in selected_markets or self._markets:
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
        universe_scanner: RealtimeUniverseScanner | None = None,
        subscription_builder: PublicSubscriptionBuilder | None = None,
        recovery_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self.markets = tuple(markets)
        self.streams = tuple(streams)
        self.raw_output = raw_output
        self.output_root = output_root
        self._audit_export_writer = WorkAuditExportWriter(output_root)
        self.policy = policy
        self.client_factory = client_factory
        self._universe_scanner = universe_scanner
        self._subscription_builder = subscription_builder
        self.failed_live_gates = validate_paper_runtime_settings(settings)
        if not self.markets or not self.streams:
            raise ValueError("paper runtime requires markets and streams")
        if (self._universe_scanner is None) != (self._subscription_builder is None):
            raise ValueError("dynamic universe scanner and subscription builder must be paired")
        if self._universe_scanner is not None and self._universe_scanner.markets != self.markets:
            raise ValueError("dynamic universe markets must match the paper runtime")

        self.run_id = uuid4()
        self.started_at_utc = datetime.now(UTC)
        self._continuity = PaperRuntimeContinuityTracker(
            self.raw_output.parent / "state",
            run_id=self.run_id,
            started_at_utc=self.started_at_utc,
            stale_after_seconds=self.policy.stale_after_seconds,
        )
        self._event_counts: defaultdict[str, int] = defaultdict(int)
        self._duplicate_messages = 0
        self._parser_errors = 0
        self._committed_files = 0
        self._committed_rows = 0
        self.raw_output.mkdir(parents=True, exist_ok=True)
        initial_maintenance = maintain_raw_storage(
            self.raw_output,
            policy=self.policy.storage_policy,
            compact=False,
        )
        self._retained_files = initial_maintenance.summary.file_count
        self._retained_rows = initial_maintenance.summary.row_count
        self._retained_bytes = initial_maintenance.summary.byte_size
        self._storage_compaction_runs = int(initial_maintenance.compacted_source_files > 0)
        self._storage_compacted_source_files = initial_maintenance.compacted_source_files
        self._storage_retention_deleted_files = initial_maintenance.retention_deleted_files
        self._storage_capacity_deleted_files = initial_maintenance.capacity_deleted_files
        self._storage_reclaimed_bytes = initial_maintenance.reclaimed_bytes
        self._disk_free_bytes = initial_maintenance.disk_free_bytes
        self._raw_quality_index_path = (
            self.raw_output.parent / "index" / "raw-data-quality-index.json"
        )
        self._raw_quality_index = update_raw_data_quality_index(
            self.raw_output,
            self._raw_quality_index_path,
            storage_label=self.policy.storage_label,
        )
        try:
            self._disk_free_bytes = require_raw_storage_capacity(
                self.raw_output, self.policy.storage_policy
            )
        except RawStorageCapacityError as exc:
            raise PaperRuntimeBlocked(str(exc)) from exc
        self._storage_queue: asyncio.Queue[EventEnvelope | None] = asyncio.Queue(
            maxsize=self.policy.storage_queue_capacity
        )
        self._storage_queue_overflows = 0
        self._heartbeat_sequence = 0
        self._last_event_at_utc: datetime | None = None
        self._last_exchange_at_utc: datetime | None = None
        self._max_ingress_latency_ms: float | None = None
        self._latest_ingress_latency_ms: float | None = None
        self._latest_exchange_clock_ahead_ms: float | None = None
        self._last_error_type: str | None = None
        self._requested_shutdown_reason: str | None = None
        self._market = _MarketAccumulator(self.markets)
        self._realtime = RealtimePaperPipeline(self.markets)
        self._decision = RealtimePaperOrchestrator(
            self.markets,
            recovery_path=(
                recovery_path
                if recovery_path is not None
                else self.raw_output.parent / "state" / "realtime-paper-recovery.json"
            ),
        )
        self._writer = ParquetRawEventWriter(
            self.raw_output, max_rows=self.policy.max_rows_per_file
        )
        self._client = self.client_factory(self._on_event, self._on_error)

    async def request_stop(self, *, reason: str) -> None:
        """Request an idempotent graceful stop from an OS signal or operator-owned supervisor."""

        if not reason or len(reason) > 100:
            raise ValueError("paper runtime stop reason is invalid")
        if self._requested_shutdown_reason is None:
            self._requested_shutdown_reason = reason
        await self._client.stop()

    async def run(self) -> PaperRuntimeSnapshot:
        cleanup_orphan_temp_files(self.raw_output)
        self._decision.begin_recovery_session(started_at_utc=self.started_at_utc)
        self._continuity.start()
        await self._write_heartbeat(PaperRuntimeState.STARTING)
        storage_task = asyncio.create_task(
            self._storage_worker(), name=f"paper-storage-{self.run_id}"
        )
        task = asyncio.create_task(
            self._client.run(max_messages=self.policy.max_messages),
            name=f"paper-public-stream-{self.run_id}",
        )
        deadline = (
            monotonic() + self.policy.duration_seconds
            if self.policy.duration_seconds is not None
            else None
        )
        shutdown_reason = "client_completed"
        failure: BaseException | None = None
        try:
            while not task.done():
                if storage_task.done():
                    storage_task.result()
                now = monotonic()
                if deadline is not None and now >= deadline:
                    shutdown_reason = "duration_elapsed"
                    await self._client.stop()
                    task.cancel()
                    break
                timeout = self.policy.heartbeat_seconds
                if deadline is not None:
                    timeout = min(timeout, max(0.001, deadline - now))
                done, _ = await asyncio.wait({task}, timeout=timeout)
                if done:
                    break
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
            if self._requested_shutdown_reason is not None:
                shutdown_reason = self._requested_shutdown_reason
            if not task.done():
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    if failure is None:
                        failure = exc
                        shutdown_reason = "runtime_failed"
            if storage_task.done():
                try:
                    storage_task.result()
                except Exception as exc:
                    if failure is None:
                        failure = exc
                        shutdown_reason = "storage_failed"
            else:
                await self._storage_queue.put(None)
                try:
                    await storage_task
                except Exception as exc:
                    if failure is None:
                        failure = exc
                        shutdown_reason = "storage_failed"
            try:
                self._decision.close(closed_at_utc=datetime.now(UTC))
            except Exception as exc:
                if failure is None:
                    failure = exc
                    shutdown_reason = "paper_decision_close_failed"

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
        try:
            self._storage_queue.put_nowait(event)
        except asyncio.QueueFull as exc:
            self._storage_queue_overflows += 1
            raise PaperRuntimeBlocked(
                "bounded raw-storage queue overflowed; public processing stopped"
            ) from exc
        # Queue acceptance defines runtime acceptance. Record it before downstream work so a
        # processing failure cannot leave a persisted row ahead of the terminal snapshot counter.
        self._event_counts[event.event_type] += 1
        if event.is_duplicate:
            self._duplicate_messages += 1
        self._last_event_at_utc = event.received_at_utc
        self._last_exchange_at_utc = event.exchange_timestamp
        latency_ms = event.ingress_latency_us / 1_000
        positive_latency_ms = max(0.0, latency_ms)
        if (
            self._max_ingress_latency_ms is None
            or positive_latency_ms > self._max_ingress_latency_ms
        ):
            self._max_ingress_latency_ms = positive_latency_ms
        self._latest_ingress_latency_ms = latency_ms
        self._latest_exchange_clock_ahead_ms = max(0.0, -latency_ms)
        if self._universe_scanner is not None:
            self._universe_scanner.ingest(event)
        frame = self._realtime.process(event)
        focused = (
            self._universe_scanner.focused_markets
            if self._universe_scanner is not None
            else self.markets
        )
        if event.market in focused:
            self._decision.process(event, frame)
        self._market.ingest(event)

    async def _storage_worker(self) -> None:
        batch: list[EventEnvelope] = []
        next_flush = monotonic() + self.policy.flush_seconds
        next_maintenance = monotonic() + self.policy.storage_policy.maintenance_interval_seconds
        while True:
            try:
                event = await asyncio.wait_for(
                    self._storage_queue.get(),
                    timeout=max(0.001, next_flush - monotonic()),
                )
            except TimeoutError:
                await self._commit_storage_batch(batch, flush=True)
                batch.clear()
                next_flush = monotonic() + self.policy.flush_seconds
                if monotonic() >= next_maintenance:
                    await self._run_storage_maintenance(compact=True)
                    next_maintenance = (
                        monotonic() + self.policy.storage_policy.maintenance_interval_seconds
                    )
                continue
            if event is None:
                self._storage_queue.task_done()
                await self._commit_storage_batch(batch, flush=True, close=True)
                await self._run_storage_maintenance(compact=False)
                return
            batch.append(event)
            if len(batch) >= self.policy.storage_batch_size:
                await self._commit_storage_batch(batch)
                batch.clear()
            if monotonic() >= next_flush:
                await self._commit_storage_batch(batch, flush=True)
                batch.clear()
                next_flush = monotonic() + self.policy.flush_seconds
            if self._retained_bytes > self.policy.storage_policy.max_bytes:
                await self._run_storage_maintenance(compact=False)
            if monotonic() >= next_maintenance:
                await self._run_storage_maintenance(compact=True)
                next_maintenance = (
                    monotonic() + self.policy.storage_policy.maintenance_interval_seconds
                )

    async def _commit_storage_batch(
        self,
        batch: Sequence[EventEnvelope],
        *,
        flush: bool = False,
        close: bool = False,
    ) -> None:
        selected = tuple(batch)

        def commit() -> tuple[tuple[RawFileManifest, ...], RawDataQualityIndex | None]:
            manifests: list[RawFileManifest] = []
            for event in selected:
                manifests.extend(self._writer.append(event))
            if flush:
                manifests.extend(self._writer.flush())
            if close:
                manifests.extend(self._writer.close())
            selected_manifests = tuple(manifests)
            quality_index = None
            if selected_manifests:
                quality_index = update_raw_data_quality_index(
                    self.raw_output,
                    self._raw_quality_index_path,
                    storage_label=self.policy.storage_label,
                )
            return selected_manifests, quality_index

        manifests, quality_index = await asyncio.to_thread(commit)
        if quality_index is not None:
            self._raw_quality_index = quality_index
        self._record_manifests(manifests)
        for _ in selected:
            self._storage_queue.task_done()

    async def _on_error(self, error: UpbitAdapterError) -> None:
        self._parser_errors += 1
        self._last_error_type = type(error).__name__

    def _record_manifests(self, manifests: Sequence[RawFileManifest]) -> None:
        self._committed_files += len(manifests)
        self._committed_rows += sum(manifest.row_count for manifest in manifests)
        self._retained_files += len(manifests)
        self._retained_rows += sum(manifest.row_count for manifest in manifests)
        self._retained_bytes += sum(manifest.byte_size for manifest in manifests)

    async def _run_storage_maintenance(self, *, compact: bool) -> None:
        def maintain_and_index() -> tuple[RawStorageMaintenance, RawDataQualityIndex]:
            result = maintain_raw_storage(
                self.raw_output,
                policy=self.policy.storage_policy,
                compact=compact,
            )
            index = update_raw_data_quality_index(
                self.raw_output,
                self._raw_quality_index_path,
                storage_label=self.policy.storage_label,
            )
            return result, index

        result, self._raw_quality_index = await asyncio.to_thread(maintain_and_index)
        self._record_storage_maintenance(result, compact=compact)
        try:
            self._disk_free_bytes = require_raw_storage_capacity(
                self.raw_output, self.policy.storage_policy
            )
        except RawStorageCapacityError as exc:
            raise PaperRuntimeBlocked(str(exc)) from exc

    def _record_storage_maintenance(
        self,
        result: RawStorageMaintenance,
        *,
        compact: bool,
    ) -> None:
        self._retained_files = result.summary.file_count
        self._retained_rows = result.summary.row_count
        self._retained_bytes = result.summary.byte_size
        if compact and result.compacted_source_files:
            self._storage_compaction_runs += 1
        self._storage_compacted_source_files += result.compacted_source_files
        self._storage_retention_deleted_files += result.retention_deleted_files
        self._storage_capacity_deleted_files += result.capacity_deleted_files
        self._storage_reclaimed_bytes += result.reclaimed_bytes
        self._disk_free_bytes = result.disk_free_bytes

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
        if state in {PaperRuntimeState.STARTING, PaperRuntimeState.RUNNING}:
            try:
                self._disk_free_bytes = require_raw_storage_capacity(
                    self.raw_output, self.policy.storage_policy
                )
            except RawStorageCapacityError as exc:
                raise PaperRuntimeBlocked(str(exc)) from exc
            await self._refresh_dynamic_focus(now_utc)
        connected = self._client.connected if stopped_at_utc is None else False
        snapshot = PaperRuntimeSnapshot(
            run_id=self.run_id,
            state=state,
            started_at_utc=self.started_at_utc,
            updated_at_utc=now_utc,
            stopped_at_utc=stopped_at_utc,
            markets=self.markets,
            market_scope="all_krw" if self._universe_scanner is not None else "fixed",
            focused_markets=(
                self._universe_scanner.focused_markets
                if self._universe_scanner is not None
                else self.markets
            ),
            warning_market_count=(
                len(self._universe_scanner.warning_markets)
                if self._universe_scanner is not None
                else 0
            ),
            caution_market_count=(
                len(self._universe_scanner.caution_markets)
                if self._universe_scanner is not None
                else 0
            ),
            streams=self.streams,
            accepted_messages=sum(self._event_counts.values()),
            event_counts=tuple(sorted(self._event_counts.items())),
            duplicate_messages=self._duplicate_messages,
            parser_errors=self._parser_errors,
            reconnects=self._client.reconnect_count,
            committed_files=self._committed_files,
            committed_rows=self._committed_rows,
            retained_files=self._retained_files,
            retained_rows=self._retained_rows,
            retained_bytes=self._retained_bytes,
            storage_queue_depth=self._storage_queue.qsize(),
            storage_queue_capacity=self.policy.storage_queue_capacity,
            storage_queue_overflows=self._storage_queue_overflows,
            storage_label=self.policy.storage_label,
            storage_retention_days=self.policy.storage_policy.retention_days,
            storage_max_bytes=self.policy.storage_policy.max_bytes,
            storage_min_free_bytes=self.policy.storage_policy.min_free_bytes,
            storage_compaction_runs=self._storage_compaction_runs,
            storage_compacted_source_files=self._storage_compacted_source_files,
            storage_retention_deleted_files=self._storage_retention_deleted_files,
            storage_capacity_deleted_files=self._storage_capacity_deleted_files,
            storage_reclaimed_bytes=self._storage_reclaimed_bytes,
            disk_free_bytes=self._disk_free_bytes,
            quality_index_status=self._raw_quality_index.measurement_status,
            verified_manifest_count=self._raw_quality_index.verified_file_count,
            indexed_event_count=self._raw_quality_index.active_row_count,
            research_eligible_market_count=len(
                self._raw_quality_index.research_readiness.eligible_markets
            ),
            research_ready_for_preregistration=(
                self._raw_quality_index.research_readiness.ready_for_new_preregistration
            ),
            heartbeat_sequence=self._heartbeat_sequence,
            websocket_connected=connected,
            last_event_at_utc=self._last_event_at_utc,
            last_exchange_at_utc=self._last_exchange_at_utc,
            max_ingress_latency_ms=self._max_ingress_latency_ms,
            latest_ingress_latency_ms=self._latest_ingress_latency_ms,
            latest_exchange_clock_ahead_ms=self._latest_exchange_clock_ahead_ms,
            last_error_type=self._last_error_type,
            shutdown_reason=shutdown_reason,
            failure_type=failure_type,
            raw_output=self.raw_output.as_posix(),
            policy_hash=self.policy.digest,
        )
        if state in {PaperRuntimeState.STOPPED, PaperRuntimeState.FAILED}:
            continuity = self._continuity.stop(
                stopped_at_utc=now_utc,
                failed=state is PaperRuntimeState.FAILED,
                shutdown_reason=shutdown_reason or "paper_runtime_stopped",
                failure_type=failure_type,
                last_event_at_utc=self._last_event_at_utc,
                reconnect_count=self._client.reconnect_count,
            )
        else:
            continuity = self._continuity.observe(
                observed_at_utc=now_utc,
                websocket_connected=connected,
                last_event_at_utc=self._last_event_at_utc,
                reconnect_count=self._client.reconnect_count,
            )
        write_paper_runtime_snapshot(snapshot, self.output_root)
        write_paper_runtime_continuity_snapshot(continuity, self.output_root)
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
                now_utc,
                stale_after_seconds=self.policy.stale_after_seconds,
                selected_markets=(
                    self._universe_scanner.focused_markets
                    if self._universe_scanner is not None
                    else None
                ),
            ),
            system=SystemView(
                websocket_state=system_state,
                market_event_age_seconds=event_age,
                queue_depth=self._storage_queue.qsize(),
                parser_errors=self._parser_errors,
                clock_skew_ms=self._latest_exchange_clock_ahead_ms,
                latest_ingress_latency_ms=self._latest_ingress_latency_ms,
                max_ingress_latency_ms=self._max_ingress_latency_ms,
                disk_free_bytes=self._disk_free_bytes,
            ),
        )
        write_dashboard_snapshot(dashboard, self.output_root)
        realtime_snapshot = self._realtime.snapshot(generated_at_utc=now_utc)
        write_realtime_pipeline_snapshot(realtime_snapshot, self.output_root)
        universe_snapshot = None
        if self._universe_scanner is not None:
            universe_snapshot = self._universe_scanner.snapshot(generated_at_utc=now_utc)
            write_realtime_universe_snapshot(universe_snapshot, self.output_root)
        if state in {PaperRuntimeState.STARTING, PaperRuntimeState.RUNNING}:
            self._decision.persist_recovery_checkpoint(
                generated_at_utc=now_utc,
                clean_shutdown=False,
            )
        decision_snapshot = self._decision.snapshot(generated_at_utc=now_utc)
        write_realtime_paper_decision_snapshot(decision_snapshot, self.output_root)
        write_paper_monitor(
            dashboard,
            snapshot,
            self.output_root,
            realtime=realtime_snapshot,
            decision=decision_snapshot,
            universe=universe_snapshot,
            continuity=continuity,
        )
        self._write_work_audit_exports(
            runtime=snapshot,
            dashboard=dashboard,
            realtime=realtime_snapshot,
            decision=decision_snapshot,
            continuity=continuity,
        )
        return snapshot

    def _write_work_audit_exports(
        self,
        *,
        runtime: PaperRuntimeSnapshot,
        dashboard: DashboardSnapshot,
        realtime: RealtimePipelineSnapshot,
        decision: RealtimePaperDecisionSnapshot,
        continuity: PaperRuntimeContinuitySnapshot,
    ) -> None:
        generated_at_utc = runtime.updated_at_utc
        portfolios = decision.portfolios

        data_quality = DataQualitySnapshot.from_live_runtime(
            generated_at_utc=generated_at_utc,
            run_id=str(runtime.run_id),
            policy_hash=runtime.policy_hash,
            accepted_messages=runtime.accepted_messages,
            processed_events=realtime.processed_events,
            event_counts=runtime.event_counts,
            duplicate_count=max(runtime.duplicate_messages, realtime.duplicate_events),
            reconnects=runtime.reconnects,
            parse_errors=runtime.parser_errors,
            feature_frames=realtime.feature_frames,
            inference_ready_frames=realtime.inference_ready_frames,
            monitored_market_count=len(runtime.markets),
            observed_market_count=len(realtime.latest_features),
            last_event_at_utc=runtime.last_event_at_utc,
            storage_queue_depth=runtime.storage_queue_depth,
            storage_queue_overflows=runtime.storage_queue_overflows,
            processing_budget_breaches=realtime.processing_budget_breaches,
            raw_quality_index=self._raw_quality_index,
        )
        gross_pnl = sum((item.gross_pnl for item in portfolios), start=Decimal(0))
        net_pnl = sum((item.net_pnl for item in portfolios), start=Decimal(0))
        fees = sum((item.fees for item in portfolios), start=Decimal(0))
        spread_cost = sum((item.spread_cost for item in portfolios), start=Decimal(0))
        slippage_cost = sum((item.slippage_cost for item in portfolios), start=Decimal(0))
        adverse_selection_cost = sum(
            (item.adverse_selection_cost for item in portfolios),
            start=Decimal(0),
        )
        exposure = sum((item.market_value for item in portfolios), start=Decimal(0))
        event_age = (
            max(0.0, (generated_at_utc - runtime.last_event_at_utc).total_seconds())
            if runtime.last_event_at_utc is not None
            else None
        )
        baseline = WorkAuditBaseline(
            generated_at_utc=generated_at_utc,
            operations=WorkOperationsSnapshot(
                generated_at_utc=generated_at_utc,
                source_run_id=runtime.run_id,
                source_started_at_utc=runtime.started_at_utc,
                source_updated_at_utc=runtime.updated_at_utc,
                runtime_state=runtime.state.value,
                code_version=dashboard.overview.code_version,
                market_scope=runtime.market_scope,
                monitored_market_count=len(runtime.markets),
                focused_market_count=len(runtime.focused_markets),
                warning_market_count=runtime.warning_market_count,
                caution_market_count=runtime.caution_market_count,
                public_websocket_state=dashboard.system.websocket_state.value,
                last_event_at_utc=runtime.last_event_at_utc,
                market_event_age_seconds=event_age,
                accepted_messages=runtime.accepted_messages,
                event_counts=runtime.event_counts,
                duplicate_messages=runtime.duplicate_messages,
                parser_errors=runtime.parser_errors,
                reconnects=runtime.reconnects,
                storage_queue_depth=runtime.storage_queue_depth,
                storage_queue_capacity=runtime.storage_queue_capacity,
                storage_queue_overflows=runtime.storage_queue_overflows,
                max_ingress_latency_ms=runtime.max_ingress_latency_ms,
                latest_ingress_latency_ms=runtime.latest_ingress_latency_ms,
                latest_exchange_clock_ahead_ms=(runtime.latest_exchange_clock_ahead_ms),
                feature_latency_p99_ms=realtime.processing_latency_p99_ms,
                decision_latency_p99_ms=decision.decision_latency_p99_ms,
                paper_orders=decision.paper_orders,
                paper_fills=decision.paper_fills,
                unknown_orders=0,
                ledger_records=decision.ledger_records,
                recovery_status=decision.recovery_status.value,
                recovery_blocked=decision.recovery_blocked,
                continuity_integrity=continuity.integrity.value,
                continuity_measurement_started_at_utc=(continuity.measurement_started_at_utc),
                current_session_uptime_seconds=(continuity.current_session_uptime_seconds),
                previous_session_outcome=continuity.previous_session_outcome.value,
                last_shutdown_at_utc=continuity.last_shutdown_at_utc,
                last_shutdown_reason=continuity.last_shutdown_reason,
                unexpected_interruption_count=(continuity.unexpected_interruption_count),
                observed_websocket_gap_count=continuity.websocket_gap_count,
                observed_stale_data_gap_count=continuity.stale_data_gap_count,
                current_gap_kind=continuity.current_gap_kind.value,
                longest_current_session_gap_seconds=(
                    continuity.longest_current_session_gap_seconds
                ),
                six_hour_baseline_ready=continuity.six_hour_baseline_ready,
                twelve_hour_baseline_ready=continuity.twelve_hour_baseline_ready,
                gross_pnl_krw=gross_pnl,
                net_pnl_krw=net_pnl,
                fees_krw=fees,
                spread_cost_krw=spread_cost,
                slippage_cost_krw=slippage_cost,
                adverse_selection_cost_krw=adverse_selection_cost,
                exposure_krw=exposure,
                turnover_krw=decision.turnover_krw,
                retained_files=runtime.retained_files,
                retained_rows=runtime.retained_rows,
                retained_bytes=runtime.retained_bytes,
                storage_retention_days=runtime.storage_retention_days,
                storage_max_bytes=runtime.storage_max_bytes,
                storage_min_free_bytes=runtime.storage_min_free_bytes,
                disk_free_bytes=runtime.disk_free_bytes,
                storage_compaction_runs=runtime.storage_compaction_runs,
                storage_deleted_files=(
                    runtime.storage_retention_deleted_files + runtime.storage_capacity_deleted_files
                ),
                model_release_status=decision.model_release_status.value,
                model_approval_valid=decision.model_approval_valid,
            ),
            data_quality=data_quality,
            incidents=WorkIncidentSnapshot(
                generated_at_utc=generated_at_utc,
                source_state=AuditEvidenceState.NOT_CONFIGURED,
                complete=False,
                open_count=0,
                acknowledged_count=0,
                limitation=(
                    "The public paper runtime is not connected to the operations incident store."
                ),
            ),
            performance=WorkPerformanceSnapshot(
                generated_at_utc=generated_at_utc,
                source_run_id=runtime.run_id,
                window_started_at_utc=runtime.started_at_utc,
                sample_state=(
                    AuditEvidenceState.PARTIAL
                    if decision.paper_fills
                    else AuditEvidenceState.INSUFFICIENT_SAMPLE
                ),
                representative=False,
                observed_market_count=len(portfolios),
                paper_order_count=decision.paper_orders,
                paper_fill_count=decision.paper_fills,
                closed_trade_count=None,
                strategy_trade_proposals=decision.strategy_trade_proposals,
                risk_approvals=decision.risk_approvals,
                gross_pnl_krw=gross_pnl,
                fees_krw=fees,
                spread_cost_krw=spread_cost,
                slippage_cost_krw=slippage_cost,
                adverse_selection_cost_krw=adverse_selection_cost,
                net_pnl_krw=net_pnl,
                turnover_krw=decision.turnover_krw,
                exposure_krw=exposure,
                model_release_status=decision.model_release_status.value,
                model_approval_valid=decision.model_approval_valid,
                paper_order_simulation_enabled=(decision.paper_order_simulation_enabled),
                limitation=(
                    "No reviewed alpha or representative completed paper trade sample exists."
                ),
            ),
            models=WorkModelSnapshot(
                generated_at_utc=generated_at_utc,
                source_state=AuditEvidenceState.INSUFFICIENT_SAMPLE,
                active_approved_model_available=decision.model_approval_valid,
                model_release_status=decision.model_release_status.value,
                model_approval_valid=decision.model_approval_valid,
                observed_components=(
                    "always-neutral-alpha-baseline",
                    "rule-regime-baseline",
                    "execution-rule-baseline",
                ),
                inference_frames=decision.inference_frames,
                inference_latency_p99_ms=decision.decision_latency_p99_ms,
                feature_distribution_state=AuditEvidenceState.PARTIAL,
                prediction_distribution_state=AuditEvidenceState.INSUFFICIENT_SAMPLE,
                calibration_state=AuditEvidenceState.INSUFFICIENT_SAMPLE,
                drift_state=AuditEvidenceState.INSUFFICIENT_SAMPLE,
                limitation=(
                    "Only unapproved neutral baseline inference is active; "
                    "drift claims are unavailable."
                ),
            ),
        )
        self._audit_export_writer.write(baseline)

    async def _refresh_dynamic_focus(self, now_utc: datetime) -> None:
        if self._universe_scanner is None or self._subscription_builder is None:
            return
        if self._decision.paper_order_simulation_available:
            return
        previous = self._universe_scanner.focused_markets
        selected = self._universe_scanner.select(now_utc=now_utc)
        if selected == previous:
            return
        await self._client.replace_subscriptions(self._subscription_builder(selected))

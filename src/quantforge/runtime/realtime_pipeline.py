"""Incremental, measured real-time feature path that remains paper-HOLD only."""

import math
import os
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from time import perf_counter_ns
from typing import Annotated
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import EventEnvelope, deterministic_execution_id
from quantforge.exchange.upbit.schemas import AskBid, UpbitOrderbook, UpbitTicker, UpbitTrade
from quantforge.operations.exports import assert_runtime_export_safe


class RealtimeDecisionState(StrEnum):
    HOLD = "HOLD"


class RealtimeFeatureFrame(BaseModel):
    """Latest causal public-market state prepared for later approved inference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "realtime-feature-frame-1"
    frame_id: UUID
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    source_event_id: UUID
    source_event_type: str
    sequence: Annotated[int, Field(ge=1)]
    event_time_utc: datetime
    available_at_utc: datetime
    best_bid: Decimal | None = Field(default=None, gt=0)
    best_ask: Decimal | None = Field(default=None, gt=0)
    mid_price: Decimal | None = Field(default=None, gt=0)
    microprice: Decimal | None = Field(default=None, gt=0)
    spread_bps: float | None = None
    top_book_imbalance: float | None = Field(default=None, ge=-1, le=1)
    total_book_imbalance: float | None = Field(default=None, ge=-1, le=1)
    bid_depth_krw: Decimal | None = Field(default=None, ge=0)
    ask_depth_krw: Decimal | None = Field(default=None, ge=0)
    book_flow_delta: float | None = None
    last_trade_price: Decimal | None = Field(default=None, gt=0)
    last_trade_volume: Decimal | None = Field(default=None, gt=0)
    last_trade_side: str | None = Field(default=None, pattern=r"^(BID|ASK)$")
    trade_count_1s: Annotated[int, Field(ge=0)] = 0
    trade_count_5s: Annotated[int, Field(ge=0)] = 0
    trade_count_15s: Annotated[int, Field(ge=0)] = 0
    trade_imbalance_1s: float | None = Field(default=None, ge=-1, le=1)
    trade_imbalance_5s: float | None = Field(default=None, ge=-1, le=1)
    trade_imbalance_15s: float | None = Field(default=None, ge=-1, le=1)
    trade_return_1s_bps: float | None = None
    trade_return_5s_bps: float | None = None
    trade_return_15s_bps: float | None = None
    realized_volatility_15s_bps: float | None = Field(default=None, ge=0)
    turnover_24h_krw: Decimal | None = Field(default=None, ge=0)
    ticker_change_rate: Decimal | None = None
    ingress_latency_ms: float
    book_age_ms: float | None = Field(default=None, ge=0)
    trade_age_ms: float | None = Field(default=None, ge=0)
    ticker_age_ms: float | None = Field(default=None, ge=0)
    ready_for_inference: bool
    hold_reasons: tuple[str, ...]
    quality_warnings: tuple[str, ...] = ()

    @field_validator("event_time_utc", "available_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("real-time feature timestamps must be UTC-aware")
        return value

    @field_validator("spread_bps", "ingress_latency_ms")
    @classmethod
    def require_finite_measurement(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("real-time feature measurements must be finite")
        return value

    @model_validator(mode="after")
    def validate_readiness(self) -> "RealtimeFeatureFrame":
        if self.ready_for_inference == bool(self.hold_reasons):
            raise ValueError("feature readiness and hold reasons are inconsistent")
        return self


class RealtimePipelineSnapshot(BaseModel):
    """Secret-free performance and HOLD evidence for one incremental pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "realtime-pipeline-1"
    generated_at_utc: datetime
    markets: tuple[str, ...] = Field(min_length=1)
    processed_events: Annotated[int, Field(ge=0)]
    feature_frames: Annotated[int, Field(ge=0)]
    inference_ready_frames: Annotated[int, Field(ge=0)]
    duplicate_events: Annotated[int, Field(ge=0)]
    processing_budget_ms: float = Field(gt=0)
    processing_budget_breaches: Annotated[int, Field(ge=0)]
    processing_latency_p50_ms: float = Field(ge=0)
    processing_latency_p95_ms: float = Field(ge=0)
    processing_latency_p99_ms: float = Field(ge=0)
    processing_latency_max_ms: float = Field(ge=0)
    observed_events_per_second: float = Field(ge=0)
    decision_state: RealtimeDecisionState = RealtimeDecisionState.HOLD
    decision_reason: str
    approved_model_available: bool = False
    strategy_order_capability: bool = False
    private_network_used: bool = False
    order_submission_available: bool = False
    live_submission_allowed: bool = False
    latest_features: tuple[RealtimeFeatureFrame, ...] = ()

    @field_validator("generated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("real-time pipeline timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_closed_order_path(self) -> "RealtimePipelineSnapshot":
        if any(
            (
                self.approved_model_available,
                self.strategy_order_capability,
                self.private_network_used,
                self.order_submission_available,
                self.live_submission_allowed,
            )
        ):
            raise ValueError("phase 11.1 real-time pipeline must remain HOLD-only")
        if self.inference_ready_frames > self.feature_frames:
            raise ValueError("ready frames cannot exceed all feature frames")
        return self


@dataclass(frozen=True, slots=True)
class _TradePoint:
    received_at_utc: datetime
    price: Decimal
    volume: Decimal
    side: AskBid

    @property
    def quote_volume(self) -> Decimal:
        return self.price * self.volume


@dataclass(slots=True)
class _TradeWindow:
    seconds: int
    points: deque[_TradePoint] = field(default_factory=deque)
    buy_quote: Decimal = Decimal(0)
    sell_quote: Decimal = Decimal(0)
    squared_returns: float = 0.0

    def append(self, point: _TradePoint, now_utc: datetime) -> None:
        if self.points and self.points[-1].price > 0:
            value = float((point.price - self.points[-1].price) / self.points[-1].price)
            self.squared_returns += value * value
        self.points.append(point)
        if point.side is AskBid.BID:
            self.buy_quote += point.quote_volume
        else:
            self.sell_quote += point.quote_volume
        self.prune(now_utc)

    def prune(self, now_utc: datetime) -> None:
        cutoff = now_utc - timedelta(seconds=self.seconds)
        while self.points and self.points[0].received_at_utc <= cutoff:
            expired = self.points.popleft()
            if self.points and expired.price > 0:
                value = float((self.points[0].price - expired.price) / expired.price)
                self.squared_returns = max(0.0, self.squared_returns - value * value)
            if expired.side is AskBid.BID:
                self.buy_quote -= expired.quote_volume
            else:
                self.sell_quote -= expired.quote_volume

    @property
    def imbalance(self) -> float | None:
        total = self.buy_quote + self.sell_quote
        return float((self.buy_quote - self.sell_quote) / total) if total else None

    @property
    def return_bps(self) -> float | None:
        if len(self.points) < 2 or self.points[0].price <= 0:
            return None
        return float((self.points[-1].price - self.points[0].price) / self.points[0].price * 10_000)

    @property
    def realized_volatility_bps(self) -> float | None:
        return math.sqrt(self.squared_returns) * 10_000 if len(self.points) >= 3 else None


@dataclass(slots=True)
class _MarketState:
    sequence: int = 0
    last_available_at_utc: datetime | None = None
    book_at_utc: datetime | None = None
    trade_at_utc: datetime | None = None
    ticker_at_utc: datetime | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    mid_price: Decimal | None = None
    microprice: Decimal | None = None
    spread_bps: float | None = None
    top_book_imbalance: float | None = None
    total_book_imbalance: float | None = None
    bid_depth_krw: Decimal | None = None
    ask_depth_krw: Decimal | None = None
    book_flow_delta: float | None = None
    previous_book_pressure: float | None = None
    last_trade_price: Decimal | None = None
    last_trade_volume: Decimal | None = None
    last_trade_side: AskBid | None = None
    turnover_24h_krw: Decimal | None = None
    ticker_change_rate: Decimal | None = None
    windows: dict[int, _TradeWindow] = field(
        default_factory=lambda: {seconds: _TradeWindow(seconds) for seconds in (1, 5, 15)}
    )


class RealtimePaperPipeline:
    """Synchronous event-hot-path state with bounded latency evidence and no order port."""

    def __init__(
        self,
        markets: tuple[str, ...],
        *,
        stale_after_ms: float = 1_000,
        processing_budget_ms: float = 5,
        latency_window_size: int = 20_000,
        clock_ns: Callable[[], int] = perf_counter_ns,
    ) -> None:
        if not markets or len(set(markets)) != len(markets):
            raise ValueError("real-time pipeline markets must be nonempty and unique")
        if stale_after_ms <= 0 or processing_budget_ms <= 0 or latency_window_size < 1:
            raise ValueError("real-time pipeline bounds must be positive")
        self.markets = markets
        self.stale_after_ms = stale_after_ms
        self.processing_budget_ms = processing_budget_ms
        self._clock_ns = clock_ns
        self._states = {market: _MarketState() for market in markets}
        self._latencies_ms: deque[float] = deque(maxlen=latency_window_size)
        self._latest: dict[str, RealtimeFeatureFrame] = {}
        self._processed_events = 0
        self._feature_frames = 0
        self._inference_ready_frames = 0
        self._duplicate_events = 0
        self._budget_breaches = 0
        self._first_event_at_utc: datetime | None = None
        self._last_event_at_utc: datetime | None = None

    def process(self, event: EventEnvelope) -> RealtimeFeatureFrame | None:
        started_ns = self._clock_ns()
        try:
            state = self._states.get(event.market)
            if state is None:
                raise ValueError("event market is outside the real-time pipeline universe")
            if event.is_duplicate:
                self._duplicate_events += 1
                return None
            if (
                state.last_available_at_utc is not None
                and event.received_at_utc < state.last_available_at_utc
            ):
                raise ValueError("real-time events require nondecreasing availability")
            state.last_available_at_utc = event.received_at_utc
            state.sequence += 1
            if event.event_type == "orderbook":
                self._ingest_book(state, UpbitOrderbook.model_validate(event.raw_payload), event)
            elif event.event_type == "trade":
                self._ingest_trade(state, UpbitTrade.model_validate(event.raw_payload), event)
            else:
                self._ingest_ticker(state, UpbitTicker.model_validate(event.raw_payload), event)
            frame = self._frame(state, event)
            self._latest[event.market] = frame
            self._processed_events += 1
            self._feature_frames += 1
            self._inference_ready_frames += int(frame.ready_for_inference)
            if self._first_event_at_utc is None:
                self._first_event_at_utc = event.received_at_utc
            self._last_event_at_utc = event.received_at_utc
            return frame
        finally:
            elapsed_ms = max(0, self._clock_ns() - started_ns) / 1_000_000
            self._latencies_ms.append(elapsed_ms)
            self._budget_breaches += int(elapsed_ms > self.processing_budget_ms)

    def snapshot(self, *, generated_at_utc: datetime) -> RealtimePipelineSnapshot:
        latencies = sorted(self._latencies_ms)
        elapsed_seconds = (
            (self._last_event_at_utc - self._first_event_at_utc).total_seconds()
            if self._first_event_at_utc is not None and self._last_event_at_utc is not None
            else 0
        )
        rate = self._processed_events / elapsed_seconds if elapsed_seconds > 0 else 0.0
        latest = tuple(self._latest[market] for market in self.markets if market in self._latest)
        return RealtimePipelineSnapshot(
            generated_at_utc=generated_at_utc,
            markets=self.markets,
            processed_events=self._processed_events,
            feature_frames=self._feature_frames,
            inference_ready_frames=self._inference_ready_frames,
            duplicate_events=self._duplicate_events,
            processing_budget_ms=self.processing_budget_ms,
            processing_budget_breaches=self._budget_breaches,
            processing_latency_p50_ms=self._percentile(latencies, 0.50),
            processing_latency_p95_ms=self._percentile(latencies, 0.95),
            processing_latency_p99_ms=self._percentile(latencies, 0.99),
            processing_latency_max_ms=max(latencies, default=0.0),
            observed_events_per_second=rate,
            decision_reason="NO_APPROVED_REALTIME_MODEL",
            latest_features=latest,
        )

    def _frame(self, state: _MarketState, event: EventEnvelope) -> RealtimeFeatureFrame:
        now = event.received_at_utc
        for window in state.windows.values():
            window.prune(now)
        ages = {
            "book": self._age_ms(state.book_at_utc, now),
            "trade": self._age_ms(state.trade_at_utc, now),
            "ticker": self._age_ms(state.ticker_at_utc, now),
        }
        reasons: list[str] = []
        for source in ("book", "trade"):
            age = ages[source]
            if age is None:
                reasons.append(f"{source.upper()}_MISSING")
            elif age > self.stale_after_ms:
                reasons.append(f"{source.upper()}_STALE")
        warnings: list[str] = []
        ticker_age = ages["ticker"]
        if ticker_age is None:
            warnings.append("TICKER_MISSING")
        elif ticker_age > self.stale_after_ms:
            warnings.append("TICKER_STALE")
        window_15 = state.windows[15]
        if len(window_15.points) < 2:
            reasons.append("TRADE_HISTORY_WARMUP")
        if state.spread_bps is not None and state.spread_bps < 0:
            reasons.append("BOOK_CROSSED")
        if "exchange_clock_ahead" in event.quality_flags:
            reasons.append("EXCHANGE_CLOCK_AHEAD")
        if "local_clock_regression" in event.quality_flags:
            reasons.append("LOCAL_CLOCK_REGRESSION")
        return RealtimeFeatureFrame(
            frame_id=deterministic_execution_id("realtime-feature", event.event_id, state.sequence),
            market=event.market,
            source_event_id=event.event_id,
            source_event_type=event.event_type,
            sequence=state.sequence,
            event_time_utc=event.exchange_timestamp,
            available_at_utc=event.received_at_utc,
            best_bid=state.best_bid,
            best_ask=state.best_ask,
            mid_price=state.mid_price,
            microprice=state.microprice,
            spread_bps=state.spread_bps,
            top_book_imbalance=state.top_book_imbalance,
            total_book_imbalance=state.total_book_imbalance,
            bid_depth_krw=state.bid_depth_krw,
            ask_depth_krw=state.ask_depth_krw,
            book_flow_delta=state.book_flow_delta,
            last_trade_price=state.last_trade_price,
            last_trade_volume=state.last_trade_volume,
            last_trade_side=state.last_trade_side.value if state.last_trade_side else None,
            trade_count_1s=len(state.windows[1].points),
            trade_count_5s=len(state.windows[5].points),
            trade_count_15s=len(window_15.points),
            trade_imbalance_1s=state.windows[1].imbalance,
            trade_imbalance_5s=state.windows[5].imbalance,
            trade_imbalance_15s=window_15.imbalance,
            trade_return_1s_bps=state.windows[1].return_bps,
            trade_return_5s_bps=state.windows[5].return_bps,
            trade_return_15s_bps=window_15.return_bps,
            realized_volatility_15s_bps=window_15.realized_volatility_bps,
            turnover_24h_krw=state.turnover_24h_krw,
            ticker_change_rate=state.ticker_change_rate,
            ingress_latency_ms=event.ingress_latency_us / 1_000,
            book_age_ms=ages["book"],
            trade_age_ms=ages["trade"],
            ticker_age_ms=ages["ticker"],
            ready_for_inference=not reasons,
            hold_reasons=tuple(reasons),
            quality_warnings=tuple(warnings),
        )

    @staticmethod
    def _ingest_book(state: _MarketState, book: UpbitOrderbook, event: EventEnvelope) -> None:
        asks = sorted(book.orderbook_units, key=lambda unit: unit.ask_price)
        bids = sorted(book.orderbook_units, key=lambda unit: unit.bid_price, reverse=True)
        best_ask = asks[0]
        best_bid = bids[0]
        mid = (best_ask.ask_price + best_bid.bid_price) / Decimal(2)
        spread = best_ask.ask_price - best_bid.bid_price
        top_size = best_bid.bid_size + best_ask.ask_size
        total_bid_size = sum((unit.bid_size for unit in bids), start=Decimal(0))
        total_ask_size = sum((unit.ask_size for unit in asks), start=Decimal(0))
        total_size = total_bid_size + total_ask_size
        pressure = float((total_bid_size - total_ask_size) / total_size) if total_size else None
        state.book_flow_delta = (
            pressure - state.previous_book_pressure
            if pressure is not None and state.previous_book_pressure is not None
            else None
        )
        state.previous_book_pressure = pressure
        state.book_at_utc = event.received_at_utc
        state.best_bid = best_bid.bid_price
        state.best_ask = best_ask.ask_price
        state.mid_price = mid
        state.microprice = (
            (best_ask.ask_price * best_bid.bid_size + best_bid.bid_price * best_ask.ask_size)
            / top_size
            if top_size
            else mid
        )
        state.spread_bps = float(spread / mid * 10_000)
        state.top_book_imbalance = (
            float((best_bid.bid_size - best_ask.ask_size) / top_size) if top_size else None
        )
        state.total_book_imbalance = pressure
        state.bid_depth_krw = sum(
            (unit.bid_price * unit.bid_size for unit in bids), start=Decimal(0)
        )
        state.ask_depth_krw = sum(
            (unit.ask_price * unit.ask_size for unit in asks), start=Decimal(0)
        )

    @staticmethod
    def _ingest_trade(state: _MarketState, trade: UpbitTrade, event: EventEnvelope) -> None:
        point = _TradePoint(
            event.received_at_utc, trade.trade_price, trade.trade_volume, trade.ask_bid
        )
        for window in state.windows.values():
            window.append(point, event.received_at_utc)
        state.trade_at_utc = event.received_at_utc
        state.last_trade_price = trade.trade_price
        state.last_trade_volume = trade.trade_volume
        state.last_trade_side = trade.ask_bid

    @staticmethod
    def _ingest_ticker(state: _MarketState, ticker: UpbitTicker, event: EventEnvelope) -> None:
        state.ticker_at_utc = event.received_at_utc
        state.turnover_24h_krw = ticker.acc_trade_price_24h
        state.ticker_change_rate = ticker.signed_change_rate

    @staticmethod
    def _age_ms(occurred_at: datetime | None, now: datetime) -> float | None:
        return max(0.0, (now - occurred_at).total_seconds() * 1_000) if occurred_at else None

    @staticmethod
    def _percentile(values: list[float], ratio: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, math.ceil(len(values) * ratio) - 1)
        return values[index]


def write_realtime_pipeline_snapshot(snapshot: RealtimePipelineSnapshot, output_root: Path) -> Path:
    payload = snapshot.model_dump(mode="json")
    assert_runtime_export_safe(payload)
    destination_dir = output_root / "ops"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "realtime-pipeline.json"
    temporary = destination_dir / f".realtime-pipeline.{uuid4().hex}.tmp"
    encoded = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def read_realtime_pipeline_snapshot(path: Path) -> RealtimePipelineSnapshot:
    payload = orjson.loads(path.read_bytes())
    assert_runtime_export_safe(payload)
    return RealtimePipelineSnapshot.model_validate(payload)

"""Broad KRW monitoring with bounded, rotating short-horizon focus selection."""

import os
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import EventEnvelope
from quantforge.exchange.upbit.schemas import UpbitTicker
from quantforge.operations.exports import assert_runtime_export_safe


@dataclass(frozen=True, slots=True)
class RealtimeUniversePolicy:
    focus_limit: int = 20
    activity_window_seconds: float = 60.0
    max_ticker_age_seconds: float = 5.0
    minimum_rotation_interval_seconds: float = 60.0
    minimum_turnover_24h_krw: Decimal = Decimal("1000000000")

    def __post_init__(self) -> None:
        if self.focus_limit < 1:
            raise ValueError("universe focus limit must be positive")
        if (
            self.activity_window_seconds <= 0
            or self.max_ticker_age_seconds <= 0
            or self.minimum_rotation_interval_seconds <= 0
        ):
            raise ValueError("universe timing bounds must be positive")
        if self.minimum_turnover_24h_krw < 0:
            raise ValueError("minimum turnover cannot be negative")


class UniverseFocusScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    activity_events: int = Field(ge=0)
    short_move_bps: Decimal
    turnover_24h_krw: Decimal = Field(ge=0)
    opportunity_score: Decimal = Field(ge=0)


class RealtimeUniverseSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["realtime-universe-1"] = "realtime-universe-1"
    generated_at_utc: datetime
    market_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    monitored_market_count: int = Field(gt=0)
    eligible_market_count: int = Field(gt=0)
    warning_markets: tuple[str, ...]
    caution_markets: tuple[str, ...]
    focused_markets: tuple[str, ...] = Field(min_length=1)
    ranked_focus: tuple[UniverseFocusScore, ...]
    ticker_coverage_count: int = Field(ge=0)
    focus_rotation_count: int = Field(ge=0)
    trading_mode: str = "paper"
    order_submission_available: bool = False
    live_submission_allowed: bool = False

    @field_validator("generated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("universe snapshot timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def remain_orderless(self) -> "RealtimeUniverseSnapshot":
        if self.order_submission_available or self.live_submission_allowed:
            raise ValueError("paper universe scanner cannot expose order submission")
        if len(self.focused_markets) > self.eligible_market_count:
            raise ValueError("focused markets cannot exceed the eligible universe")
        return self


class RealtimeUniverseScanner:
    """Rank all eligible KRW tickers while limiting detailed market processing."""

    def __init__(
        self,
        markets: Sequence[str],
        *,
        eligible_markets: Sequence[str],
        initial_focus_markets: Sequence[str],
        warning_markets: Sequence[str] = (),
        caution_markets: Sequence[str] = (),
        market_set_hash: str,
        policy: RealtimeUniversePolicy | None = None,
    ) -> None:
        self.markets = tuple(markets)
        self.eligible_markets = tuple(eligible_markets)
        self.warning_markets = tuple(sorted(warning_markets))
        self.caution_markets = tuple(sorted(caution_markets))
        self.market_set_hash = market_set_hash
        self.policy = policy or RealtimeUniversePolicy()
        if not self.markets or not self.eligible_markets:
            raise ValueError("universe scanner requires monitored and eligible markets")
        if not set(self.eligible_markets).issubset(set(self.markets)):
            raise ValueError("eligible markets must be monitored")
        initial = tuple(initial_focus_markets)
        if not initial or not set(initial).issubset(set(self.eligible_markets)):
            raise ValueError("initial focus must contain only eligible markets")
        self._focus = initial[: self.policy.focus_limit]
        self._tickers: dict[str, UpbitTicker] = {}
        self._activity: dict[str, deque[datetime]] = {
            market: deque(maxlen=10_000) for market in self.markets
        }
        self._prices: dict[str, deque[tuple[datetime, Decimal]]] = {
            market: deque(maxlen=2_000) for market in self.markets
        }
        self._rotation_count = 0
        self._last_rotation_at_utc: datetime | None = None
        self._latest_ranking: tuple[UniverseFocusScore, ...] = ()

    @property
    def focused_markets(self) -> tuple[str, ...]:
        return self._focus

    def ingest(self, event: EventEnvelope) -> None:
        if event.is_duplicate or event.event_type != "ticker":
            return
        ticker = UpbitTicker.model_validate(event.raw_payload)
        self._tickers[event.market] = ticker
        self._activity[event.market].append(event.received_at_utc)
        self._prices[event.market].append((event.received_at_utc, ticker.trade_price))

    def select(self, *, now_utc: datetime) -> tuple[str, ...]:
        self._require_utc(now_utc)
        ranked = self._rank(now_utc)
        selected = tuple(item.market for item in ranked[: self.policy.focus_limit])
        if len(selected) < self.policy.focus_limit:
            selected_list = list(selected)
            for market in self._focus:
                if market not in selected_list and market in self.eligible_markets:
                    selected_list.append(market)
                if len(selected_list) >= self.policy.focus_limit:
                    break
            selected = tuple(selected_list)
        if not selected:
            selected = self._focus
        rotation_allowed = (
            self._last_rotation_at_utc is None
            or (now_utc - self._last_rotation_at_utc).total_seconds()
            >= self.policy.minimum_rotation_interval_seconds
        )
        if selected != self._focus and rotation_allowed:
            self._focus = selected
            self._rotation_count += 1
            self._last_rotation_at_utc = now_utc
        self._latest_ranking = ranked
        return self._focus

    def snapshot(self, *, generated_at_utc: datetime) -> RealtimeUniverseSnapshot:
        self._require_utc(generated_at_utc)
        return RealtimeUniverseSnapshot(
            generated_at_utc=generated_at_utc,
            market_set_hash=self.market_set_hash,
            monitored_market_count=len(self.markets),
            eligible_market_count=len(self.eligible_markets),
            warning_markets=self.warning_markets,
            caution_markets=self.caution_markets,
            focused_markets=self._focus,
            ranked_focus=self._latest_ranking[: self.policy.focus_limit],
            ticker_coverage_count=len(self._tickers),
            focus_rotation_count=self._rotation_count,
        )

    def _rank(self, now_utc: datetime) -> tuple[UniverseFocusScore, ...]:
        scores: list[UniverseFocusScore] = []
        cutoff = now_utc.timestamp() - self.policy.activity_window_seconds
        for market in self.eligible_markets:
            ticker = self._tickers.get(market)
            if ticker is None:
                continue
            if ticker.market_state != "ACTIVE" or ticker.market_warning == "CAUTION":
                continue
            if ticker.is_trading_suspended is True:
                continue
            arrivals = self._activity[market]
            while arrivals and arrivals[0].timestamp() < cutoff:
                arrivals.popleft()
            prices = self._prices[market]
            while prices and prices[0][0].timestamp() < cutoff:
                prices.popleft()
            age = max(0.0, (now_utc - arrivals[-1]).total_seconds()) if arrivals else float("inf")
            if age > self.policy.max_ticker_age_seconds:
                continue
            if ticker.acc_trade_price_24h < self.policy.minimum_turnover_24h_krw:
                continue
            first = prices[0][1] if prices else ticker.trade_price
            last = prices[-1][1] if prices else ticker.trade_price
            move_bps = (last - first) / first * Decimal(10_000) if first > 0 else Decimal(0)
            scores.append(
                UniverseFocusScore(
                    market=market,
                    activity_events=len(arrivals),
                    short_move_bps=move_bps,
                    turnover_24h_krw=ticker.acc_trade_price_24h,
                    opportunity_score=Decimal(len(arrivals)) * (abs(move_bps) + Decimal(1)),
                )
            )
        return tuple(
            sorted(
                scores,
                key=lambda item: (
                    -item.opportunity_score,
                    -item.turnover_24h_krw,
                    item.market,
                ),
            )
        )

    @staticmethod
    def _require_utc(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("universe scanner requires UTC timestamps")


def write_realtime_universe_snapshot(snapshot: RealtimeUniverseSnapshot, output_root: Path) -> Path:
    payload = snapshot.model_dump(mode="json")
    assert_runtime_export_safe(payload)
    destination_dir = output_root / "ops"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "realtime-universe.json"
    temporary = destination_dir / f".realtime-universe.{uuid4().hex}.tmp"
    encoded = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def read_realtime_universe_snapshot(path: Path) -> RealtimeUniverseSnapshot:
    payload = orjson.loads(path.read_bytes())
    assert_runtime_export_safe(payload)
    return RealtimeUniverseSnapshot.model_validate(payload)

"""Causal volatility features from closed, available trade bars."""

from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from itertools import pairwise
from math import log, pi, sqrt

from quantforge.domain import TradeBar
from quantforge.features.contracts import FeatureSnapshot, LookaheadViolation


class VolatilityFeatureCalculator:
    def __init__(self, *, ewma_lambda: float = 0.94, minimum_bars: int = 3) -> None:
        if not 0 < ewma_lambda < 1 or minimum_bars < 2:
            raise ValueError("EWMA lambda must be in (0,1) and minimum_bars at least two")
        self.ewma_lambda = ewma_lambda
        self.minimum_bars = minimum_bars

    def compute(
        self,
        bars: Sequence[TradeBar],
        *,
        market: str,
        as_of_utc: datetime,
    ) -> FeatureSnapshot:
        if as_of_utc.tzinfo is None or as_of_utc.utcoffset() != UTC.utcoffset(as_of_utc):
            raise ValueError("volatility feature as-of time must be UTC-aware")
        market_bars = [bar for bar in bars if bar.market == market]
        if any(bar.available_at_utc > as_of_utc for bar in market_bars):
            raise LookaheadViolation("volatility input contains a future-available bar")
        eligible = sorted(
            (
                bar
                for bar in market_bars
                if bar.is_complete and not bar.no_trade and not bar.data_gap
            ),
            key=lambda bar: (bar.end_utc, bar.interval_seconds, bar.bar_id),
        )
        if len(eligible) < self.minimum_bars:
            raise ValueError("insufficient complete traded bars for volatility features")
        closes = [float(bar.close) for bar in eligible if bar.close is not None]
        if len(closes) != len(eligible) or any(close <= 0 for close in closes):
            raise ValueError("volatility bars require positive closes")
        returns = [log(current / previous) for previous, current in pairwise(closes)]
        realized_variance = sum(value * value for value in returns)
        realized_volatility = sqrt(realized_variance)
        bipower = (pi / 2) * sum(
            abs(previous) * abs(current) for previous, current in pairwise(returns)
        )
        true_ranges: list[float] = []
        for index, bar in enumerate(eligible):
            assert bar.high is not None and bar.low is not None
            high = float(bar.high)
            low = float(bar.low)
            prior_close = closes[index - 1] if index else closes[index]
            true_ranges.append(max(high - low, abs(high - prior_close), abs(low - prior_close)))
        range_terms = [
            log(float(bar.high) / float(bar.low)) ** 2
            for bar in eligible
            if bar.high is not None and bar.low is not None and bar.low > 0
        ]
        ewma_variance = returns[0] ** 2
        for value in returns[1:]:
            ewma_variance = self.ewma_lambda * ewma_variance + (1 - self.ewma_lambda) * value**2
        squared_returns = [value * value for value in returns]
        mean_squared = sum(squared_returns) / len(squared_returns)
        vol_of_vol = sqrt(
            sum((value - mean_squared) ** 2 for value in squared_returns) / len(squared_returns)
        )
        downside = [value for value in returns if value < 0]
        values: dict[str, float | None] = {
            "log_return": returns[-1],
            "multi_horizon_return_1": returns[-1],
            "multi_horizon_return_5": (log(closes[-1] / closes[-6]) if len(closes) >= 6 else None),
            "realized_variance": realized_variance,
            "realized_volatility": realized_volatility,
            "bipower_variation": bipower,
            "jump_proxy": max(realized_variance - bipower, 0.0),
            "atr_baseline": sum(true_ranges) / len(true_ranges),
            "range_volatility": sqrt(sum(range_terms) / (4 * log(2))) if range_terms else None,
            "ewma_volatility": sqrt(ewma_variance),
            "har_like_short_rv": sum(squared_returns[-3:]),
            "har_like_medium_rv": sum(squared_returns[-12:]),
            "har_like_long_rv": realized_variance,
            "volatility_of_volatility": vol_of_vol,
            "downside_volatility": (
                sqrt(sum(value * value for value in downside)) if downside else 0.0
            ),
        }
        flags: list[str] = []
        if len(closes) < 6:
            flags.append("insufficient_multi_horizon_history")
        if any(bar.data_gap for bar in market_bars):
            flags.append("gaps_excluded")
        input_hash = sha256("\n".join(bar.source_hash for bar in eligible).encode()).hexdigest()
        return FeatureSnapshot(
            feature_set="volatility",
            feature_version="time-bar-volatility-v1",
            market=market,
            event_time_utc=eligible[-1].end_utc,
            available_at_utc=max(bar.available_at_utc for bar in eligible),
            computed_at_utc=as_of_utc,
            values=values,
            input_hash=input_hash,
            quality_flags=tuple(flags),
        )

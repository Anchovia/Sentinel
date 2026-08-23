"""Availability-filtered rolling trade-flow features."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from itertools import pairwise
from math import sqrt

from quantforge.domain import EventEnvelope
from quantforge.exchange.upbit.schemas import AskBid, UpbitTrade, parse_public_message
from quantforge.features.contracts import FeatureSnapshot, LookaheadViolation


def _trade_time(message: UpbitTrade) -> datetime:
    seconds, milliseconds = divmod(message.trade_timestamp, 1000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=milliseconds * 1000)


class TradeFeatureCalculator:
    def __init__(
        self,
        *,
        window_seconds: int = 60,
        large_trade_threshold: Decimal = Decimal("1"),
    ) -> None:
        if window_seconds < 1 or large_trade_threshold <= 0:
            raise ValueError("trade window and large-trade threshold must be positive")
        self.window_seconds = window_seconds
        self.large_trade_threshold = large_trade_threshold

    def compute(
        self,
        events: Sequence[EventEnvelope],
        *,
        market: str,
        as_of_utc: datetime,
        current_mid: Decimal | None = None,
    ) -> FeatureSnapshot:
        if as_of_utc.tzinfo is None or as_of_utc.utcoffset() != UTC.utcoffset(as_of_utc):
            raise ValueError("trade feature as-of time must be UTC-aware")
        relevant_events = [
            event
            for event in events
            if event.market == market and event.event_type == "trade" and not event.is_duplicate
        ]
        if any(event.received_at_utc > as_of_utc for event in relevant_events):
            raise LookaheadViolation("trade feature input contains a future-available event")
        cutoff = as_of_utc - timedelta(seconds=self.window_seconds)
        parsed: list[tuple[EventEnvelope, UpbitTrade]] = []
        for event in relevant_events:
            if event.received_at_utc <= cutoff:
                continue
            message, _ = parse_public_message(event.raw_payload_text)
            if isinstance(message, UpbitTrade):
                parsed.append((event, message))
        parsed.sort(
            key=lambda item: (
                item[0].received_at_utc,
                item[1].sequential_id,
                str(item[0].event_id),
            )
        )
        if not parsed:
            raise ValueError("no causal trade events are available in the requested window")

        messages = [message for _, message in parsed]
        buy_volume = sum(
            (message.trade_volume for message in messages if message.ask_bid is AskBid.BID),
            start=Decimal(0),
        )
        sell_volume = sum(
            (message.trade_volume for message in messages if message.ask_bid is AskBid.ASK),
            start=Decimal(0),
        )
        total_volume = buy_volume + sell_volume
        signed_volume = buy_volume - sell_volume
        quote_volume = sum(
            (message.trade_price * message.trade_volume for message in messages),
            start=Decimal(0),
        )
        vwap = quote_volume / total_volume
        times = [_trade_time(message) for message in messages]
        intervals = [(current - prior).total_seconds() for prior, current in pairwise(times)]
        interarrival_mean = sum(intervals) / len(intervals) if intervals else None
        interarrival_variance = (
            sum((value - interarrival_mean) ** 2 for value in intervals) / len(intervals)
            if intervals and interarrival_mean is not None
            else None
        )
        large = [
            message for message in messages if message.trade_volume >= self.large_trade_threshold
        ]
        last_side = messages[-1].ask_bid
        run_length = 0
        for message in reversed(messages):
            if message.ask_bid is not last_side:
                break
            run_length += 1
        prior_volumes = [float(message.trade_volume) for message in messages[:-1]]
        volume_shock: float | None = None
        intensity_zscore: float | None = None
        if prior_volumes:
            mean_volume = sum(prior_volumes) / len(prior_volumes)
            if mean_volume:
                volume_shock = float(messages[-1].trade_volume) / mean_volume - 1
            if len(prior_volumes) >= 2:
                variance = sum((value - mean_volume) ** 2 for value in prior_volumes) / len(
                    prior_volumes
                )
                intensity_zscore = (
                    (float(messages[-1].trade_volume) - mean_volume) / sqrt(variance)
                    if variance
                    else 0.0
                )

        last_price = messages[-1].trade_price
        values: dict[str, float | None] = {
            "signed_trade_volume": float(signed_volume),
            "aggressive_buy_volume": float(buy_volume),
            "aggressive_sell_volume": float(sell_volume),
            "trade_imbalance": float(signed_volume / total_volume),
            "trade_arrival_rate": len(messages) / self.window_seconds,
            "interarrival_mean": interarrival_mean,
            "interarrival_variance": interarrival_variance,
            "volume_weighted_trade_imbalance": float(signed_volume / total_volume),
            "large_trade_count": float(len(large)),
            "large_trade_volume": float(
                sum((message.trade_volume for message in large), start=Decimal(0))
            ),
            "buy_run_length": float(run_length if last_side is AskBid.BID else 0),
            "sell_run_length": float(run_length if last_side is AskBid.ASK else 0),
            "trade_price_vs_mid": (
                float((last_price - current_mid) / current_mid) if current_mid else None
            ),
            "short_term_vwap": float(vwap),
            "vwap_deviation": float((last_price - vwap) / vwap),
            "trade_intensity_zscore": intensity_zscore,
            "volume_shock": volume_shock,
        }
        quality: list[str] = []
        if len(messages) < 2:
            quality.append("insufficient_interarrival_history")
        if intensity_zscore is None:
            quality.append("insufficient_intensity_history")
        if current_mid is None:
            quality.append("mid_price_unavailable")
        input_hash = sha256(
            "\n".join(event.raw_payload_hash for event, _ in parsed).encode()
        ).hexdigest()
        return FeatureSnapshot(
            feature_set="trade_flow",
            feature_version="upbit-trade-window-v1",
            market=market,
            event_time_utc=max(event.exchange_timestamp for event, _ in parsed),
            available_at_utc=max(event.received_at_utc for event, _ in parsed),
            computed_at_utc=as_of_utc,
            values=values,
            input_hash=input_hash,
            quality_flags=tuple(quality),
        )

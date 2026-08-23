"""Causal Level-2 snapshot features with bounded rolling state."""

from collections import defaultdict, deque
from datetime import datetime
from decimal import Decimal
from math import sqrt

from quantforge.domain import EventEnvelope
from quantforge.exchange.upbit.schemas import (
    UpbitOrderbook,
    UpbitOrderbookUnit,
    parse_public_message,
)
from quantforge.features.contracts import FeatureSnapshot, LookaheadViolation


def _sum_depth(units: list[UpbitOrderbookUnit], depth: int, side: str) -> Decimal | None:
    if len(units) < depth:
        return None
    if side == "bid":
        return sum((unit.bid_size for unit in units[:depth]), start=Decimal(0))
    return sum((unit.ask_size for unit in units[:depth]), start=Decimal(0))


def _imbalance(bid: Decimal | None, ask: Decimal | None) -> float | None:
    if bid is None or ask is None or bid + ask == 0:
        return None
    return float((bid - ask) / (bid + ask))


def _zscore(value: float, history: deque[float]) -> float | None:
    if len(history) < 2:
        return None
    mean = sum(history) / len(history)
    variance = sum((item - mean) ** 2 for item in history) / len(history)
    if variance == 0:
        return 0.0
    return (value - mean) / sqrt(variance)


def _walk_impact(
    units: list[UpbitOrderbookUnit], target_volume: Decimal, side: str, mid: Decimal
) -> float | None:
    remaining = target_volume
    notional = Decimal(0)
    consumed = Decimal(0)
    for unit in units:
        price = unit.ask_price if side == "buy" else unit.bid_price
        size = unit.ask_size if side == "buy" else unit.bid_size
        take = min(remaining, size)
        notional += price * take
        consumed += take
        remaining -= take
        if remaining == 0:
            break
    if remaining > 0 or consumed == 0 or mid == 0:
        return None
    average = notional / consumed
    return float((average - mid) / mid if side == "buy" else (mid - average) / mid)


class OrderbookFeatureCalculator:
    def __init__(self, *, history_size: int = 60, impact_volume: Decimal = Decimal("0.1")) -> None:
        if history_size < 2 or impact_volume <= 0:
            raise ValueError("history_size must be at least two and impact_volume must be positive")
        self._history_size = history_size
        self._impact_volume = impact_volume
        self._previous: dict[str, UpbitOrderbook] = {}
        self._last_available: dict[str, datetime] = {}
        self._spread_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self._history_size)
        )
        self._depth_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self._history_size)
        )

    def compute(self, event: EventEnvelope, *, as_of_utc: datetime) -> FeatureSnapshot:
        if event.event_type != "orderbook":
            raise ValueError("orderbook calculator requires an orderbook event")
        if event.received_at_utc > as_of_utc:
            raise LookaheadViolation(
                "orderbook event was not available at the requested as-of time"
            )
        previous_available = self._last_available.get(event.market)
        if previous_available is not None and event.received_at_utc < previous_available:
            raise ValueError("stateful orderbook features require nondecreasing availability")
        message, _ = parse_public_message(event.raw_payload_text)
        if not isinstance(message, UpbitOrderbook):
            raise ValueError("event payload does not contain an orderbook")

        units = message.orderbook_units
        best = units[0]
        best_bid = best.bid_price
        best_ask = best.ask_price
        mid = (best_bid + best_ask) / Decimal(2)
        spread = best_ask - best_bid
        denominator = best.bid_size + best.ask_size
        weighted_mid = (
            (best_ask * best.bid_size + best_bid * best.ask_size) / denominator
            if denominator
            else None
        )
        quality: list[str] = []
        if best_bid > best_ask:
            quality.append("crossed_book")
        if denominator == 0:
            quality.append("empty_top_size")

        values: dict[str, float | None] = {
            "best_bid": float(best_bid),
            "best_ask": float(best_ask),
            "mid_price": float(mid),
            "spread": float(spread),
            "relative_spread": float(spread / mid) if mid else None,
            "weighted_mid": float(weighted_mid) if weighted_mid is not None else None,
            "microprice": float(weighted_mid) if weighted_mid is not None else None,
        }
        depths: dict[int, tuple[Decimal | None, Decimal | None]] = {}
        for depth in (1, 5, 15, 30):
            bid_depth = _sum_depth(units, depth, "bid")
            ask_depth = _sum_depth(units, depth, "ask")
            depths[depth] = (bid_depth, ask_depth)
            values[f"bid_depth_{depth}"] = float(bid_depth) if bid_depth is not None else None
            values[f"ask_depth_{depth}"] = float(ask_depth) if ask_depth is not None else None
            values[f"queue_imbalance_{depth}"] = _imbalance(bid_depth, ask_depth)
            if bid_depth is None or ask_depth is None:
                quality.append(f"partial_depth_{depth}")

        previous = self._previous.get(event.market)
        for depth in (1, 5, 15, 30):
            current_bid, current_ask = depths[depth]
            prior_bid = (
                _sum_depth(previous.orderbook_units, depth, "bid") if previous is not None else None
            )
            prior_ask = (
                _sum_depth(previous.orderbook_units, depth, "ask") if previous is not None else None
            )
            if (
                current_bid is not None
                and current_ask is not None
                and prior_bid is not None
                and prior_ask is not None
            ):
                values[f"snapshot_derived_ofi_{depth}"] = float(
                    (current_bid - prior_bid) - (current_ask - prior_ask)
                )
            else:
                values[f"snapshot_derived_ofi_{depth}"] = None

        total_bid = sum((unit.bid_size for unit in units), start=Decimal(0))
        total_ask = sum((unit.ask_size for unit in units), start=Decimal(0))
        total_depth = total_bid + total_ask
        values["book_pressure"] = _imbalance(total_bid, total_ask)
        values["depth_concentration"] = (
            float((best.bid_size + best.ask_size) / total_depth) if total_depth else None
        )
        values["orderbook_slope_bid"] = (
            float((best_bid - units[-1].bid_price) / mid / (len(units) - 1))
            if len(units) > 1 and mid
            else None
        )
        values["orderbook_slope_ask"] = (
            float((units[-1].ask_price - best_ask) / mid / (len(units) - 1))
            if len(units) > 1 and mid
            else None
        )
        buy_impact = _walk_impact(units, self._impact_volume, "buy", mid)
        sell_impact = _walk_impact(units, self._impact_volume, "sell", mid)
        values["price_impact_buy"] = buy_impact
        values["price_impact_sell"] = sell_impact
        values["estimated_market_buy_slippage"] = buy_impact
        values["estimated_market_sell_slippage"] = sell_impact
        prior_total = (
            sum(
                (unit.bid_size + unit.ask_size for unit in previous.orderbook_units),
                start=Decimal(0),
            )
            if previous is not None
            else None
        )
        values["book_resilience_proxy"] = (
            float((total_depth - prior_total) / prior_total) if prior_total else None
        )

        spread_float = float(spread)
        depth_float = float(total_depth)
        values["spread_zscore"] = _zscore(spread_float, self._spread_history[event.market])
        values["depth_zscore"] = _zscore(depth_float, self._depth_history[event.market])
        if values["spread_zscore"] is None:
            quality.append("insufficient_spread_history")
        if values["depth_zscore"] is None:
            quality.append("insufficient_depth_history")

        self._spread_history[event.market].append(spread_float)
        self._depth_history[event.market].append(depth_float)
        self._previous[event.market] = message
        self._last_available[event.market] = event.received_at_utc
        return FeatureSnapshot(
            feature_set="orderbook",
            feature_version="upbit-l2-v1",
            market=event.market,
            event_time_utc=event.exchange_timestamp,
            available_at_utc=event.received_at_utc,
            computed_at_utc=as_of_utc,
            values=values,
            input_hash=event.raw_payload_hash,
            quality_flags=tuple(dict.fromkeys((*event.quality_flags, *quality))),
        )

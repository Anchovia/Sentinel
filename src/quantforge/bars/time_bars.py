"""Batch time bars built from trade events and explicit collection coverage."""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

from quantforge.domain import (
    CoverageWindow,
    DataGap,
    EventEnvelope,
    SupportedInterval,
    TradeBar,
    deterministic_bar_id,
)
from quantforge.exchange.upbit.schemas import AskBid, UpbitTrade, parse_public_message

SUPPORTED_INTERVALS: tuple[SupportedInterval, ...] = (1, 5, 15, 60)


def _timestamp_ms_to_utc(value: int) -> datetime:
    seconds, milliseconds = divmod(value, 1000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=milliseconds * 1000)


def _overlaps(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    return start < other_end and other_start < end


def _fully_covered(start: datetime, end: datetime, windows: Sequence[CoverageWindow]) -> bool:
    cursor = start
    for window in sorted(windows, key=lambda item: (item.start_utc, item.end_utc)):
        if window.end_utc <= cursor or window.start_utc >= end:
            continue
        if window.start_utc > cursor:
            return False
        cursor = max(cursor, window.end_utc)
        if cursor >= end:
            return True
    return False


def _source_hash(parts: Iterable[str]) -> str:
    return sha256("\n".join(sorted(parts)).encode()).hexdigest()


class TimeBarBuilder:
    """Construct bars without inferring health from an absence of trades."""

    def __init__(self, intervals: Sequence[SupportedInterval] = SUPPORTED_INTERVALS) -> None:
        selected = tuple(intervals)
        if not selected or len(set(selected)) != len(selected):
            raise ValueError("bar intervals must be a non-empty unique sequence")
        if any(interval not in SUPPORTED_INTERVALS for interval in selected):
            raise ValueError("Phase 2 supports only 1s, 5s, 15s, and 60s bars")
        self.intervals = tuple(sorted(selected))

    def build(
        self,
        *,
        markets: Sequence[str],
        start_utc: datetime,
        end_utc: datetime,
        events: Sequence[EventEnvelope],
        coverage: Sequence[CoverageWindow],
        gaps: Sequence[DataGap] = (),
    ) -> list[TradeBar]:
        self._validate_range(markets, start_utc, end_utc)
        output: list[TradeBar] = []
        for market in sorted(set(markets)):
            market_events = [
                event
                for event in events
                if event.market == market and event.event_type == "trade" and not event.is_duplicate
            ]
            market_coverage = [window for window in coverage if window.market == market]
            market_gaps = [gap for gap in gaps if gap.market == market]
            for interval in self.intervals:
                cursor = start_utc
                while cursor < end_utc:
                    bucket_end = cursor + timedelta(seconds=interval)
                    output.append(
                        self._build_bucket(
                            market,
                            interval,
                            cursor,
                            bucket_end,
                            market_events,
                            market_coverage,
                            market_gaps,
                        )
                    )
                    cursor = bucket_end
        return sorted(output, key=lambda bar: (bar.start_utc, bar.market, bar.interval_seconds))

    @staticmethod
    def _validate_range(markets: Sequence[str], start_utc: datetime, end_utc: datetime) -> None:
        if not markets:
            raise ValueError("at least one market is required")
        if any(
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
            for value in (start_utc, end_utc)
        ):
            raise ValueError("bar range must be UTC-aware")
        if end_utc <= start_utc:
            raise ValueError("bar range end must be after start")
        if int(start_utc.timestamp()) % 60 or int(end_utc.timestamp()) % 60:
            raise ValueError("multi-timeframe build range must align to minute boundaries")

    @staticmethod
    def _build_bucket(
        market: str,
        interval: SupportedInterval,
        start: datetime,
        end: datetime,
        events: Sequence[EventEnvelope],
        coverage: Sequence[CoverageWindow],
        gaps: Sequence[DataGap],
    ) -> TradeBar:
        relevant_coverage = [
            window for window in coverage if _overlaps(start, end, window.start_utc, window.end_utc)
        ]
        relevant_gaps = [gap for gap in gaps if _overlaps(start, end, gap.start_utc, gap.end_utc)]
        coverage_complete = _fully_covered(start, end, relevant_coverage)
        if relevant_gaps or not coverage_complete:
            flags = ("explicit_data_gap",) if relevant_gaps else ("coverage_not_asserted",)
            known_times = [gap.known_at_utc for gap in relevant_gaps]
            known_times.extend(window.asserted_at_utc for window in relevant_coverage)
            return TradeBar(
                bar_id=deterministic_bar_id(market, interval, start),
                market=market,
                interval_seconds=interval,
                start_utc=start,
                end_utc=end,
                available_at_utc=max([end, *known_times]),
                open=None,
                high=None,
                low=None,
                close=None,
                volume=None,
                quote_volume=None,
                trade_count=None,
                aggressive_buy_volume=None,
                aggressive_sell_volume=None,
                vwap=None,
                first_trade_timestamp=None,
                last_trade_timestamp=None,
                is_complete=False,
                no_trade=False,
                data_gap=True,
                source_hash=_source_hash(
                    [gap.fingerprint() for gap in relevant_gaps]
                    + [
                        f"coverage|{window.start_utc.isoformat()}|{window.end_utc.isoformat()}"
                        for window in relevant_coverage
                    ]
                    + [f"bucket|{market}|{interval}|{start.isoformat()}"]
                ),
                quality_flags=flags,
            )

        trades: list[tuple[datetime, EventEnvelope, UpbitTrade]] = []
        for event in events:
            message, _ = parse_public_message(event.raw_payload_text)
            if not isinstance(message, UpbitTrade):
                continue
            trade_timestamp = _timestamp_ms_to_utc(message.trade_timestamp)
            if start <= trade_timestamp < end:
                trades.append((trade_timestamp, event, message))
        trades.sort(key=lambda item: (item[0], item[2].sequential_id, str(item[1].event_id)))
        source_parts = [event.raw_payload_hash for _, event, _ in trades]
        source_parts.extend(
            f"coverage|{window.start_utc.isoformat()}|{window.end_utc.isoformat()}"
            for window in relevant_coverage
        )
        if not trades:
            zero = Decimal(0)
            return TradeBar(
                bar_id=deterministic_bar_id(market, interval, start),
                market=market,
                interval_seconds=interval,
                start_utc=start,
                end_utc=end,
                available_at_utc=max(
                    [end, *(window.asserted_at_utc for window in relevant_coverage)]
                ),
                open=None,
                high=None,
                low=None,
                close=None,
                volume=zero,
                quote_volume=zero,
                trade_count=0,
                aggressive_buy_volume=zero,
                aggressive_sell_volume=zero,
                vwap=None,
                first_trade_timestamp=None,
                last_trade_timestamp=None,
                is_complete=True,
                no_trade=True,
                data_gap=False,
                source_hash=_source_hash([*source_parts, f"no-trade|{start.isoformat()}"]),
            )

        prices = [message.trade_price for _, _, message in trades]
        volumes = [message.trade_volume for _, _, message in trades]
        total_volume = sum(volumes, start=Decimal(0))
        quote_volume = sum(
            (message.trade_price * message.trade_volume for _, _, message in trades),
            start=Decimal(0),
        )
        aggressive_buy = sum(
            (message.trade_volume for _, _, message in trades if message.ask_bid is AskBid.BID),
            start=Decimal(0),
        )
        aggressive_sell = total_volume - aggressive_buy
        return TradeBar(
            bar_id=deterministic_bar_id(market, interval, start),
            market=market,
            interval_seconds=interval,
            start_utc=start,
            end_utc=end,
            available_at_utc=max(
                [
                    end,
                    *(event.received_at_utc for _, event, _ in trades),
                    *(window.asserted_at_utc for window in relevant_coverage),
                ]
            ),
            open=prices[0],
            high=max(prices),
            low=min(prices),
            close=prices[-1],
            volume=total_volume,
            quote_volume=quote_volume,
            trade_count=len(trades),
            aggressive_buy_volume=aggressive_buy,
            aggressive_sell_volume=aggressive_sell,
            vwap=quote_volume / total_volume,
            first_trade_timestamp=trades[0][0],
            last_trade_timestamp=trades[-1][0],
            is_complete=True,
            no_trade=False,
            data_gap=False,
            source_hash=_source_hash(source_parts),
        )

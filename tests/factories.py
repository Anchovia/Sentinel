from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

import orjson

from quantforge.domain import EventEnvelope, TradeBar, deterministic_bar_id
from quantforge.exchange.upbit.mapper import map_public_message
from quantforge.research import AlphaClass, LabeledExample

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def utc_ms(value: datetime) -> int:
    return int(value.timestamp()) * 1000 + value.microsecond // 1000


def make_trade_event(
    *,
    sequence: int,
    exchange_offset_ms: int,
    received_offset_ms: int,
    price: int = 100,
    volume: int = 1,
    ask_bid: str = "BID",
    connection: int = 1,
    market: str = "KRW-BTC",
) -> EventEnvelope:
    trade_time = BASE_TIME + timedelta(milliseconds=exchange_offset_ms)
    payload = {
        "type": "trade",
        "code": market,
        "timestamp": utc_ms(trade_time),
        "trade_date": "2026-01-01",
        "trade_time": trade_time.strftime("%H:%M:%S"),
        "trade_timestamp": utc_ms(trade_time),
        "trade_price": price,
        "trade_volume": volume,
        "ask_bid": ask_bid,
        "prev_closing_price": 99,
        "change": "RISE",
        "change_price": 1,
        "sequential_id": 10_000 + sequence,
        "best_ask_price": price + 1,
        "best_ask_size": 2,
        "best_bid_price": price - 1,
        "best_bid_size": 3,
        "stream_type": "REALTIME",
    }
    raw = orjson.dumps(payload)
    event = map_public_message(
        raw,
        received_at_utc=BASE_TIME + timedelta(milliseconds=received_offset_ms),
        received_monotonic_ns=sequence,
        connection_id=UUID(int=connection),
        subscription_id="test-subscription",
        local_sequence=sequence,
    )
    return event.model_copy(update={"event_id": UUID(int=sequence)})


def make_orderbook_event(
    *,
    sequence: int,
    received_offset_ms: int,
    asks: tuple[tuple[int | str, int | str], ...] = ((101, 1), (102, 2)),
    bids: tuple[tuple[int | str, int | str], ...] = ((99, 1), (98, 2)),
    connection: int = 1,
    market: str = "KRW-BTC",
) -> EventEnvelope:
    if len(asks) != len(bids):
        raise ValueError("synthetic Upbit orderbook sides must have equal lengths")
    event_time = BASE_TIME + timedelta(milliseconds=received_offset_ms)
    units = [
        {
            "ask_price": ask_price,
            "bid_price": bid_price,
            "ask_size": ask_size,
            "bid_size": bid_size,
        }
        for (ask_price, ask_size), (bid_price, bid_size) in zip(asks, bids, strict=True)
    ]
    payload = {
        "type": "orderbook",
        "code": market,
        "timestamp": utc_ms(event_time),
        "total_ask_size": str(sum(Decimal(str(size)) for _, size in asks)),
        "total_bid_size": str(sum(Decimal(str(size)) for _, size in bids)),
        "orderbook_units": units,
        "level": 0,
        "stream_type": "REALTIME",
    }
    raw = orjson.dumps(payload)
    event = map_public_message(
        raw,
        received_at_utc=event_time,
        received_monotonic_ns=sequence,
        connection_id=UUID(int=connection),
        subscription_id="test-subscription",
        local_sequence=sequence,
    )
    return event.model_copy(update={"event_id": UUID(int=sequence)})


def make_ticker_event(
    *,
    sequence: int,
    received_offset_ms: int,
    price: int = 100,
    connection: int = 1,
    market: str = "KRW-BTC",
) -> EventEnvelope:
    event_time = BASE_TIME + timedelta(milliseconds=received_offset_ms)
    payload = {
        "type": "ticker",
        "code": market,
        "opening_price": price - 5,
        "high_price": price + 5,
        "low_price": price - 10,
        "trade_price": price,
        "prev_closing_price": price - 1,
        "change": "RISE",
        "change_price": 1,
        "signed_change_price": 1,
        "change_rate": "0.01",
        "signed_change_rate": "0.01",
        "trade_volume": "0.1",
        "acc_trade_volume": "100",
        "acc_trade_volume_24h": "200",
        "acc_trade_price": "1000000",
        "acc_trade_price_24h": "2000000",
        "trade_date": "20260101",
        "trade_time": "000000",
        "trade_timestamp": utc_ms(event_time),
        "ask_bid": "BID",
        "acc_ask_volume": "40",
        "acc_bid_volume": "60",
        "highest_52_week_price": price + 50,
        "highest_52_week_date": "2025-12-01",
        "lowest_52_week_price": max(1, price - 50),
        "lowest_52_week_date": "2025-01-01",
        "market_state": "ACTIVE",
        "delisting_date": None,
        "market_warning": "NONE",
        "timestamp": utc_ms(event_time),
        "stream_type": "REALTIME",
    }
    raw = orjson.dumps(payload)
    event = map_public_message(
        raw,
        received_at_utc=event_time,
        received_monotonic_ns=sequence,
        connection_id=UUID(int=connection),
        subscription_id="test-subscription",
        local_sequence=sequence,
    )
    return event.model_copy(update={"event_id": UUID(int=sequence)})


def make_trade_bar(
    *,
    index: int,
    close: int,
    available_delay_seconds: int = 0,
    market: str = "KRW-BTC",
) -> TradeBar:
    start = BASE_TIME + timedelta(seconds=index)
    end = start + timedelta(seconds=1)
    price = Decimal(close)
    return TradeBar(
        bar_id=deterministic_bar_id(market, 1, start),
        market=market,
        interval_seconds=1,
        start_utc=start,
        end_utc=end,
        available_at_utc=end + timedelta(seconds=available_delay_seconds),
        open=price - 1,
        high=price + 1,
        low=price - 2,
        close=price,
        volume=Decimal(1),
        quote_volume=price,
        trade_count=1,
        aggressive_buy_volume=Decimal(1),
        aggressive_sell_volume=Decimal(0),
        vwap=price,
        first_trade_timestamp=start + timedelta(milliseconds=100),
        last_trade_timestamp=start + timedelta(milliseconds=100),
        is_complete=True,
        no_trade=False,
        data_gap=False,
        source_hash=sha256(f"bar-{index}-{close}".encode()).hexdigest(),
    )


def make_labeled_examples(count: int = 90) -> tuple[LabeledExample, ...]:
    examples: list[LabeledExample] = []
    for index in range(count):
        x = ((index % 30) - 15) / 5
        if x < -0.5:
            label = AlphaClass.DOWN
            future_return = -20.0
        elif x > 0.5:
            label = AlphaClass.UP
            future_return = 20.0
        else:
            label = AlphaClass.NEUTRAL
            future_return = 0.0
        event_time = BASE_TIME + timedelta(seconds=index)
        future_price = (
            "100.2" if label is AlphaClass.UP else "99.8" if label is AlphaClass.DOWN else "100"
        )
        examples.append(
            LabeledExample(
                example_id=UUID(int=50_000 + index),
                source_row_id=UUID(int=60_000 + index),
                market="KRW-BTC",
                event_time_utc=event_time,
                features_available_at_utc=event_time,
                label_end_utc=event_time + timedelta(seconds=1),
                label_available_at_utc=event_time + timedelta(seconds=1),
                values=(("volatility", abs(x)), ("x", x)),
                alpha_class=label,
                future_return_bps=future_return,
                current_reference_price="100",
                future_reference_price=future_price,
            )
        )
    return tuple(examples)

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from factories import BASE_TIME, make_trade_bar, make_trade_event
from quantforge.domain import EventEnvelope, TradeBar
from quantforge.exchange.upbit.mapper import map_public_message
from quantforge.features import (
    FeatureDefinition,
    FeatureRegistry,
    FeatureSnapshot,
    LookaheadViolation,
    OrderbookFeatureCalculator,
    TradeFeatureCalculator,
    VolatilityFeatureCalculator,
    default_feature_registry,
)

ORDERBOOK = Path(__file__).parents[1] / "fixtures" / "upbit" / "orderbook.synthetic.json"


def _orderbook_event(received_offset_seconds: int = 0) -> EventEnvelope:
    raw = ORDERBOOK.read_bytes()
    timestamp_ms = __import__("json").loads(raw)["timestamp"]
    exchange = datetime.fromtimestamp(timestamp_ms // 1000, tz=UTC).replace(
        microsecond=(timestamp_ms % 1000) * 1000
    )
    event = map_public_message(
        raw,
        received_at_utc=exchange + timedelta(milliseconds=100, seconds=received_offset_seconds),
        received_monotonic_ns=received_offset_seconds + 1,
        connection_id=UUID(int=1),
        subscription_id="features",
        local_sequence=received_offset_seconds + 1,
    )
    return event.model_copy(update={"event_id": UUID(int=received_offset_seconds + 1)})


def test_orderbook_features_handle_partial_depth_and_causal_history() -> None:
    calculator = OrderbookFeatureCalculator(impact_volume=Decimal("0.1"))
    first = _orderbook_event()
    snapshot = calculator.compute(first, as_of_utc=first.received_at_utc)
    assert snapshot.values["best_bid"] == 137001000.0
    assert snapshot.values["best_ask"] == 137002000.0
    assert snapshot.values["mid_price"] == 137001500.0
    assert snapshot.values["spread"] == 1000.0
    assert snapshot.values["queue_imbalance_1"] is not None
    assert snapshot.values["bid_depth_5"] is None
    assert "partial_depth_5" in snapshot.quality_flags
    assert snapshot.values["price_impact_buy"] is not None
    assert snapshot.values["snapshot_derived_ofi_1"] is None
    assert set(snapshot.values) <= {
        definition.name for definition in default_feature_registry().definitions
    }

    second = _orderbook_event(1)
    second_snapshot = calculator.compute(second, as_of_utc=second.received_at_utc)
    assert second_snapshot.values["snapshot_derived_ofi_1"] == 0.0
    third = _orderbook_event(2)
    third_snapshot = calculator.compute(third, as_of_utc=third.received_at_utc)
    assert third_snapshot.values["spread_zscore"] == 0.0
    assert third_snapshot.values["depth_zscore"] == 0.0


def test_orderbook_feature_leakage_and_state_order_fail_closed() -> None:
    event = _orderbook_event(1)
    calculator = OrderbookFeatureCalculator()
    with pytest.raises(LookaheadViolation):
        calculator.compute(event, as_of_utc=event.received_at_utc - timedelta(microseconds=1))
    trade = make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=150)
    with pytest.raises(ValueError, match="orderbook event"):
        calculator.compute(trade, as_of_utc=trade.received_at_utc)
    calculator.compute(event, as_of_utc=event.received_at_utc)
    with pytest.raises(ValueError, match="nondecreasing"):
        calculator.compute(_orderbook_event(), as_of_utc=event.received_at_utc)
    with pytest.raises(ValueError):
        OrderbookFeatureCalculator(history_size=1)


def test_trade_flow_features_follow_upbit_bid_buy_ask_sell_semantics() -> None:
    events = [
        make_trade_event(
            sequence=1,
            exchange_offset_ms=100,
            received_offset_ms=150,
            price=100,
            volume=1,
            ask_bid="BID",
        ),
        make_trade_event(
            sequence=2,
            exchange_offset_ms=1100,
            received_offset_ms=1150,
            price=101,
            volume=2,
            ask_bid="ASK",
        ),
        make_trade_event(
            sequence=3,
            exchange_offset_ms=2100,
            received_offset_ms=2150,
            price=102,
            volume=3,
            ask_bid="BID",
        ),
    ]
    snapshot = TradeFeatureCalculator(large_trade_threshold=Decimal(2)).compute(
        events,
        market="KRW-BTC",
        as_of_utc=BASE_TIME + timedelta(seconds=3),
        current_mid=Decimal(101),
    )
    assert snapshot.values["aggressive_buy_volume"] == 4.0
    assert snapshot.values["aggressive_sell_volume"] == 2.0
    assert snapshot.values["signed_trade_volume"] == 2.0
    assert snapshot.values["trade_imbalance"] == pytest.approx(1 / 3)
    assert snapshot.values["large_trade_count"] == 2.0
    assert snapshot.values["large_trade_volume"] == 5.0
    assert snapshot.values["buy_run_length"] == 1.0
    assert snapshot.values["sell_run_length"] == 0.0
    assert snapshot.values["interarrival_mean"] == 1.0
    assert snapshot.values["short_term_vwap"] == pytest.approx(608 / 6)
    assert set(snapshot.values) <= {
        definition.name for definition in default_feature_registry().definitions
    }


def test_trade_features_reject_future_and_empty_windows() -> None:
    event = make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=150)
    calculator = TradeFeatureCalculator()
    with pytest.raises(LookaheadViolation):
        calculator.compute(
            [event],
            market="KRW-BTC",
            as_of_utc=event.received_at_utc - timedelta(microseconds=1),
        )
    with pytest.raises(ValueError, match="no causal"):
        calculator.compute([event], market="KRW-ETH", as_of_utc=BASE_TIME + timedelta(seconds=1))
    single = calculator.compute(
        [event], market="KRW-BTC", as_of_utc=BASE_TIME + timedelta(seconds=1)
    )
    assert "insufficient_interarrival_history" in single.quality_flags
    assert "mid_price_unavailable" in single.quality_flags
    with pytest.raises(ValueError):
        TradeFeatureCalculator(window_seconds=0)


def test_volatility_features_use_only_closed_available_bars() -> None:
    closes = [100, 101, 99, 102, 103, 104]
    bars = [make_trade_bar(index=index, close=close) for index, close in enumerate(closes)]
    as_of = BASE_TIME + timedelta(seconds=6)
    snapshot = VolatilityFeatureCalculator().compute(bars, market="KRW-BTC", as_of_utc=as_of)
    assert snapshot.values["realized_variance"] is not None
    assert snapshot.values["realized_volatility"] is not None
    assert snapshot.values["multi_horizon_return_5"] == pytest.approx(
        __import__("math").log(104 / 100)
    )
    assert snapshot.values["atr_baseline"] is not None
    assert snapshot.values["downside_volatility"] > 0  # type: ignore[operator]
    assert snapshot.quality_flags == ()
    assert set(snapshot.values) <= {
        definition.name for definition in default_feature_registry().definitions
    }


def test_volatility_features_reject_future_and_insufficient_inputs() -> None:
    bars = [make_trade_bar(index=index, close=100 + index) for index in range(3)]
    calculator = VolatilityFeatureCalculator()
    with pytest.raises(LookaheadViolation):
        calculator.compute(
            [*bars, make_trade_bar(index=3, close=103, available_delay_seconds=10)],
            market="KRW-BTC",
            as_of_utc=BASE_TIME + timedelta(seconds=4),
        )
    with pytest.raises(ValueError, match="insufficient"):
        calculator.compute(bars[:2], market="KRW-BTC", as_of_utc=BASE_TIME + timedelta(seconds=3))
    with pytest.raises(ValueError):
        VolatilityFeatureCalculator(ewma_lambda=1)


def test_feature_registry_is_unique_and_stably_hashed() -> None:
    first = default_feature_registry()
    second = default_feature_registry()
    assert first.manifest_hash == second.manifest_hash
    assert first.get("mid_price").family == "orderbook"
    assert len(first.definitions) >= 40
    with pytest.raises(KeyError, match="unknown feature"):
        first.get("not_registered")
    with pytest.raises(ValueError, match="already registered"):
        first.register(first.get("mid_price"))

    custom = FeatureRegistry()
    definition = FeatureDefinition(
        name="custom_feature",
        version="1",
        family="trade",
        unit="ratio",
        description="test definition",
    )
    custom.register(definition)
    assert custom.definitions == (definition,)


def test_feature_snapshot_contract_rejects_leakage_nonfinite_and_duplicate_flags() -> None:
    payload = {
        "feature_set": "test",
        "feature_version": "1",
        "market": "KRW-BTC",
        "event_time_utc": BASE_TIME,
        "available_at_utc": BASE_TIME,
        "computed_at_utc": BASE_TIME,
        "values": {"value": 1.0},
        "input_hash": "a" * 64,
    }
    snapshot = FeatureSnapshot.model_validate(payload)
    assert len(snapshot.snapshot_hash) == 64
    with pytest.raises(ValidationError, match="before"):
        FeatureSnapshot.model_validate(
            {**payload, "computed_at_utc": BASE_TIME - timedelta(seconds=1)}
        )
    with pytest.raises(ValidationError, match="finite"):
        FeatureSnapshot.model_validate({**payload, "values": {"value": float("nan")}})
    with pytest.raises(ValidationError, match="quality flags"):
        FeatureSnapshot.model_validate({**payload, "quality_flags": ("same", "same")})


def test_gap_bar_is_excluded_and_reported_by_volatility() -> None:
    bars = [make_trade_bar(index=index, close=100 + index) for index in range(3)]
    template = bars[0]
    gap = TradeBar.model_validate(
        {
            **template.model_dump(),
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": None,
            "quote_volume": None,
            "trade_count": None,
            "aggressive_buy_volume": None,
            "aggressive_sell_volume": None,
            "vwap": None,
            "first_trade_timestamp": None,
            "last_trade_timestamp": None,
            "is_complete": False,
            "data_gap": True,
        }
    )
    snapshot = VolatilityFeatureCalculator().compute(
        [*bars, gap],
        market="KRW-BTC",
        as_of_utc=BASE_TIME + timedelta(seconds=3),
    )
    assert "gaps_excluded" in snapshot.quality_flags

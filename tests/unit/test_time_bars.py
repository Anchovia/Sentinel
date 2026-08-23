from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from factories import BASE_TIME, make_trade_event
from quantforge.bars import TimeBarBuilder
from quantforge.domain import CoverageWindow, DataGap, DataGapReason, TradeBar


def _coverage(start: datetime = BASE_TIME, end: datetime | None = None) -> CoverageWindow:
    selected_end = end or BASE_TIME + timedelta(minutes=1)
    return CoverageWindow(
        market="KRW-BTC",
        start_utc=start,
        end_utc=selected_end,
        asserted_at_utc=selected_end,
    )


def _gap() -> DataGap:
    return DataGap(
        market="KRW-BTC",
        start_utc=BASE_TIME + timedelta(seconds=1),
        end_utc=BASE_TIME + timedelta(seconds=2),
        known_at_utc=BASE_TIME + timedelta(seconds=2),
        reason=DataGapReason.CONNECTION_LOST,
        details="one second disconnect",
    )


def test_one_second_bars_distinguish_trade_no_trade_and_gap() -> None:
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
            exchange_offset_ms=600,
            received_offset_ms=650,
            price=101,
            volume=2,
            ask_bid="ASK",
        ),
    ]
    bars = TimeBarBuilder((1,)).build(
        markets=["KRW-BTC"],
        start_utc=BASE_TIME,
        end_utc=BASE_TIME + timedelta(minutes=1),
        events=events,
        coverage=[_coverage()],
        gaps=[_gap()],
    )
    assert len(bars) == 60
    traded, gap, no_trade = bars[:3]
    assert (traded.open, traded.high, traded.low, traded.close) == (
        Decimal(100),
        Decimal(101),
        Decimal(100),
        Decimal(101),
    )
    assert traded.volume == Decimal(3)
    assert traded.quote_volume == Decimal(302)
    assert traded.trade_count == 2
    assert traded.aggressive_buy_volume == Decimal(1)
    assert traded.aggressive_sell_volume == Decimal(2)
    assert traded.vwap == Decimal(302) / Decimal(3)
    assert traded.is_complete and not traded.no_trade and not traded.data_gap

    assert gap.data_gap and not gap.is_complete
    assert gap.volume is None and gap.trade_count is None
    assert gap.quality_flags == ("explicit_data_gap",)

    assert no_trade.no_trade and no_trade.is_complete
    assert no_trade.volume == 0 and no_trade.trade_count == 0
    assert no_trade.close is None


def test_same_inputs_produce_same_bar_identity_and_hash() -> None:
    event = make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=150)
    builder = TimeBarBuilder((60,))
    kwargs = {
        "markets": ["KRW-BTC"],
        "start_utc": BASE_TIME,
        "end_utc": BASE_TIME + timedelta(minutes=1),
        "events": [event],
        "coverage": [_coverage()],
    }
    first = builder.build(**kwargs)[0]  # type: ignore[arg-type]
    second = builder.build(**kwargs)[0]  # type: ignore[arg-type]
    assert first == second
    assert first.bar_id == second.bar_id
    assert first.source_hash == second.source_hash


def test_missing_positive_coverage_becomes_gap_not_zero_volume() -> None:
    bars = TimeBarBuilder((1,)).build(
        markets=["KRW-BTC"],
        start_utc=BASE_TIME,
        end_utc=BASE_TIME + timedelta(minutes=1),
        events=[make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=150)],
        coverage=[],
    )
    assert all(bar.data_gap for bar in bars)
    assert all(bar.volume is None for bar in bars)
    assert bars[0].quality_flags == ("coverage_not_asserted",)


def test_all_phase2_intervals_are_materialized() -> None:
    bars = TimeBarBuilder().build(
        markets=["KRW-BTC"],
        start_utc=BASE_TIME,
        end_utc=BASE_TIME + timedelta(minutes=1),
        events=[],
        coverage=[_coverage()],
    )
    assert len(bars) == 60 + 12 + 4 + 1
    assert {bar.interval_seconds for bar in bars} == {1, 5, 15, 60}
    assert all(bar.no_trade for bar in bars)


@pytest.mark.parametrize(
    "intervals",
    [(), (1, 1), (2,)],
)
def test_invalid_intervals_are_rejected(intervals: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        TimeBarBuilder(intervals)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("markets", "start", "end"),
    [
        ([], BASE_TIME, BASE_TIME + timedelta(minutes=1)),
        (["KRW-BTC"], datetime(2026, 1, 1), BASE_TIME + timedelta(minutes=1)),
        (["KRW-BTC"], BASE_TIME, BASE_TIME),
        (["KRW-BTC"], BASE_TIME + timedelta(seconds=1), BASE_TIME + timedelta(minutes=1)),
    ],
)
def test_invalid_build_range_is_rejected(
    markets: list[str], start: datetime, end: datetime
) -> None:
    with pytest.raises(ValueError):
        TimeBarBuilder((1,)).build(
            markets=markets,
            start_utc=start,
            end_utc=end,
            events=[],
            coverage=[],
        )


def test_bar_contract_rejects_fabricated_gap_and_inconsistent_traded_values() -> None:
    valid = TimeBarBuilder((60,)).build(
        markets=["KRW-BTC"],
        start_utc=BASE_TIME,
        end_utc=BASE_TIME + timedelta(minutes=1),
        events=[make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=150)],
        coverage=[_coverage()],
    )[0]
    with pytest.raises(ValidationError, match="data-gap"):
        TradeBar.model_validate(
            {
                **valid.model_dump(),
                "data_gap": True,
                "is_complete": False,
            }
        )
    with pytest.raises(ValidationError, match="OHLC"):
        TradeBar.model_validate({**valid.model_dump(), "high": Decimal(1)})

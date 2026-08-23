from datetime import timedelta
from pathlib import Path

import pytest

from factories import BASE_TIME, make_orderbook_event, make_ticker_event, make_trade_event
from quantforge.runtime import (
    RealtimeDecisionState,
    RealtimePaperPipeline,
    read_realtime_pipeline_snapshot,
    write_realtime_pipeline_snapshot,
)


def _ready_events():  # type: ignore[no-untyped-def]
    return (
        make_ticker_event(sequence=1, received_offset_ms=100),
        make_orderbook_event(sequence=2, received_offset_ms=110),
        make_trade_event(sequence=3, exchange_offset_ms=115, received_offset_ms=120),
        make_trade_event(
            sequence=4,
            exchange_offset_ms=125,
            received_offset_ms=130,
            price=101,
            ask_bid="ASK",
        ),
    )


def test_incremental_pipeline_builds_causal_multi_window_features_and_holds() -> None:
    pipeline = RealtimePaperPipeline(("KRW-BTC",))

    frames = [pipeline.process(event) for event in _ready_events()]
    latest = frames[-1]
    assert latest is not None
    assert latest.ready_for_inference is True
    assert latest.hold_reasons == ()
    assert latest.mid_price == 100
    assert latest.microprice == 100
    assert latest.spread_bps == pytest.approx(200)
    assert latest.trade_count_1s == 2
    assert latest.trade_count_5s == 2
    assert latest.trade_count_15s == 2
    assert latest.trade_return_1s_bps == pytest.approx(100)
    assert latest.trade_imbalance_1s is not None
    snapshot = pipeline.snapshot(generated_at_utc=BASE_TIME + timedelta(seconds=1))
    assert snapshot.processed_events == 4
    assert snapshot.inference_ready_frames == 1
    assert snapshot.decision_state is RealtimeDecisionState.HOLD
    assert snapshot.decision_reason == "NO_APPROVED_REALTIME_MODEL"
    assert snapshot.approved_model_available is False
    assert snapshot.strategy_order_capability is False
    assert snapshot.order_submission_available is False
    assert snapshot.live_submission_allowed is False


def test_pipeline_prunes_windows_and_fails_closed_on_stale_inputs() -> None:
    pipeline = RealtimePaperPipeline(("KRW-BTC",), stale_after_ms=500)
    for event in _ready_events():
        pipeline.process(event)

    stale = pipeline.process(make_orderbook_event(sequence=5, received_offset_ms=2_000))

    assert stale is not None
    assert stale.ready_for_inference is False
    assert stale.trade_count_1s == 0
    assert stale.trade_count_5s == 2
    assert "TRADE_STALE" in stale.hold_reasons
    assert "TICKER_STALE" in stale.quality_warnings


def test_realized_volatility_updates_and_prunes_incrementally() -> None:
    pipeline = RealtimePaperPipeline(("KRW-BTC",), stale_after_ms=2_000)
    events = (
        make_orderbook_event(sequence=1, received_offset_ms=0),
        make_trade_event(sequence=2, exchange_offset_ms=0, received_offset_ms=0, price=100),
        make_trade_event(sequence=3, exchange_offset_ms=100, received_offset_ms=100, price=101),
        make_trade_event(sequence=4, exchange_offset_ms=200, received_offset_ms=200, price=103),
    )
    frames = [pipeline.process(event) for event in events]

    latest = frames[-1]
    assert latest is not None
    expected = ((0.01**2 + (2 / 101) ** 2) ** 0.5) * 10_000
    assert latest.realized_volatility_15s_bps == pytest.approx(expected)

    pruned = pipeline.process(make_orderbook_event(sequence=5, received_offset_ms=1_150))
    assert pruned is not None
    assert pruned.trade_count_1s == 1
    assert pruned.realized_volatility_15s_bps == pytest.approx(expected)

    fully_pruned = pipeline.process(make_orderbook_event(sequence=6, received_offset_ms=15_150))
    assert fully_pruned is not None
    assert fully_pruned.trade_count_15s == 1
    assert fully_pruned.realized_volatility_15s_bps is None


def test_ticker_is_enrichment_not_a_required_decision_source() -> None:
    pipeline = RealtimePaperPipeline(("KRW-BTC",))
    events = (
        make_orderbook_event(sequence=1, received_offset_ms=100),
        make_trade_event(sequence=2, exchange_offset_ms=105, received_offset_ms=110),
        make_trade_event(sequence=3, exchange_offset_ms=115, received_offset_ms=120),
    )

    frames = [pipeline.process(event) for event in events]

    latest = frames[-1]
    assert latest is not None
    assert latest.ready_for_inference is True
    assert latest.hold_reasons == ()
    assert latest.quality_warnings == ("TICKER_MISSING",)


def test_pipeline_ignores_marked_duplicates_and_rejects_bad_ordering() -> None:
    pipeline = RealtimePaperPipeline(("KRW-BTC",))
    first = make_ticker_event(sequence=1, received_offset_ms=100)
    duplicate = first.model_copy(update={"is_duplicate": True})
    assert pipeline.process(duplicate) is None
    pipeline.process(first)

    with pytest.raises(ValueError, match="nondecreasing"):
        pipeline.process(make_orderbook_event(sequence=2, received_offset_ms=99))
    with pytest.raises(ValueError, match="outside"):
        pipeline.process(make_orderbook_event(sequence=3, received_offset_ms=101, market="KRW-ETH"))

    snapshot = pipeline.snapshot(generated_at_utc=BASE_TIME + timedelta(seconds=1))
    assert snapshot.duplicate_events == 1
    assert snapshot.processed_events == 1


def test_pipeline_records_latency_budget_breaches_deterministically() -> None:
    ticks = iter((0, 1_000_000, 2_000_000, 9_000_000))
    pipeline = RealtimePaperPipeline(
        ("KRW-BTC",), processing_budget_ms=5, clock_ns=lambda: next(ticks)
    )

    pipeline.process(make_ticker_event(sequence=1, received_offset_ms=100))
    pipeline.process(make_orderbook_event(sequence=2, received_offset_ms=110))
    snapshot = pipeline.snapshot(generated_at_utc=BASE_TIME + timedelta(seconds=1))

    assert snapshot.processing_latency_p50_ms == 1
    assert snapshot.processing_latency_p99_ms == 7
    assert snapshot.processing_latency_max_ms == 7
    assert snapshot.processing_budget_breaches == 1


def test_realtime_snapshot_is_atomic_secret_free_round_trip(tmp_path: Path) -> None:
    pipeline = RealtimePaperPipeline(("KRW-BTC",))
    for event in _ready_events():
        pipeline.process(event)
    snapshot = pipeline.snapshot(generated_at_utc=BASE_TIME + timedelta(seconds=1))

    path = write_realtime_pipeline_snapshot(snapshot, tmp_path)

    assert read_realtime_pipeline_snapshot(path) == snapshot
    text = path.read_text(encoding="utf-8").lower()
    assert "authorization" not in text
    assert "raw_payload" not in text
    assert "order_submission_available" in text
    assert list(path.parent.glob("*.tmp")) == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"markets": ()},
        {"markets": ("KRW-BTC", "KRW-BTC")},
        {"markets": ("KRW-BTC",), "stale_after_ms": 0},
        {"markets": ("KRW-BTC",), "processing_budget_ms": 0},
        {"markets": ("KRW-BTC",), "latency_window_size": 0},
    ],
)
def test_pipeline_rejects_invalid_bounds(kwargs: object) -> None:
    with pytest.raises(ValueError):
        RealtimePaperPipeline(**kwargs)  # type: ignore[arg-type]

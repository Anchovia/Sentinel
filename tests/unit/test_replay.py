from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import orjson
import pytest

from factories import BASE_TIME, make_trade_event
from quantforge.domain import DataGap, DataGapReason, EventEnvelope
from quantforge.replay import (
    ReplayConfig,
    ReplayEngine,
    VirtualClock,
    load_checkpoint,
    save_checkpoint,
)

EXPECTED = Path(__file__).parents[1] / "fixtures" / "replay" / "golden_expected.json"


def _golden_items():  # type: ignore[no-untyped-def]
    first = make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=150, price=100)
    second = make_trade_event(
        sequence=2, exchange_offset_ms=600, received_offset_ms=650, price=101, ask_bid="ASK"
    )
    duplicate = second.model_copy(
        update={
            "event_id": UUID(int=3),
            "received_at_utc": BASE_TIME + timedelta(milliseconds=700),
            "received_monotonic_ns": 3,
            "local_sequence": 3,
        }
    )
    out_of_order = make_trade_event(
        sequence=4,
        exchange_offset_ms=400,
        received_offset_ms=800,
        price=99,
        connection=2,
    )
    gap = DataGap(
        market="KRW-BTC",
        start_utc=BASE_TIME + timedelta(seconds=1),
        end_utc=BASE_TIME + timedelta(seconds=2),
        known_at_utc=BASE_TIME + timedelta(milliseconds=2100),
        reason=DataGapReason.CONNECTION_LOST,
        details="golden reconnect boundary",
    )
    after_gap = make_trade_event(
        sequence=5,
        exchange_offset_ms=2200,
        received_offset_ms=2250,
        price=102,
        connection=2,
    )
    return [after_gap, gap, out_of_order, duplicate, second, first]


def _handler(item: EventEnvelope | DataGap, clock: VirtualClock) -> str:
    assert clock.now == (item.known_at_utc if isinstance(item, DataGap) else item.received_at_utc)
    if isinstance(item, DataGap):
        return f"gap|{item.fingerprint()}"
    return f"event|{item.raw_payload_hash}|{','.join(item.quality_flags)}"


def test_golden_replay_is_identical_for_same_inputs() -> None:
    engine = ReplayEngine()
    first = engine.run(_golden_items(), _handler)
    second = engine.run(list(reversed(_golden_items())), _handler)
    expected = orjson.loads(EXPECTED.read_bytes())
    for name, value in expected.items():
        assert getattr(first, name) == value
    assert first.dataset_hash == second.dataset_hash
    assert first.output_hash == second.output_hash
    assert first.config_hash == second.config_hash
    assert first.checkpoint.cursor == 6


def test_replay_checkpoint_resume_matches_full_hash_chain(tmp_path: Path) -> None:
    items = _golden_items()
    engine = ReplayEngine()
    full = engine.run(items, _handler)
    partial = engine.run(items, _handler, stop_after=3)
    assert partial.checkpoint.cursor == 3

    path = tmp_path / "checkpoint.json"
    save_checkpoint(partial.checkpoint, path)
    restored = load_checkpoint(path)
    resumed = engine.run(items, _handler, checkpoint=restored)
    assert resumed.output_hash == full.output_hash
    assert resumed.checkpoint.cursor == len(items)
    assert resumed.delivered_events == full.delivered_events


def test_checkpoint_corruption_and_mismatch_fail_closed(tmp_path: Path) -> None:
    items = _golden_items()
    checkpoint = ReplayEngine().run(items, _handler, stop_after=1).checkpoint
    path = tmp_path / "checkpoint.json"
    save_checkpoint(checkpoint, path)
    envelope = orjson.loads(path.read_bytes())
    envelope["sha256"] = "0" * 64
    path.write_bytes(orjson.dumps(envelope))
    with pytest.raises(ValueError, match="checksum"):
        load_checkpoint(path)

    with pytest.raises(ValueError, match="dataset or configuration"):
        ReplayEngine(ReplayConfig(random_seed=9)).run(items, _handler, checkpoint=checkpoint)
    too_far = checkpoint.model_copy(update={"cursor": len(items) + 1})
    with pytest.raises(ValueError, match="cursor"):
        ReplayEngine().run(items, _handler, checkpoint=too_far)


def test_malformed_checkpoint_envelope_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        load_checkpoint(path)


def test_replay_can_deliver_duplicates_and_skip_annotation() -> None:
    delivered: list[EventEnvelope | DataGap] = []

    def collect(item: EventEnvelope | DataGap, clock: VirtualClock) -> None:
        del clock
        delivered.append(item)

    result = ReplayEngine(ReplayConfig(drop_duplicates=False, annotate_out_of_order=False)).run(
        _golden_items(), collect
    )
    assert result.delivered_events == 5
    assert result.skipped_duplicates == 0
    assert result.out_of_order_events == 1
    assert not any(
        "out_of_order" in item.quality_flags
        for item in delivered
        if isinstance(item, EventEnvelope)
    )


def test_replay_validates_empty_input_and_bounds() -> None:
    engine = ReplayEngine()
    with pytest.raises(ValueError, match="at least one"):
        engine.run([], _handler)
    with pytest.raises(ValueError, match="stop_after"):
        engine.run(_golden_items(), _handler, stop_after=0)


def test_virtual_clock_only_moves_forward_in_utc() -> None:
    clock = VirtualClock(BASE_TIME)
    assert clock.advance_by(timedelta(seconds=1)) == BASE_TIME + timedelta(seconds=1)
    assert clock.advance_to(BASE_TIME + timedelta(seconds=2)) == BASE_TIME + timedelta(seconds=2)
    with pytest.raises(ValueError, match="backwards"):
        clock.advance_to(BASE_TIME)
    with pytest.raises(ValueError, match="negative"):
        clock.advance_by(timedelta(seconds=-1))
    with pytest.raises(ValueError, match="UTC-aware"):
        VirtualClock(datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="UTC-aware"):
        VirtualClock(BASE_TIME.astimezone(timezone(timedelta(hours=9))))

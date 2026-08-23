from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from quantforge.exchange.upbit.mapper import map_public_message
from quantforge.market_data import EventDeduplicator

FIXTURE = Path(__file__).parents[1] / "fixtures" / "upbit" / "trade.default.json"


def _event(sequence: int):  # type: ignore[no-untyped-def]
    return map_public_message(
        FIXTURE.read_bytes(),
        received_at_utc=datetime(2024, 10, 31, 1, 7, 43, tzinfo=UTC),
        received_monotonic_ns=sequence,
        connection_id=uuid4(),
        subscription_id="test",
        local_sequence=sequence,
    )


def test_duplicate_is_marked_without_mutating_first_event() -> None:
    deduplicator = EventDeduplicator(max_entries=2)
    first = deduplicator.mark(_event(1))
    second = deduplicator.mark(_event(2))
    assert first.is_duplicate is False
    assert second.is_duplicate is True
    assert second.quality_flags == ("duplicate_raw_payload",)
    assert len(deduplicator) == 1


def test_oldest_digest_is_evicted() -> None:
    deduplicator = EventDeduplicator(max_entries=1)
    first = _event(1)
    alternate = first.model_copy(update={"raw_payload_hash": "a" * 64})
    deduplicator.mark(first)
    deduplicator.mark(alternate)
    replay = deduplicator.mark(first)
    assert replay.is_duplicate is False


def test_invalid_capacity_is_rejected() -> None:
    try:
        EventDeduplicator(max_entries=0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected invalid capacity to fail")

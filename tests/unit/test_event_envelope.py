from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from quantforge.domain import EventEnvelope
from quantforge.exchange.upbit.mapper import map_public_message

FIXTURES = Path(__file__).parents[1] / "fixtures" / "upbit"


def _map_fixture(name: str, *, received_offset_ms: int = 10) -> EventEnvelope:
    raw = (FIXTURES / name).read_bytes()
    timestamp_ms = __import__("json").loads(raw)["timestamp"]
    exchange_time = datetime.fromtimestamp(timestamp_ms // 1000, tz=UTC).replace(
        microsecond=(timestamp_ms % 1000) * 1000
    )
    return map_public_message(
        raw,
        received_at_utc=exchange_time + timedelta(milliseconds=received_offset_ms),
        received_monotonic_ns=42,
        connection_id=uuid4(),
        subscription_id="fixture-subscription",
        local_sequence=1,
    )


def test_mapper_preserves_raw_lineage_and_latency() -> None:
    raw = (FIXTURES / "trade.default.json").read_bytes()
    event = _map_fixture("trade.default.json")
    assert event.event_type == "trade"
    assert event.is_snapshot is True
    assert event.is_realtime is False
    assert event.raw_payload_hash == sha256(raw).hexdigest()
    assert event.raw_payload_text == raw.decode("utf-8")
    assert event.ingress_latency_us == 10_000
    assert event.quality_flags == ()


def test_mapper_marks_stale_and_future_clock_skew() -> None:
    stale = _map_fixture("ticker.default.json", received_offset_ms=5_001)
    future = _map_fixture("orderbook.synthetic.json", received_offset_ms=-1_001)
    assert stale.quality_flags == ("stale_at_ingress",)
    assert future.quality_flags == ("exchange_clock_ahead",)


def test_envelope_requires_utc_and_exactly_one_stream_kind() -> None:
    event = _map_fixture("trade.default.json")
    with pytest.raises(ValidationError, match="timezone-aware"):
        EventEnvelope.model_validate(
            {
                **event.model_dump(),
                "received_at_utc": event.received_at_utc.replace(tzinfo=None),
            }
        )
    with pytest.raises(ValidationError, match="exactly one"):
        EventEnvelope.model_validate(
            {**event.model_dump(), "is_snapshot": True, "is_realtime": True}
        )


def test_envelope_rejects_duplicate_quality_flags() -> None:
    event = _map_fixture("trade.default.json")
    with pytest.raises(ValidationError, match="quality flags"):
        EventEnvelope.model_validate({**event.model_dump(), "quality_flags": ("same", "same")})

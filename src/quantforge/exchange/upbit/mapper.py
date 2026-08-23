"""Upbit wire-to-domain mapping with raw-byte lineage."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from quantforge.domain import EventEnvelope
from quantforge.exchange.upbit.schemas import StreamType, parse_public_message

NORMALIZATION_VERSION = "upbit-public-v1"
STALE_INGRESS_US = 5_000_000
FUTURE_CLOCK_SKEW_US = -1_000_000


def _timestamp_ms_to_utc(value: int) -> datetime:
    seconds, milliseconds = divmod(value, 1000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=milliseconds * 1000)


def map_public_message(
    raw: str | bytes,
    *,
    received_at_utc: datetime,
    received_monotonic_ns: int,
    connection_id: UUID,
    subscription_id: str,
    local_sequence: int,
) -> EventEnvelope:
    """Validate an untrusted message and wrap it in a versioned immutable envelope."""

    message, payload = parse_public_message(raw)
    raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    raw_text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    exchange_timestamp = _timestamp_ms_to_utc(message.timestamp)
    stream_type = message.stream_type
    preliminary_latency = received_at_utc - exchange_timestamp
    latency_us = (
        preliminary_latency.days * 86_400_000_000
        + preliminary_latency.seconds * 1_000_000
        + preliminary_latency.microseconds
    )
    quality_flags: list[str] = []
    if latency_us > STALE_INGRESS_US:
        quality_flags.append("stale_at_ingress")
    if latency_us < FUTURE_CLOCK_SKEW_US:
        quality_flags.append("exchange_clock_ahead")

    return EventEnvelope(
        event_id=uuid4(),
        event_type=message.type,
        market=message.code,
        exchange_timestamp=exchange_timestamp,
        received_at_utc=received_at_utc,
        received_monotonic_ns=received_monotonic_ns,
        connection_id=connection_id,
        subscription_id=subscription_id,
        local_sequence=local_sequence,
        raw_payload=payload,
        raw_payload_text=raw_text,
        raw_payload_hash=sha256(raw_bytes).hexdigest(),
        normalization_version=NORMALIZATION_VERSION,
        is_snapshot=stream_type is StreamType.SNAPSHOT,
        is_realtime=stream_type is StreamType.REALTIME,
        quality_flags=tuple(quality_flags),
    )

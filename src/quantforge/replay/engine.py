"""Availability-ordered deterministic replay with resumable hash-chain checkpoints."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.domain import DataGap, EventEnvelope
from quantforge.replay.clock import VirtualClock

type ReplayItem = EventEnvelope | DataGap
type ReplayHandler = Callable[[ReplayItem, VirtualClock], str | bytes | None]

INITIAL_CHAIN_HASH = "0" * 64


class ReplayConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    drop_duplicates: bool = True
    annotate_out_of_order: bool = True
    random_seed: int = 0

    @property
    def digest(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()


class ReplayCheckpoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    cursor: Annotated[int, Field(ge=0)]
    virtual_time_utc: datetime
    chain_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    delivered_events: Annotated[int, Field(ge=0)]
    delivered_gaps: Annotated[int, Field(ge=0)]
    skipped_duplicates: Annotated[int, Field(ge=0)]
    out_of_order_events: Annotated[int, Field(ge=0)]
    reconnect_boundaries: Annotated[int, Field(ge=0)]

    @field_validator("virtual_time_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("checkpoint virtual time must be UTC-aware")
        return value


class ReplayResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_hash: str
    config_hash: str
    output_hash: str
    total_inputs: int
    delivered_events: int
    delivered_gaps: int
    skipped_duplicates: int
    out_of_order_events: int
    reconnect_boundaries: int
    started_at_utc: datetime
    ended_at_utc: datetime
    checkpoint: ReplayCheckpoint


def _event_fingerprint(event: EventEnvelope) -> str:
    payload = "|".join(
        (
            "event",
            str(event.event_id),
            event.raw_payload_hash,
            event.event_type,
            event.market,
            event.exchange_timestamp.isoformat(),
            event.received_at_utc.isoformat(),
            str(event.received_monotonic_ns),
            str(event.connection_id),
            str(event.local_sequence),
            str(event.is_duplicate),
        )
    )
    return sha256(payload.encode()).hexdigest()


def replay_item_fingerprint(item: ReplayItem) -> str:
    return item.fingerprint() if isinstance(item, DataGap) else _event_fingerprint(item)


def _availability_time(item: ReplayItem) -> datetime:
    return item.availability_time if isinstance(item, DataGap) else item.received_at_utc


def _sort_key(item: ReplayItem) -> tuple[datetime, int, int, str, int, str]:
    if isinstance(item, DataGap):
        return (
            item.known_at_utc,
            1,
            0,
            "",
            0,
            item.fingerprint(),
        )
    return (
        item.received_at_utc,
        0,
        item.received_monotonic_ns,
        str(item.connection_id),
        item.local_sequence,
        str(item.event_id),
    )


def _chain(previous: str, item_fingerprint: str, output: str | bytes | None) -> str:
    if output is None:
        output_bytes = b""
    elif isinstance(output, bytes):
        output_bytes = output
    else:
        output_bytes = output.encode()
    digest = sha256()
    digest.update(previous.encode())
    digest.update(item_fingerprint.encode())
    digest.update(output_bytes)
    return digest.hexdigest()


class ReplayEngine:
    def __init__(self, config: ReplayConfig | None = None) -> None:
        self.config = config or ReplayConfig()

    def run(
        self,
        items: Sequence[ReplayItem],
        handler: ReplayHandler,
        *,
        checkpoint: ReplayCheckpoint | None = None,
        stop_after: int | None = None,
    ) -> ReplayResult:
        if not items:
            raise ValueError("replay requires at least one input")
        if stop_after is not None and stop_after < 1:
            raise ValueError("stop_after must be positive")
        ordered = sorted(items, key=_sort_key)
        dataset_hash = sha256(
            "\n".join(replay_item_fingerprint(item) for item in ordered).encode()
        ).hexdigest()
        config_hash = self.config.digest
        cursor = 0
        chain_hash = INITIAL_CHAIN_HASH
        delivered_events = 0
        delivered_gaps = 0
        skipped_duplicates = 0
        out_of_order_events = 0
        reconnect_boundaries = 0
        start_time = _availability_time(ordered[0])

        if checkpoint is not None:
            if checkpoint.dataset_hash != dataset_hash or checkpoint.config_hash != config_hash:
                raise ValueError("checkpoint dataset or configuration hash does not match")
            if checkpoint.cursor > len(ordered):
                raise ValueError("checkpoint cursor exceeds replay input")
            cursor = checkpoint.cursor
            chain_hash = checkpoint.chain_hash
            delivered_events = checkpoint.delivered_events
            delivered_gaps = checkpoint.delivered_gaps
            skipped_duplicates = checkpoint.skipped_duplicates
            out_of_order_events = checkpoint.out_of_order_events
            reconnect_boundaries = checkpoint.reconnect_boundaries
            start_time = checkpoint.virtual_time_utc

        clock = VirtualClock(start_time)
        seen_hashes, last_exchange, previous_connection = self._rebuild_state(ordered[:cursor])
        for processed_this_run, item in enumerate(ordered[cursor:]):
            if stop_after is not None and processed_this_run >= stop_after:
                break
            clock.advance_to(_availability_time(item))
            fingerprint = replay_item_fingerprint(item)
            delivered: ReplayItem = item
            output: str | bytes | None

            if isinstance(item, DataGap):
                delivered_gaps += 1
                output = handler(item, clock)
            else:
                duplicate = item.is_duplicate or item.raw_payload_hash in seen_hashes
                seen_hashes.add(item.raw_payload_hash)
                if duplicate and self.config.drop_duplicates:
                    skipped_duplicates += 1
                    output = b"SKIP_DUPLICATE"
                else:
                    key = (item.market, item.event_type)
                    prior_exchange_time = last_exchange.get(key)
                    if (
                        prior_exchange_time is not None
                        and item.exchange_timestamp < prior_exchange_time
                    ):
                        out_of_order_events += 1
                        if (
                            self.config.annotate_out_of_order
                            and "out_of_order" not in item.quality_flags
                        ):
                            delivered = item.model_copy(
                                update={"quality_flags": (*item.quality_flags, "out_of_order")}
                            )
                    last_exchange[key] = max(
                        item.exchange_timestamp,
                        prior_exchange_time or item.exchange_timestamp,
                    )
                    if (
                        previous_connection is not None
                        and item.connection_id != previous_connection
                    ):
                        reconnect_boundaries += 1
                    previous_connection = item.connection_id
                    delivered_events += 1
                    output = handler(delivered, clock)

            chain_hash = _chain(chain_hash, fingerprint, output)
            cursor += 1

        replay_checkpoint = ReplayCheckpoint(
            dataset_hash=dataset_hash,
            config_hash=config_hash,
            cursor=cursor,
            virtual_time_utc=clock.now,
            chain_hash=chain_hash,
            delivered_events=delivered_events,
            delivered_gaps=delivered_gaps,
            skipped_duplicates=skipped_duplicates,
            out_of_order_events=out_of_order_events,
            reconnect_boundaries=reconnect_boundaries,
        )
        return ReplayResult(
            dataset_hash=dataset_hash,
            config_hash=config_hash,
            output_hash=chain_hash,
            total_inputs=len(ordered),
            delivered_events=delivered_events,
            delivered_gaps=delivered_gaps,
            skipped_duplicates=skipped_duplicates,
            out_of_order_events=out_of_order_events,
            reconnect_boundaries=reconnect_boundaries,
            started_at_utc=start_time,
            ended_at_utc=clock.now,
            checkpoint=replay_checkpoint,
        )

    @staticmethod
    def _rebuild_state(
        items: Sequence[ReplayItem],
    ) -> tuple[set[str], dict[tuple[str, str], datetime], UUID | None]:
        seen: set[str] = set()
        last_exchange: dict[tuple[str, str], datetime] = {}
        previous_connection: UUID | None = None
        for item in items:
            if isinstance(item, DataGap):
                continue
            duplicate = item.is_duplicate or item.raw_payload_hash in seen
            seen.add(item.raw_payload_hash)
            if duplicate:
                continue
            key = (item.market, item.event_type)
            previous = last_exchange.get(key)
            last_exchange[key] = max(item.exchange_timestamp, previous or item.exchange_timestamp)
            previous_connection = item.connection_id
        return seen, last_exchange, previous_connection

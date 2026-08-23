"""Atomic ZSTD Parquet writer for append-only raw exchange events."""

import os
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import orjson
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from quantforge.domain import EventEnvelope

RAW_EVENT_SCHEMA = pa.schema(
    [
        pa.field("event_id", pa.string(), nullable=False),
        pa.field("event_type", pa.string(), nullable=False),
        pa.field("schema_version", pa.int32(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("market", pa.string(), nullable=False),
        pa.field("exchange_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("received_at_utc", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("received_monotonic_ns", pa.int64(), nullable=False),
        pa.field("connection_id", pa.string(), nullable=False),
        pa.field("subscription_id", pa.string(), nullable=False),
        pa.field("local_sequence", pa.int64(), nullable=False),
        pa.field("raw_payload", pa.string(), nullable=False),
        pa.field("raw_payload_hash", pa.string(), nullable=False),
        pa.field("normalization_version", pa.string(), nullable=False),
        pa.field("is_snapshot", pa.bool_(), nullable=False),
        pa.field("is_realtime", pa.bool_(), nullable=False),
        pa.field("is_duplicate", pa.bool_(), nullable=False),
        pa.field("quality_flags", pa.list_(pa.string()), nullable=False),
        pa.field("ingress_latency_us", pa.int64(), nullable=False),
    ],
    metadata={
        b"quantforge_contract": b"raw-event-envelope",
        b"quantforge_schema_version": b"1",
    },
)


class RawFileManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_schema_version: int = 1
    event_schema_version: int = 1
    source: str
    event_type: str
    data_file: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    row_count: Annotated[int, Field(gt=0)]
    byte_size: Annotated[int, Field(gt=0)]
    min_exchange_timestamp: datetime
    max_exchange_timestamp: datetime
    created_at_utc: datetime
    compression: str = "zstd"


def _event_row(event: EventEnvelope) -> dict[str, object]:
    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "source": event.source,
        "market": event.market,
        "exchange_timestamp": event.exchange_timestamp,
        "received_at_utc": event.received_at_utc,
        "received_monotonic_ns": event.received_monotonic_ns,
        "connection_id": str(event.connection_id),
        "subscription_id": event.subscription_id,
        "local_sequence": event.local_sequence,
        "raw_payload": event.raw_payload_text,
        "raw_payload_hash": event.raw_payload_hash,
        "normalization_version": event.normalization_version,
        "is_snapshot": event.is_snapshot,
        "is_realtime": event.is_realtime,
        "is_duplicate": event.is_duplicate,
        "quality_flags": list(event.quality_flags),
        "ingress_latency_us": event.ingress_latency_us,
    }


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ParquetRawEventWriter:
    """Buffer events and atomically commit immutable partition files plus manifests."""

    def __init__(self, root: Path, *, max_rows: int = 10_000) -> None:
        if max_rows < 1:
            raise ValueError("max_rows must be positive")
        self.root = root
        self.max_rows = max_rows
        self._buffer: list[EventEnvelope] = []

    def append(self, event: EventEnvelope) -> list[RawFileManifest]:
        self._buffer.append(event)
        if len(self._buffer) >= self.max_rows:
            return self.flush()
        return []

    def flush(self) -> list[RawFileManifest]:
        if not self._buffer:
            return []
        selected, self._buffer = self._buffer, []
        groups: dict[tuple[str, str, str, str], list[EventEnvelope]] = defaultdict(list)
        for event in selected:
            groups[
                (
                    event.source,
                    event.event_type,
                    event.exchange_timestamp.date().isoformat(),
                    f"{event.exchange_timestamp.hour:02d}",
                )
            ].append(event)
        return [self._write_partition(key, events) for key, events in sorted(groups.items())]

    def close(self) -> list[RawFileManifest]:
        return self.flush()

    def _write_partition(
        self, key: tuple[str, str, str, str], events: list[EventEnvelope]
    ) -> RawFileManifest:
        source, event_type, date, hour = key
        partition = (
            self.root
            / f"source={source}"
            / f"event_type={event_type}"
            / f"date={date}"
            / f"hour={hour}"
        )
        partition.mkdir(parents=True, exist_ok=True)
        timestamp_token = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        data_path = partition / f"part-{timestamp_token}-{uuid4().hex}.parquet"
        temp_data = partition / f".{data_path.name}.{uuid4().hex}.tmp"
        manifest_path = data_path.with_suffix(".manifest.json")
        temp_manifest = partition / f".{manifest_path.name}.{uuid4().hex}.tmp"

        timestamps = [event.exchange_timestamp for event in events]
        try:
            table = pa.Table.from_pylist(
                [_event_row(event) for event in events], schema=RAW_EVENT_SCHEMA
            )
            pq.write_table(
                table,
                temp_data,
                compression="zstd",
                use_dictionary=True,
                write_statistics=True,
            )
            manifest = RawFileManifest(
                source=source,
                event_type=event_type,
                data_file=data_path.relative_to(self.root).as_posix(),
                sha256=_file_sha256(temp_data),
                row_count=len(events),
                byte_size=temp_data.stat().st_size,
                min_exchange_timestamp=min(timestamps),
                max_exchange_timestamp=max(timestamps),
                created_at_utc=datetime.now(UTC),
            )
            temp_manifest.write_bytes(
                orjson.dumps(
                    manifest.model_dump(mode="json"),
                    option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
                )
                + b"\n"
            )
            if data_path.exists() or manifest_path.exists():
                raise FileExistsError("append-only target unexpectedly already exists")
            os.replace(temp_data, data_path)
            os.replace(temp_manifest, manifest_path)
            return manifest
        finally:
            temp_data.unlink(missing_ok=True)
            temp_manifest.unlink(missing_ok=True)


def verify_manifest_checksum(root: Path, manifest: RawFileManifest) -> bool:
    data_path = (root / manifest.data_file).resolve()
    resolved_root = root.resolve()
    if resolved_root not in data_path.parents:
        raise ValueError("manifest data path escapes the raw-data root")
    return data_path.is_file() and _file_sha256(data_path) == manifest.sha256


def cleanup_orphan_temp_files(root: Path) -> int:
    """Remove only writer-owned hidden `.tmp` files under the explicit raw root."""

    if not root.exists():
        return 0
    resolved_root = root.resolve()
    removed = 0
    for path in root.rglob(".*.tmp"):
        resolved = path.resolve()
        if resolved_root not in resolved.parents or not resolved.is_file():
            continue
        resolved.unlink()
        removed += 1
    return removed

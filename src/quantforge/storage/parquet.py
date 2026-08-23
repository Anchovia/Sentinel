"""Atomic ZSTD Parquet writer for append-only raw exchange events."""

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, cast
from uuid import UUID, uuid4

import orjson
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from quantforge.domain import EventEnvelope, EventType
from quantforge.exchange.upbit.schemas import decode_json_object

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


class RawDataIntegrityError(ValueError):
    """A raw file, manifest, or row failed immutable lineage validation."""


@dataclass(frozen=True, slots=True)
class RawStorageSummary:
    """Manifest-backed retained raw-data totals without reading event payloads."""

    file_count: int = 0
    row_count: int = 0
    byte_size: int = 0


def summarize_raw_storage(root: Path) -> RawStorageSummary:
    """Count retained immutable files from validated manifests and file sizes."""

    if not root.exists():
        return RawStorageSummary()
    resolved_root = root.resolve()
    data_files: set[Path] = set()
    row_count = 0
    byte_size = 0
    for manifest_path in sorted(root.rglob("*.manifest.json")):
        try:
            manifest = RawFileManifest.model_validate_json(manifest_path.read_bytes())
        except ValueError as exc:
            raise RawDataIntegrityError(f"invalid raw manifest: {manifest_path}") from exc
        data_path = (root / manifest.data_file).resolve()
        if resolved_root not in data_path.parents:
            raise RawDataIntegrityError(f"unsafe raw manifest path: {manifest.data_file}")
        if data_path in data_files:
            raise RawDataIntegrityError(f"duplicate raw manifest target: {manifest.data_file}")
        if not data_path.is_file() or data_path.stat().st_size != manifest.byte_size:
            raise RawDataIntegrityError(f"raw file size mismatch: {manifest.data_file}")
        data_files.add(data_path)
        row_count += manifest.row_count
        byte_size += manifest.byte_size
    return RawStorageSummary(
        file_count=len(data_files),
        row_count=row_count,
        byte_size=byte_size,
    )


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


def read_raw_events(root: Path) -> list[EventEnvelope]:
    """Verify every manifest/checksum and reconstruct immutable envelopes."""

    events: list[EventEnvelope] = []
    for manifest_path in sorted(root.rglob("*.manifest.json")):
        try:
            manifest = RawFileManifest.model_validate_json(manifest_path.read_bytes())
        except ValueError as exc:
            raise RawDataIntegrityError(f"invalid raw manifest: {manifest_path}") from exc
        try:
            checksum_valid = verify_manifest_checksum(root, manifest)
        except ValueError as exc:
            raise RawDataIntegrityError(f"unsafe raw manifest path: {manifest.data_file}") from exc
        if not checksum_valid:
            raise RawDataIntegrityError(f"raw checksum mismatch: {manifest.data_file}")
        data_path = root / manifest.data_file
        parquet_file = pq.ParquetFile(data_path)
        metadata = parquet_file.schema_arrow.metadata or {}
        if (
            metadata.get(b"quantforge_schema_version")
            != str(manifest.event_schema_version).encode()
        ):
            raise RawDataIntegrityError(f"raw schema version mismatch: {manifest.data_file}")
        table = parquet_file.read()
        if table.num_rows != manifest.row_count:
            raise RawDataIntegrityError(f"raw row count mismatch: {manifest.data_file}")
        for row in table.to_pylist():
            raw_text = row["raw_payload"]
            if not isinstance(raw_text, str):
                raise RawDataIntegrityError("raw payload column must contain text")
            digest = sha256(raw_text.encode()).hexdigest()
            if digest != row["raw_payload_hash"]:
                raise RawDataIntegrityError("raw payload digest does not match its row")
            try:
                event = EventEnvelope(
                    event_id=UUID(row["event_id"]),
                    event_type=cast(EventType, row["event_type"]),
                    schema_version=row["schema_version"],
                    source=row["source"],
                    market=row["market"],
                    exchange_timestamp=row["exchange_timestamp"],
                    received_at_utc=row["received_at_utc"],
                    received_monotonic_ns=row["received_monotonic_ns"],
                    connection_id=UUID(row["connection_id"]),
                    subscription_id=row["subscription_id"],
                    local_sequence=row["local_sequence"],
                    raw_payload=decode_json_object(raw_text),
                    raw_payload_text=raw_text,
                    raw_payload_hash=digest,
                    normalization_version=row["normalization_version"],
                    is_snapshot=row["is_snapshot"],
                    is_realtime=row["is_realtime"],
                    is_duplicate=row["is_duplicate"],
                    quality_flags=tuple(row["quality_flags"]),
                )
            except (TypeError, ValueError) as exc:
                raise RawDataIntegrityError("raw row failed event-envelope validation") from exc
            if event.ingress_latency_us != row["ingress_latency_us"]:
                raise RawDataIntegrityError("raw row ingress latency does not match timestamps")
            events.append(event)
    return sorted(
        events,
        key=lambda event: (
            event.received_at_utc,
            event.received_monotonic_ns,
            str(event.connection_id),
            event.local_sequence,
            str(event.event_id),
        ),
    )

"""Atomic ZSTD Parquet writer for append-only raw exchange events."""

import os
import shutil
import struct
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from heapq import merge
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Annotated, BinaryIO, Literal, cast
from uuid import UUID, uuid4

import orjson
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

_RESEARCH_IDENTITY = struct.Struct(">QQ16sQ16s32s")
_RESEARCH_EVENT_ID_SIZE = 16
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class RawFileManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_schema_version: Literal[1, 2] = 1
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
    supersedes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_compaction_lineage(self) -> "RawFileManifest":
        if self.supersedes and self.manifest_schema_version != 2:
            raise ValueError("compaction lineage requires manifest schema version 2")
        if self.data_file in self.supersedes or len(set(self.supersedes)) != len(self.supersedes):
            raise ValueError("compaction lineage must contain unique prior data files")
        return self


class RawDataIntegrityError(ValueError):
    """A raw file, manifest, or row failed immutable lineage validation."""


class RawResearchInventoryTimeout(TimeoutError):
    """The bounded offline inventory scan exceeded its explicit wall-time budget."""


class RawEventReadLimitError(RuntimeError):
    """A bounded raw-event read exceeded its declared event-count limit."""


class RawEventReadTimeout(TimeoutError):
    """A bounded raw-event read exceeded its declared wall-time limit."""


@dataclass(frozen=True, slots=True)
class RawResearchInventoryProgress:
    """Coarse progress evidence for a potentially large offline fingerprint scan."""

    phase: Literal["scan", "event-id-check", "dataset-hash"]
    completed_units: int
    total_units: int
    selected_event_count: int


@dataclass(frozen=True, slots=True)
class RawStorageSummary:
    """Manifest-backed retained raw-data totals without reading event payloads."""

    file_count: int = 0
    row_count: int = 0
    byte_size: int = 0


@dataclass(frozen=True, slots=True)
class RawStoragePolicy:
    """Bounded local-paper retention and low-space fail-closed policy."""

    retention_days: int = 30
    max_bytes: int = 50 * 1024**3
    min_free_bytes: int = 1024**3
    maintenance_interval_seconds: float = 900.0
    compaction_min_files: int = 4
    compaction_target_rows: int = 250_000

    def __post_init__(self) -> None:
        if (
            min(
                self.retention_days,
                self.max_bytes,
                self.min_free_bytes,
                self.compaction_min_files,
                self.compaction_target_rows,
            )
            < 1
            or self.maintenance_interval_seconds <= 0
        ):
            raise ValueError("raw storage lifecycle bounds must be positive")


@dataclass(frozen=True, slots=True)
class RawStorageMaintenance:
    """One maintenance pass with manifest-backed post-operation totals."""

    summary: RawStorageSummary
    compacted_source_files: int = 0
    compacted_output_files: int = 0
    retention_deleted_files: int = 0
    capacity_deleted_files: int = 0
    reclaimed_bytes: int = 0
    disk_free_bytes: int = 0


class RawStorageCapacityError(RuntimeError):
    """Raised when the explicit paper-data filesystem crosses its safety floor."""


class RawEventMarketInventory(BaseModel):
    """Content-addressed research availability for one public market."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    trade_events: Annotated[int, Field(ge=0)] = 0
    orderbook_events: Annotated[int, Field(ge=0)] = 0
    first_received_at_utc: datetime
    last_received_at_utc: datetime

    @model_validator(mode="after")
    def validate_interval(self) -> "RawEventMarketInventory":
        if self.last_received_at_utc < self.first_received_at_utc:
            raise ValueError("raw market inventory interval is reversed")
        return self

    @property
    def observed_span_seconds(self) -> float:
        return (self.last_received_at_utc - self.first_received_at_utc).total_seconds()


class RawEventResearchInventory(BaseModel):
    """Verified row-level identity for a bounded public research selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["raw-event-research-inventory-1"] = "raw-event-research-inventory-1"
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_set_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    maximum_exchange_timestamp_utc: datetime | None = None
    maximum_received_at_utc: datetime | None = None
    exclude_marked_duplicates: bool = False
    exclude_quality_flagged_events: bool = False
    selected_file_count: Annotated[int, Field(ge=0)]
    selected_event_count: Annotated[int, Field(ge=0)]
    markets: tuple[RawEventMarketInventory, ...]

    @field_validator("maximum_exchange_timestamp_utc", "maximum_received_at_utc")
    @classmethod
    def require_utc_cutoff(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError("raw research inventory cutoffs must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_market_order(self) -> "RawEventResearchInventory":
        names = tuple(item.market for item in self.markets)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("raw research markets must be sorted and unique")
        if self.selected_event_count != sum(
            item.trade_events + item.orderbook_events for item in self.markets
        ):
            raise ValueError("raw research inventory counts do not reconcile")
        return self


@dataclass(frozen=True, slots=True)
class _ManifestRecord:
    path: Path
    manifest: RawFileManifest


def _manifest_records(root: Path) -> tuple[_ManifestRecord, ...]:
    records: list[_ManifestRecord] = []
    targets: set[str] = set()
    for manifest_path in sorted(root.rglob("*.manifest.json")):
        try:
            manifest = RawFileManifest.model_validate_json(manifest_path.read_bytes())
        except ValueError as exc:
            raise RawDataIntegrityError(f"invalid raw manifest: {manifest_path}") from exc
        if manifest.data_file in targets:
            raise RawDataIntegrityError(f"duplicate raw manifest target: {manifest.data_file}")
        targets.add(manifest.data_file)
        records.append(_ManifestRecord(manifest_path, manifest))
    return tuple(records)


def _safe_data_path(root: Path, data_file: str) -> Path:
    resolved_root = root.resolve()
    data_path = (root / data_file).resolve()
    if resolved_root not in data_path.parents:
        raise RawDataIntegrityError(f"unsafe raw manifest path: {data_file}")
    return data_path


def _active_manifest_records(root: Path) -> tuple[_ManifestRecord, ...]:
    records = _manifest_records(root)
    superseded = {data_file for record in records for data_file in record.manifest.supersedes}
    return tuple(record for record in records if record.manifest.data_file not in superseded)


def _validate_record_sizes(root: Path, records: tuple[_ManifestRecord, ...]) -> None:
    for record in records:
        data_path = _safe_data_path(root, record.manifest.data_file)
        if not data_path.is_file() or data_path.stat().st_size != record.manifest.byte_size:
            raise RawDataIntegrityError(f"raw file size mismatch: {record.manifest.data_file}")


def summarize_raw_storage(root: Path) -> RawStorageSummary:
    """Count retained immutable files from validated manifests and file sizes."""

    if not root.exists():
        return RawStorageSummary()
    row_count = 0
    byte_size = 0
    active = _active_manifest_records(root)
    _validate_record_sizes(root, active)
    for record in active:
        row_count += record.manifest.row_count
        byte_size += record.manifest.byte_size
    return RawStorageSummary(
        file_count=len(active),
        row_count=row_count,
        byte_size=byte_size,
    )


def active_raw_file_manifests(root: Path) -> tuple[RawFileManifest, ...]:
    """Return the size-validated active immutable manifest set in stable order."""

    if not root.exists():
        return ()
    active = _active_manifest_records(root)
    _validate_record_sizes(root, active)
    return tuple(
        record.manifest for record in sorted(active, key=lambda item: item.manifest.data_file)
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


def _retirement_paths(root: Path, data_file: str, reason: str) -> tuple[Path, Path]:
    token = sha256(data_file.encode()).hexdigest()
    maintenance_root = root.parent / "maintenance"
    return (
        maintenance_root / "pending" / reason / f"{token}.json",
        maintenance_root / "retired" / reason / f"{token}.json",
    )


def _retire_record(root: Path, record: _ManifestRecord, *, reason: str) -> int:
    """Make a file non-readable before deleting its immutable payload."""

    data_path = _safe_data_path(root, record.manifest.data_file)
    pending_path, retired_path = _retirement_paths(root, record.manifest.data_file, reason)
    if pending_path.exists() or retired_path.exists():
        raise RawDataIntegrityError(
            f"raw retirement marker already exists: {record.manifest.data_file}"
        )
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    retired_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(record.path, pending_path)
    data_path.unlink(missing_ok=True)
    os.replace(pending_path, retired_path)
    return record.manifest.byte_size


def _resume_retired_deletions(root: Path) -> None:
    active_targets = {record.manifest.data_file for record in _manifest_records(root)}
    pending_root = root.parent / "maintenance" / "pending"
    if pending_root.exists():
        for pending_path in sorted(pending_root.rglob("*.json")):
            try:
                manifest = RawFileManifest.model_validate_json(pending_path.read_bytes())
            except ValueError as exc:
                raise RawDataIntegrityError(
                    f"invalid raw retirement marker: {pending_path}"
                ) from exc
            if manifest.data_file in active_targets:
                raise RawDataIntegrityError(
                    f"retired raw target is still active: {manifest.data_file}"
                )
            _safe_data_path(root, manifest.data_file).unlink(missing_ok=True)
            reason = pending_path.parent.name
            _, retired_path = _retirement_paths(root, manifest.data_file, reason)
            retired_path.parent.mkdir(parents=True, exist_ok=True)
            if retired_path.exists():
                raise RawDataIntegrityError(
                    f"completed raw retirement marker already exists: {manifest.data_file}"
                )
            os.replace(pending_path, retired_path)

    for pattern, reason in (
        ("*.compacted.json", "compacted"),
        ("*.expired.json", "expired"),
        ("*.capacity.json", "capacity"),
    ):
        for legacy_path in sorted(root.rglob(pattern)):
            try:
                manifest = RawFileManifest.model_validate_json(legacy_path.read_bytes())
            except ValueError as exc:
                raise RawDataIntegrityError(
                    f"invalid legacy raw retirement marker: {legacy_path}"
                ) from exc
            if manifest.data_file in active_targets:
                raise RawDataIntegrityError(
                    f"legacy retired raw target is still active: {manifest.data_file}"
                )
            _safe_data_path(root, manifest.data_file).unlink(missing_ok=True)
            _, retired_path = _retirement_paths(root, manifest.data_file, reason)
            retired_path.parent.mkdir(parents=True, exist_ok=True)
            if retired_path.exists():
                raise RawDataIntegrityError(
                    f"duplicate completed retirement marker: {manifest.data_file}"
                )
            os.replace(legacy_path, retired_path)


def _retire_superseded_sources(root: Path) -> None:
    records = _manifest_records(root)
    superseded = {data_file for record in records for data_file in record.manifest.supersedes}
    for record in records:
        if record.manifest.data_file in superseded:
            _retire_record(root, record, reason="compacted")


def _write_compacted_records(
    root: Path,
    records: tuple[_ManifestRecord, ...],
) -> tuple[int, int]:
    sources = {record.manifest.source for record in records}
    event_types = {record.manifest.event_type for record in records}
    parents = {record.path.parent for record in records}
    if len(sources) != 1 or len(event_types) != 1 or len(parents) != 1:
        raise RawDataIntegrityError("raw compaction inputs must share one partition contract")

    tables: list[pa.Table] = []
    for record in records:
        if not verify_manifest_checksum(root, record.manifest):
            raise RawDataIntegrityError(
                f"raw checksum mismatch before compaction: {record.manifest.data_file}"
            )
        with (root / record.manifest.data_file).open("rb") as source:
            parquet_file = pq.ParquetFile(source)
            metadata = parquet_file.schema_arrow.metadata or {}
            if metadata.get(b"quantforge_schema_version") != b"1":
                raise RawDataIntegrityError(
                    f"raw schema mismatch before compaction: {record.manifest.data_file}"
                )
            table = parquet_file.read()
        if table.num_rows != record.manifest.row_count:
            raise RawDataIntegrityError(
                f"raw row count mismatch before compaction: {record.manifest.data_file}"
            )
        tables.append(table)

    table = pa.concat_tables(tables)
    partition = next(iter(parents))
    timestamp_token = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    data_path = partition / f"compact-{timestamp_token}-{uuid4().hex}.parquet"
    temp_data = partition / f".{data_path.name}.{uuid4().hex}.tmp"
    manifest_path = data_path.with_suffix(".manifest.json")
    temp_manifest = partition / f".{manifest_path.name}.{uuid4().hex}.tmp"
    try:
        pq.write_table(
            table,
            temp_data,
            compression="zstd",
            use_dictionary=True,
            write_statistics=True,
        )
        manifest = RawFileManifest(
            manifest_schema_version=2,
            source=next(iter(sources)),
            event_type=next(iter(event_types)),
            data_file=data_path.relative_to(root).as_posix(),
            sha256=_file_sha256(temp_data),
            row_count=sum(record.manifest.row_count for record in records),
            byte_size=temp_data.stat().st_size,
            min_exchange_timestamp=min(
                record.manifest.min_exchange_timestamp for record in records
            ),
            max_exchange_timestamp=max(
                record.manifest.max_exchange_timestamp for record in records
            ),
            created_at_utc=max(record.manifest.created_at_utc for record in records),
            supersedes=tuple(record.manifest.data_file for record in records),
        )
        temp_manifest.write_bytes(
            orjson.dumps(
                manifest.model_dump(mode="json"),
                option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
            )
            + b"\n"
        )
        if data_path.exists() or manifest_path.exists():
            raise FileExistsError("compacted raw target unexpectedly already exists")
        os.replace(temp_data, data_path)
        os.replace(temp_manifest, manifest_path)
        for record in records:
            _retire_record(root, record, reason="compacted")
        return (
            sum(record.manifest.byte_size for record in records),
            manifest.byte_size,
        )
    finally:
        temp_data.unlink(missing_ok=True)
        temp_manifest.unlink(missing_ok=True)


def compact_raw_storage(
    root: Path,
    *,
    now_utc: datetime,
    min_files: int,
    target_rows: int,
) -> tuple[int, int, int, int]:
    """Compact completed creation-hour partitions without changing replayed rows."""

    if now_utc.tzinfo is None or now_utc.utcoffset() != UTC.utcoffset(now_utc):
        raise ValueError("raw compaction time must be UTC-aware")
    if min_files < 2 or target_rows < 1:
        raise ValueError("raw compaction bounds are invalid")
    _retire_superseded_sources(root)
    _resume_retired_deletions(root)
    completed_before = now_utc.replace(minute=0, second=0, microsecond=0)
    grouped: dict[Path, list[_ManifestRecord]] = defaultdict(list)
    for record in _active_manifest_records(root):
        if record.manifest.created_at_utc < completed_before:
            grouped[record.path.parent].append(record)

    source_files = 0
    output_files = 0
    source_bytes = 0
    output_bytes = 0
    for records in grouped.values():
        ordered = sorted(
            records,
            key=lambda record: (
                record.manifest.created_at_utc,
                record.manifest.data_file,
            ),
        )
        chunk: list[_ManifestRecord] = []
        chunk_rows = 0
        chunks: list[tuple[_ManifestRecord, ...]] = []
        for record in ordered:
            if (
                chunk
                and chunk_rows + record.manifest.row_count > target_rows
                and len(chunk) >= min_files
            ):
                chunks.append(tuple(chunk))
                chunk = []
                chunk_rows = 0
            chunk.append(record)
            chunk_rows += record.manifest.row_count
            if chunk_rows >= target_rows and len(chunk) >= min_files:
                chunks.append(tuple(chunk))
                chunk = []
                chunk_rows = 0
        if len(chunk) >= min_files:
            chunks.append(tuple(chunk))
        for selected in chunks:
            old_bytes, new_bytes = _write_compacted_records(root, selected)
            source_files += len(selected)
            output_files += 1
            source_bytes += old_bytes
            output_bytes += new_bytes
    return source_files, output_files, source_bytes, output_bytes


def _expire_records(
    root: Path,
    records: tuple[_ManifestRecord, ...],
    *,
    reason: Literal["expired", "capacity"],
) -> int:
    reclaimed = 0
    for record in records:
        reclaimed += _retire_record(root, record, reason=reason)
    return reclaimed


def maintain_raw_storage(
    root: Path,
    *,
    policy: RawStoragePolicy,
    now_utc: datetime | None = None,
    compact: bool = True,
) -> RawStorageMaintenance:
    """Compact and prune one explicit raw root, then return verified retained totals."""

    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() != UTC.utcoffset(now):
        raise ValueError("raw storage maintenance time must be UTC-aware")
    root.mkdir(parents=True, exist_ok=True)
    cleanup_orphan_temp_files(root)
    _retire_superseded_sources(root)
    _resume_retired_deletions(root)
    summarize_raw_storage(root)

    compacted_source_files = 0
    compacted_output_files = 0
    compacted_source_bytes = 0
    compacted_output_bytes = 0
    if compact:
        (
            compacted_source_files,
            compacted_output_files,
            compacted_source_bytes,
            compacted_output_bytes,
        ) = compact_raw_storage(
            root,
            now_utc=now,
            min_files=policy.compaction_min_files,
            target_rows=policy.compaction_target_rows,
        )

    active = _active_manifest_records(root)
    retention_cutoff = now - timedelta(days=policy.retention_days)
    expired = tuple(
        record for record in active if record.manifest.created_at_utc < retention_cutoff
    )
    retention_bytes = _expire_records(root, expired, reason="expired")

    active = _active_manifest_records(root)
    retained_bytes = sum(record.manifest.byte_size for record in active)
    capacity: list[_ManifestRecord] = []
    for record in sorted(
        active,
        key=lambda item: (item.manifest.created_at_utc, item.manifest.data_file),
    ):
        if retained_bytes <= policy.max_bytes:
            break
        capacity.append(record)
        retained_bytes -= record.manifest.byte_size
    capacity_bytes = _expire_records(root, tuple(capacity), reason="capacity")
    _resume_retired_deletions(root)
    summary = summarize_raw_storage(root)
    free_bytes = shutil.disk_usage(root.resolve()).free
    return RawStorageMaintenance(
        summary=summary,
        compacted_source_files=compacted_source_files,
        compacted_output_files=compacted_output_files,
        retention_deleted_files=len(expired),
        capacity_deleted_files=len(capacity),
        reclaimed_bytes=max(
            0,
            compacted_source_bytes - compacted_output_bytes + retention_bytes + capacity_bytes,
        ),
        disk_free_bytes=free_bytes,
    )


def require_raw_storage_capacity(root: Path, policy: RawStoragePolicy) -> int:
    """Fail before accepting more public data when the explicit filesystem is too full."""

    free_bytes = shutil.disk_usage(root.resolve()).free
    if free_bytes < policy.min_free_bytes:
        raise RawStorageCapacityError(
            "paper raw-data filesystem is below the configured free-space safety floor"
        )
    return free_bytes


def _require_inventory_deadline(started_at: float, maximum_elapsed_seconds: float | None) -> None:
    if maximum_elapsed_seconds is not None and monotonic() - started_at > maximum_elapsed_seconds:
        raise RawResearchInventoryTimeout(
            f"research inventory exceeded {maximum_elapsed_seconds:g} seconds"
        )


def _require_read_deadline(started_at: float, maximum_elapsed_seconds: float | None) -> None:
    if maximum_elapsed_seconds is not None and monotonic() - started_at > maximum_elapsed_seconds:
        raise RawEventReadTimeout(f"raw event read exceeded {maximum_elapsed_seconds:g} seconds")


def _selected_research_batch(
    batch: pa.RecordBatch,
    *,
    event_type: str,
    markets: frozenset[str] | None,
    maximum_exchange_timestamp_utc: datetime | None,
    minimum_received_at_utc: datetime | None,
    maximum_received_at_utc: datetime | None,
    exclude_marked_duplicates: bool,
    exclude_quality_flagged_events: bool,
) -> pa.Table:
    table = pa.Table.from_batches([batch])
    event_type_matches = pc.equal(table["event_type"], event_type)
    if not bool(pc.all(event_type_matches).as_py()):
        raise RawDataIntegrityError("raw event type disagrees with its manifest")
    mask = event_type_matches
    if markets is not None:
        mask = pc.and_(
            mask,
            pc.is_in(table["market"], value_set=pa.array(sorted(markets))),
        )
    if maximum_exchange_timestamp_utc is not None:
        mask = pc.and_(
            mask,
            pc.less_equal(table["exchange_timestamp"], maximum_exchange_timestamp_utc),
        )
    if minimum_received_at_utc is not None:
        mask = pc.and_(
            mask,
            pc.greater_equal(table["received_at_utc"], minimum_received_at_utc),
        )
    if maximum_received_at_utc is not None:
        mask = pc.and_(
            mask,
            pc.less_equal(table["received_at_utc"], maximum_received_at_utc),
        )
    if exclude_marked_duplicates:
        mask = pc.and_(mask, pc.invert(table["is_duplicate"]))
    if exclude_quality_flagged_events:
        mask = pc.and_(mask, pc.equal(pc.list_value_length(table["quality_flags"]), 0))
    selected = table.filter(mask)
    if selected.num_rows == 0:
        return selected
    if not bool(pc.all(pc.starts_with(selected["market"], "KRW-")).as_py()):
        raise RawDataIntegrityError("research selection contains a non-KRW market")
    payload_hashes_valid = pc.match_substring_regex(selected["raw_payload_hash"], "^[a-f0-9]{64}$")
    if not bool(pc.all(payload_hashes_valid).as_py()):
        raise RawDataIntegrityError("raw payload hash is malformed")
    return selected


def _identity_record(
    received_microseconds: int,
    received_monotonic_ns: int,
    connection_id: str,
    local_sequence: int,
    event_id: str,
    payload_hash: str,
) -> bytes:
    try:
        return _RESEARCH_IDENTITY.pack(
            received_microseconds,
            received_monotonic_ns,
            UUID(connection_id).bytes,
            local_sequence,
            UUID(event_id).bytes,
            bytes.fromhex(payload_hash),
        )
    except (OverflowError, ValueError, struct.error) as exc:
        raise RawDataIntegrityError("raw research identity is malformed") from exc


def _write_research_runs(
    selected: pa.Table,
    identity_path: Path,
    event_id_path: Path,
) -> None:
    columns = (
        pc.cast(selected["received_at_utc"], pa.int64()).to_pylist(),
        selected["received_monotonic_ns"].to_pylist(),
        selected["connection_id"].to_pylist(),
        selected["local_sequence"].to_pylist(),
        selected["event_id"].to_pylist(),
        selected["raw_payload_hash"].to_pylist(),
    )
    identities = sorted(_identity_record(*values) for values in zip(*columns, strict=True))
    identity_path.write_bytes(b"".join(identities))
    event_ids = sorted(identity[40:56] for identity in identities)
    event_id_path.write_bytes(b"".join(event_ids))


def _iter_fixed_records(stream: BinaryIO, record_size: int) -> Iterator[bytes]:
    while record := stream.read(record_size):
        if len(record) != record_size:
            raise RawDataIntegrityError("research scratch run is truncated")
        yield record


def _merge_event_id_runs(
    paths: list[Path],
    *,
    selected_event_count: int,
    started_at: float,
    maximum_elapsed_seconds: float | None,
    progress: Callable[[RawResearchInventoryProgress], None] | None,
) -> None:
    previous: bytes | None = None
    processed = 0
    next_checkpoint = 100_000
    with ExitStack() as stack:
        streams = tuple(stack.enter_context(path.open("rb")) for path in paths)
        records = merge(
            *(_iter_fixed_records(stream, _RESEARCH_EVENT_ID_SIZE) for stream in streams)
        )
        for record in records:
            if record == previous:
                raise RawDataIntegrityError("duplicate event identity in research selection")
            previous = record
            processed += 1
            if processed >= next_checkpoint:
                _require_inventory_deadline(started_at, maximum_elapsed_seconds)
                next_checkpoint += 100_000
                if progress is not None and processed % 1_000_000 == 0:
                    progress(
                        RawResearchInventoryProgress(
                            phase="event-id-check",
                            completed_units=processed,
                            total_units=selected_event_count,
                            selected_event_count=selected_event_count,
                        )
                    )
    if processed != selected_event_count:
        raise RawDataIntegrityError("research event-id run count does not reconcile")


def _merge_identity_runs(
    paths: list[Path],
    *,
    selected_event_count: int,
    started_at: float,
    maximum_elapsed_seconds: float | None,
    progress: Callable[[RawResearchInventoryProgress], None] | None,
) -> str:
    digest = sha256()
    processed = 0
    next_checkpoint = 100_000
    with ExitStack() as stack:
        streams = tuple(stack.enter_context(path.open("rb")) for path in paths)
        records = merge(
            *(_iter_fixed_records(stream, _RESEARCH_IDENTITY.size) for stream in streams)
        )
        for record in records:
            (
                received_microseconds,
                received_monotonic_ns,
                connection_id,
                local_sequence,
                event_id,
                payload_hash,
            ) = _RESEARCH_IDENTITY.unpack(record)
            received_at = _UNIX_EPOCH + timedelta(microseconds=received_microseconds)
            digest.update(
                "|".join(
                    (
                        received_at.isoformat(),
                        str(received_monotonic_ns),
                        str(UUID(bytes=connection_id)),
                        str(local_sequence),
                        str(UUID(bytes=event_id)),
                        payload_hash.hex(),
                    )
                ).encode()
            )
            digest.update(b"\n")
            processed += 1
            if processed >= next_checkpoint:
                _require_inventory_deadline(started_at, maximum_elapsed_seconds)
                next_checkpoint += 100_000
                if progress is not None and processed % 1_000_000 == 0:
                    progress(
                        RawResearchInventoryProgress(
                            phase="dataset-hash",
                            completed_units=processed,
                            total_units=selected_event_count,
                            selected_event_count=selected_event_count,
                        )
                    )
    if processed != selected_event_count:
        raise RawDataIntegrityError("research identity run count does not reconcile")
    return digest.hexdigest()


def scan_raw_event_research_inventory(
    root: Path,
    *,
    maximum_exchange_timestamp_utc: datetime | None = None,
    maximum_received_at_utc: datetime | None = None,
    exclude_marked_duplicates: bool = False,
    exclude_quality_flagged_events: bool = False,
    scratch_root: Path | None = None,
    maximum_elapsed_seconds: float | None = None,
    progress: Callable[[RawResearchInventoryProgress], None] | None = None,
) -> RawEventResearchInventory:
    """Verify and externally fingerprint detailed public rows with bounded memory."""

    for cutoff in (maximum_exchange_timestamp_utc, maximum_received_at_utc):
        if cutoff is not None and (
            cutoff.tzinfo is None or cutoff.utcoffset() != UTC.utcoffset(cutoff)
        ):
            raise ValueError("research inventory cutoffs must be UTC-aware")
    if maximum_elapsed_seconds is not None and maximum_elapsed_seconds <= 0:
        raise ValueError("research inventory wall-time budget must be positive")

    started_at = monotonic()
    counts: dict[str, dict[str, object]] = {}
    selected_files = 0
    selected_events = 0
    columns = (
        "event_id",
        "event_type",
        "market",
        "exchange_timestamp",
        "received_at_utc",
        "received_monotonic_ns",
        "connection_id",
        "local_sequence",
        "raw_payload_hash",
        "is_duplicate",
        "quality_flags",
    )
    active_records = tuple(
        sorted(_active_manifest_records(root), key=lambda item: item.manifest.data_file)
    )
    manifest_digest = sha256()
    for record in active_records:
        manifest_sha256 = sha256(
            orjson.dumps(record.manifest.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        ).hexdigest()
        manifest_digest.update(f"{record.manifest.data_file}|{manifest_sha256}\n".encode())

    detailed_records = tuple(
        record for record in active_records if record.manifest.event_type in {"trade", "orderbook"}
    )
    selected_scratch_root = scratch_root or root.parent
    selected_scratch_root.mkdir(parents=True, exist_ok=True)
    identity_paths: list[Path] = []
    event_id_paths: list[Path] = []
    run_number = 0
    with TemporaryDirectory(prefix=".quantforge-research-", dir=selected_scratch_root) as temporary:
        temporary_root = Path(temporary)
        for file_number, record in enumerate(detailed_records, start=1):
            _require_inventory_deadline(started_at, maximum_elapsed_seconds)
            manifest = record.manifest
            try:
                checksum_valid = verify_manifest_checksum(root, manifest)
            except ValueError as exc:
                raise RawDataIntegrityError(
                    f"unsafe raw manifest path: {manifest.data_file}"
                ) from exc
            if not checksum_valid:
                raise RawDataIntegrityError(f"raw checksum mismatch: {manifest.data_file}")
            parquet_file = pq.ParquetFile(root / manifest.data_file)
            metadata = parquet_file.schema_arrow.metadata or {}
            if (
                metadata.get(b"quantforge_schema_version")
                != str(manifest.event_schema_version).encode()
            ):
                raise RawDataIntegrityError(f"raw schema version mismatch: {manifest.data_file}")
            if parquet_file.metadata.num_rows != manifest.row_count:
                raise RawDataIntegrityError(f"raw row count mismatch: {manifest.data_file}")

            file_selected = False
            for batch in parquet_file.iter_batches(batch_size=65_536, columns=columns):
                _require_inventory_deadline(started_at, maximum_elapsed_seconds)
                selected = _selected_research_batch(
                    batch,
                    event_type=manifest.event_type,
                    markets=None,
                    maximum_exchange_timestamp_utc=maximum_exchange_timestamp_utc,
                    minimum_received_at_utc=None,
                    maximum_received_at_utc=maximum_received_at_utc,
                    exclude_marked_duplicates=exclude_marked_duplicates,
                    exclude_quality_flagged_events=exclude_quality_flagged_events,
                )
                if selected.num_rows == 0:
                    continue
                run_number += 1
                identity_path = temporary_root / f"identity-{run_number:06d}.bin"
                event_id_path = temporary_root / f"event-id-{run_number:06d}.bin"
                _write_research_runs(selected, identity_path, event_id_path)
                identity_paths.append(identity_path)
                event_id_paths.append(event_id_path)
                selected_events += selected.num_rows
                file_selected = True

                summary = (
                    selected.select(["market", "received_at_utc"])
                    .group_by("market")
                    .aggregate(
                        [
                            ("received_at_utc", "count"),
                            ("received_at_utc", "min"),
                            ("received_at_utc", "max"),
                        ]
                    )
                )
                for row in summary.to_pylist():
                    market = cast(str, row["market"])
                    first = cast(datetime, row["received_at_utc_min"])
                    last = cast(datetime, row["received_at_utc_max"])
                    market_counts = counts.setdefault(
                        market,
                        {
                            "trade": 0,
                            "orderbook": 0,
                            "first": first,
                            "last": last,
                        },
                    )
                    market_counts[manifest.event_type] = cast(
                        int, market_counts[manifest.event_type]
                    ) + cast(int, row["received_at_utc_count"])
                    market_counts["first"] = min(cast(datetime, market_counts["first"]), first)
                    market_counts["last"] = max(cast(datetime, market_counts["last"]), last)
            selected_files += int(file_selected)
            if progress is not None:
                progress(
                    RawResearchInventoryProgress(
                        phase="scan",
                        completed_units=file_number,
                        total_units=len(detailed_records),
                        selected_event_count=selected_events,
                    )
                )

        _merge_event_id_runs(
            event_id_paths,
            selected_event_count=selected_events,
            started_at=started_at,
            maximum_elapsed_seconds=maximum_elapsed_seconds,
            progress=progress,
        )
        dataset_hash = _merge_identity_runs(
            identity_paths,
            selected_event_count=selected_events,
            started_at=started_at,
            maximum_elapsed_seconds=maximum_elapsed_seconds,
            progress=progress,
        )

    markets = tuple(
        RawEventMarketInventory(
            market=market,
            trade_events=cast(int, values["trade"]),
            orderbook_events=cast(int, values["orderbook"]),
            first_received_at_utc=cast(datetime, values["first"]),
            last_received_at_utc=cast(datetime, values["last"]),
        )
        for market, values in sorted(counts.items())
    )
    return RawEventResearchInventory(
        dataset_hash=dataset_hash,
        manifest_set_sha256=manifest_digest.hexdigest(),
        maximum_exchange_timestamp_utc=maximum_exchange_timestamp_utc,
        maximum_received_at_utc=maximum_received_at_utc,
        exclude_marked_duplicates=exclude_marked_duplicates,
        exclude_quality_flagged_events=exclude_quality_flagged_events,
        selected_file_count=selected_files,
        selected_event_count=selected_events,
        markets=markets,
    )


def read_raw_events(
    root: Path,
    *,
    markets: frozenset[str] | None = None,
    event_types: frozenset[str] | None = None,
    maximum_exchange_timestamp_utc: datetime | None = None,
    minimum_received_at_utc: datetime | None = None,
    maximum_received_at_utc: datetime | None = None,
    exclude_marked_duplicates: bool = False,
    exclude_quality_flagged_events: bool = False,
    maximum_events: int | None = None,
    maximum_elapsed_seconds: float | None = None,
) -> list[EventEnvelope]:
    """Verify selected manifests/checksums and reconstruct bounded immutable envelopes."""

    for bound in (
        maximum_exchange_timestamp_utc,
        minimum_received_at_utc,
        maximum_received_at_utc,
    ):
        if bound is not None and (
            bound.tzinfo is None or bound.utcoffset() != UTC.utcoffset(bound)
        ):
            raise ValueError("raw event selection timestamps must be UTC-aware")
    if (
        minimum_received_at_utc is not None
        and maximum_received_at_utc is not None
        and maximum_received_at_utc < minimum_received_at_utc
    ):
        raise ValueError("raw event selection interval is reversed")
    if markets is not None and (
        not markets or any(not item.startswith("KRW-") for item in markets)
    ):
        raise ValueError("raw event market selection must contain uppercase KRW markets")
    if event_types is not None and (
        not event_types or not event_types <= {"ticker", "trade", "orderbook"}
    ):
        raise ValueError("raw event type selection is invalid")
    if maximum_events is not None and maximum_events < 1:
        raise ValueError("raw event limit must be positive")
    if maximum_elapsed_seconds is not None and maximum_elapsed_seconds <= 0:
        raise ValueError("raw event wall-time limit must be positive")

    started_at = monotonic()
    events: list[EventEnvelope] = []
    for record in _active_manifest_records(root):
        _require_read_deadline(started_at, maximum_elapsed_seconds)
        manifest = record.manifest
        if event_types is not None and manifest.event_type not in event_types:
            continue
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
        if parquet_file.metadata.num_rows != manifest.row_count:
            raise RawDataIntegrityError(f"raw row count mismatch: {manifest.data_file}")
        for batch in parquet_file.iter_batches(batch_size=65_536):
            _require_read_deadline(started_at, maximum_elapsed_seconds)
            selected = _selected_research_batch(
                batch,
                event_type=manifest.event_type,
                markets=markets,
                maximum_exchange_timestamp_utc=maximum_exchange_timestamp_utc,
                minimum_received_at_utc=minimum_received_at_utc,
                maximum_received_at_utc=maximum_received_at_utc,
                exclude_marked_duplicates=exclude_marked_duplicates,
                exclude_quality_flagged_events=exclude_quality_flagged_events,
            )
            if maximum_events is not None and len(events) + selected.num_rows > maximum_events:
                raise RawEventReadLimitError(
                    f"raw event selection exceeds the {maximum_events} event limit"
                )
            for row in selected.to_pylist():
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
    _require_read_deadline(started_at, maximum_elapsed_seconds)
    ordered = sorted(
        events,
        key=lambda event: (
            event.received_at_utc,
            event.received_monotonic_ns,
            str(event.connection_id),
            event.local_sequence,
            str(event.event_id),
        ),
    )
    _require_read_deadline(started_at, maximum_elapsed_seconds)
    return ordered

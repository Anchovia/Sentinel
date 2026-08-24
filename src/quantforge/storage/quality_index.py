"""Incremental, manifest-backed quality and research-availability index."""

import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal, cast
from uuid import uuid4

import orjson
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.storage.parquet import (
    RawDataIntegrityError,
    RawFileManifest,
    active_raw_file_manifests,
    verify_manifest_checksum,
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RawIndexedFileMarket(_FrozenModel):
    """Per-market availability contained in one verified immutable file."""

    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    event_count: Annotated[int, Field(gt=0)]
    first_received_at_utc: datetime
    last_received_at_utc: datetime

    @field_validator("first_received_at_utc", "last_received_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("indexed market timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def require_ordered_interval(self) -> "RawIndexedFileMarket":
        if self.last_received_at_utc < self.first_received_at_utc:
            raise ValueError("indexed market interval is reversed")
        return self


class RawIndexedFile(_FrozenModel):
    """Cached verification evidence for one active manifest target."""

    data_file: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    data_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source: str = Field(min_length=1)
    event_type: Literal["ticker", "trade", "orderbook"]
    event_schema_version: Annotated[int, Field(ge=1)]
    row_count: Annotated[int, Field(gt=0)]
    byte_size: Annotated[int, Field(gt=0)]
    min_exchange_timestamp_utc: datetime
    max_exchange_timestamp_utc: datetime
    verified_at_utc: datetime
    duplicate_message_count: Annotated[int, Field(ge=0)] = 0
    duplicate_event_identity_count: Annotated[int, Field(ge=0)] = 0
    received_time_regressions: Annotated[int, Field(ge=0)] = 0
    local_sequence_regressions: Annotated[int, Field(ge=0)] = 0
    quality_flagged_event_count: Annotated[int, Field(ge=0)] = 0
    markets: tuple[RawIndexedFileMarket, ...]

    @field_validator(
        "min_exchange_timestamp_utc",
        "max_exchange_timestamp_utc",
        "verified_at_utc",
    )
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("indexed file timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_file_summary(self) -> "RawIndexedFile":
        names = tuple(item.market for item in self.markets)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("indexed file markets must be sorted and unique")
        if sum(item.event_count for item in self.markets) != self.row_count:
            raise ValueError("indexed file market counts do not reconcile")
        if self.max_exchange_timestamp_utc < self.min_exchange_timestamp_utc:
            raise ValueError("indexed exchange interval is reversed")
        return self


class RawIndexedMarket(_FrozenModel):
    """Aggregated verified availability for one public KRW market."""

    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    ticker_events: Annotated[int, Field(ge=0)] = 0
    trade_events: Annotated[int, Field(ge=0)] = 0
    orderbook_events: Annotated[int, Field(ge=0)] = 0
    first_received_at_utc: datetime
    last_received_at_utc: datetime
    detailed_first_received_at_utc: datetime | None = None
    detailed_last_received_at_utc: datetime | None = None

    @field_validator(
        "first_received_at_utc",
        "last_received_at_utc",
        "detailed_first_received_at_utc",
        "detailed_last_received_at_utc",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError("indexed aggregate timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_market_summary(self) -> "RawIndexedMarket":
        if self.last_received_at_utc < self.first_received_at_utc:
            raise ValueError("indexed aggregate interval is reversed")
        detailed = (self.detailed_first_received_at_utc, self.detailed_last_received_at_utc)
        if (detailed[0] is None) != (detailed[1] is None):
            raise ValueError("detailed interval must be wholly present or absent")
        if detailed[0] is not None and cast(datetime, detailed[1]) < detailed[0]:
            raise ValueError("indexed detailed interval is reversed")
        if self.trade_events + self.orderbook_events and detailed[0] is None:
            raise ValueError("detailed events require a detailed interval")
        return self

    @property
    def event_count(self) -> int:
        return self.ticker_events + self.trade_events + self.orderbook_events

    @property
    def detailed_span_seconds(self) -> float:
        if self.detailed_first_received_at_utc is None:
            return 0.0
        return (
            cast(datetime, self.detailed_last_received_at_utc) - self.detailed_first_received_at_utc
        ).total_seconds()


class RawResearchReadinessPolicy(_FrozenModel):
    """Diagnostic threshold only; it never authorizes a trial or paper order."""

    minimum_observed_span_hours: Annotated[int, Field(gt=0)] = 24
    minimum_trade_events_per_market: Annotated[int, Field(gt=0)] = 20_000
    minimum_orderbook_events_per_market: Annotated[int, Field(gt=0)] = 20_000
    minimum_eligible_markets: Annotated[int, Field(gt=0)] = 3

    @property
    def digest(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()


class RawResearchReadiness(_FrozenModel):
    """Current availability for a future preregistration, never an experiment approval."""

    policy_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    eligible_markets: tuple[str, ...]
    required_eligible_markets: Annotated[int, Field(gt=0)]
    ready_for_new_preregistration: bool
    current_experiment_authorized: Literal[False] = False
    paper_order_gate_changed: Literal[False] = False

    @model_validator(mode="after")
    def validate_readiness(self) -> "RawResearchReadiness":
        if self.eligible_markets != tuple(sorted(set(self.eligible_markets))):
            raise ValueError("eligible markets must be sorted and unique")
        expected = len(self.eligible_markets) >= self.required_eligible_markets
        if self.ready_for_new_preregistration != expected:
            raise ValueError("research readiness does not match its eligible market count")
        return self


class RawDataQualityIndex(_FrozenModel):
    """Bounded sidecar cache for verified active raw manifests."""

    schema_version: Literal["raw-data-quality-index-1"] = "raw-data-quality-index-1"
    generated_at_utc: datetime
    storage_label: str = Field(min_length=1, max_length=200)
    manifest_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    measurement_status: Literal["VERIFIED_STORAGE", "INSUFFICIENT_SAMPLE"]
    active_file_count: Annotated[int, Field(ge=0)]
    active_row_count: Annotated[int, Field(ge=0)]
    active_byte_size: Annotated[int, Field(ge=0)]
    verified_file_count: Annotated[int, Field(ge=0)]
    checksum_failures: Literal[0] = 0
    scanned_file_count: Annotated[int, Field(ge=0)]
    reused_file_count: Annotated[int, Field(ge=0)]
    retired_cache_entry_count: Annotated[int, Field(ge=0)]
    event_counts: tuple[tuple[str, int], ...]
    duplicate_message_count: Annotated[int, Field(ge=0)]
    duplicate_event_identity_count: Annotated[int, Field(ge=0)]
    received_time_regressions: Annotated[int, Field(ge=0)]
    local_sequence_regressions: Annotated[int, Field(ge=0)]
    quality_flagged_event_count: Annotated[int, Field(ge=0)]
    files: tuple[RawIndexedFile, ...]
    markets: tuple[RawIndexedMarket, ...]
    research_readiness: RawResearchReadiness
    authentication_used: Literal[False] = False
    private_network_used: Literal[False] = False
    order_submission_available: Literal[False] = False
    limitation: str = Field(min_length=1)

    @field_validator("generated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("raw quality index timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_index_totals(self) -> "RawDataQualityIndex":
        file_names = tuple(item.data_file for item in self.files)
        market_names = tuple(item.market for item in self.markets)
        if file_names != tuple(sorted(file_names)) or len(file_names) != len(set(file_names)):
            raise ValueError("indexed files must be sorted and unique")
        if market_names != tuple(sorted(market_names)) or len(market_names) != len(
            set(market_names)
        ):
            raise ValueError("indexed markets must be sorted and unique")
        if self.active_file_count != len(self.files):
            raise ValueError("active file count does not reconcile")
        if self.verified_file_count != self.active_file_count:
            raise ValueError("every active file must be checksum verified")
        if self.active_row_count != sum(item.row_count for item in self.files):
            raise ValueError("active row count does not reconcile")
        if self.active_byte_size != sum(item.byte_size for item in self.files):
            raise ValueError("active byte size does not reconcile")
        if sum(value for _, value in self.event_counts) != self.active_row_count:
            raise ValueError("event counts do not reconcile")
        expected_status = "VERIFIED_STORAGE" if self.active_file_count else "INSUFFICIENT_SAMPLE"
        if self.measurement_status != expected_status:
            raise ValueError("measurement status does not match active storage")
        return self


def _manifest_sha256(manifest: RawFileManifest) -> str:
    payload = orjson.dumps(manifest.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    return sha256(payload).hexdigest()


def _require_constant(table: pa.Table, column: str, expected: object, data_file: str) -> None:
    matches = pc.equal(table[column], pa.scalar(expected))
    if not bool(pc.all(matches).as_py()):
        raise RawDataIntegrityError(f"raw {column} disagrees with manifest: {data_file}")


def _count_regressions(column: pa.ChunkedArray, *, allow_equal: bool) -> int:
    differences = pc.pairwise_diff(column.combine_chunks())
    comparison = (
        pc.less_equal(differences, pa.scalar(0))
        if allow_equal
        else pc.less(differences, pa.scalar(timedelta(0)))
    )
    return int(pc.sum(pc.cast(pc.fill_null(comparison, False), pa.int64())).as_py() or 0)


def _scan_indexed_file(
    root: Path,
    manifest: RawFileManifest,
    *,
    manifest_sha256: str,
    verified_at_utc: datetime,
) -> RawIndexedFile:
    try:
        checksum_valid = verify_manifest_checksum(root, manifest)
    except ValueError as exc:
        raise RawDataIntegrityError(f"unsafe raw manifest path: {manifest.data_file}") from exc
    if not checksum_valid:
        raise RawDataIntegrityError(f"raw checksum mismatch: {manifest.data_file}")

    resolved_root = root.resolve()
    data_path = (root / manifest.data_file).resolve()
    if resolved_root not in data_path.parents:
        raise RawDataIntegrityError(f"unsafe raw manifest path: {manifest.data_file}")
    parquet_file = pq.ParquetFile(data_path)
    metadata = parquet_file.schema_arrow.metadata or {}
    if metadata.get(b"quantforge_schema_version") != str(manifest.event_schema_version).encode():
        raise RawDataIntegrityError(f"raw schema version mismatch: {manifest.data_file}")
    if parquet_file.metadata.num_rows != manifest.row_count:
        raise RawDataIntegrityError(f"raw row count mismatch: {manifest.data_file}")

    columns = (
        "event_id",
        "event_type",
        "schema_version",
        "source",
        "market",
        "exchange_timestamp",
        "received_at_utc",
        "local_sequence",
        "raw_payload_hash",
        "is_duplicate",
        "quality_flags",
    )
    missing = sorted(set(columns) - set(parquet_file.schema_arrow.names))
    if missing:
        raise RawDataIntegrityError(
            f"raw file is missing indexed columns {missing}: {manifest.data_file}"
        )
    table = parquet_file.read(columns=columns)
    _require_constant(table, "event_type", manifest.event_type, manifest.data_file)
    _require_constant(table, "source", manifest.source, manifest.data_file)
    _require_constant(table, "schema_version", manifest.event_schema_version, manifest.data_file)
    valid_payload_hashes = pc.match_substring_regex(table["raw_payload_hash"], r"^[a-f0-9]{64}$")
    if not bool(pc.all(valid_payload_hashes).as_py()):
        raise RawDataIntegrityError(f"raw payload hash is malformed: {manifest.data_file}")

    min_exchange = cast(datetime, pc.min(table["exchange_timestamp"]).as_py())
    max_exchange = cast(datetime, pc.max(table["exchange_timestamp"]).as_py())
    if min_exchange != manifest.min_exchange_timestamp or max_exchange != (
        manifest.max_exchange_timestamp
    ):
        raise RawDataIntegrityError(
            f"raw exchange timestamp bounds disagree with manifest: {manifest.data_file}"
        )

    grouped = table.group_by("market").aggregate(
        [
            ("received_at_utc", "min"),
            ("received_at_utc", "max"),
            ("event_id", "count"),
        ]
    )
    markets = tuple(
        RawIndexedFileMarket(
            market=cast(str, row["market"]),
            event_count=cast(int, row["event_id_count"]),
            first_received_at_utc=cast(datetime, row["received_at_utc_min"]),
            last_received_at_utc=cast(datetime, row["received_at_utc_max"]),
        )
        for row in sorted(grouped.to_pylist(), key=lambda item: cast(str, item["market"]))
    )
    distinct_event_ids = int(pc.count_distinct(table["event_id"]).as_py())
    duplicate_messages = int(pc.sum(pc.cast(table["is_duplicate"], pa.int64())).as_py() or 0)
    flagged = pc.greater(pc.list_value_length(table["quality_flags"]), 0)
    flagged_events = int(pc.sum(pc.cast(flagged, pa.int64())).as_py() or 0)
    return RawIndexedFile(
        data_file=manifest.data_file,
        manifest_sha256=manifest_sha256,
        data_sha256=manifest.sha256,
        source=manifest.source,
        event_type=cast(Literal["ticker", "trade", "orderbook"], manifest.event_type),
        event_schema_version=manifest.event_schema_version,
        row_count=manifest.row_count,
        byte_size=manifest.byte_size,
        min_exchange_timestamp_utc=min_exchange,
        max_exchange_timestamp_utc=max_exchange,
        verified_at_utc=verified_at_utc,
        duplicate_message_count=duplicate_messages,
        duplicate_event_identity_count=manifest.row_count - distinct_event_ids,
        received_time_regressions=_count_regressions(table["received_at_utc"], allow_equal=False),
        local_sequence_regressions=_count_regressions(table["local_sequence"], allow_equal=True),
        quality_flagged_event_count=flagged_events,
        markets=markets,
    )


def _aggregate_markets(files: tuple[RawIndexedFile, ...]) -> tuple[RawIndexedMarket, ...]:
    values: dict[str, dict[str, object]] = {}
    for file in files:
        for item in file.markets:
            current = values.setdefault(
                item.market,
                {
                    "ticker": 0,
                    "trade": 0,
                    "orderbook": 0,
                    "first": item.first_received_at_utc,
                    "last": item.last_received_at_utc,
                    "detailed_first": None,
                    "detailed_last": None,
                },
            )
            current[file.event_type] = cast(int, current[file.event_type]) + item.event_count
            current["first"] = min(cast(datetime, current["first"]), item.first_received_at_utc)
            current["last"] = max(cast(datetime, current["last"]), item.last_received_at_utc)
            if file.event_type in {"trade", "orderbook"}:
                first = cast(datetime | None, current["detailed_first"])
                last = cast(datetime | None, current["detailed_last"])
                current["detailed_first"] = (
                    item.first_received_at_utc
                    if first is None
                    else min(first, item.first_received_at_utc)
                )
                current["detailed_last"] = (
                    item.last_received_at_utc
                    if last is None
                    else max(last, item.last_received_at_utc)
                )
    return tuple(
        RawIndexedMarket(
            market=market,
            ticker_events=cast(int, item["ticker"]),
            trade_events=cast(int, item["trade"]),
            orderbook_events=cast(int, item["orderbook"]),
            first_received_at_utc=cast(datetime, item["first"]),
            last_received_at_utc=cast(datetime, item["last"]),
            detailed_first_received_at_utc=cast(datetime | None, item["detailed_first"]),
            detailed_last_received_at_utc=cast(datetime | None, item["detailed_last"]),
        )
        for market, item in sorted(values.items())
    )


def _research_readiness(
    markets: tuple[RawIndexedMarket, ...],
    policy: RawResearchReadinessPolicy,
) -> RawResearchReadiness:
    eligible = tuple(
        item.market
        for item in markets
        if item.detailed_span_seconds >= policy.minimum_observed_span_hours * 3600
        and item.trade_events >= policy.minimum_trade_events_per_market
        and item.orderbook_events >= policy.minimum_orderbook_events_per_market
    )
    return RawResearchReadiness(
        policy_sha256=policy.digest,
        eligible_markets=eligible,
        required_eligible_markets=policy.minimum_eligible_markets,
        ready_for_new_preregistration=len(eligible) >= policy.minimum_eligible_markets,
    )


def read_raw_data_quality_index(path: Path) -> RawDataQualityIndex:
    return RawDataQualityIndex.model_validate_json(path.read_bytes())


def write_raw_data_quality_index(index: RawDataQualityIndex, path: Path) -> Path:
    """Atomically replace the bounded sidecar index."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    payload = (
        orjson.dumps(
            index.model_dump(mode="json"),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def update_raw_data_quality_index(
    root: Path,
    index_path: Path,
    *,
    storage_label: str = "local-paper-data",
    now_utc: datetime | None = None,
    reverify_after_seconds: float = 86_400,
    research_policy: RawResearchReadinessPolicy | None = None,
) -> RawDataQualityIndex:
    """Verify only new, changed, or expired-cache active files and rebuild aggregates."""

    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() != UTC.utcoffset(now):
        raise ValueError("raw quality index time must be UTC-aware")
    if reverify_after_seconds < 0:
        raise ValueError("raw quality re-verification interval cannot be negative")
    if not storage_label.strip() or len(storage_label) > 200:
        raise ValueError("raw quality storage label is invalid")

    previous = read_raw_data_quality_index(index_path) if index_path.is_file() else None
    cached = {item.data_file: item for item in previous.files} if previous is not None else {}
    active = active_raw_file_manifests(root)
    active_names = {manifest.data_file for manifest in active}
    files: list[RawIndexedFile] = []
    scanned = 0
    reused = 0
    for manifest in active:
        fingerprint = _manifest_sha256(manifest)
        existing = cached.get(manifest.data_file)
        cache_fresh = existing is not None and (
            now - existing.verified_at_utc <= timedelta(seconds=reverify_after_seconds)
        )
        if existing is not None and existing.manifest_sha256 == fingerprint and cache_fresh:
            files.append(existing)
            reused += 1
            continue
        files.append(
            _scan_indexed_file(
                root,
                manifest,
                manifest_sha256=fingerprint,
                verified_at_utc=now,
            )
        )
        scanned += 1

    selected = tuple(sorted(files, key=lambda item: item.data_file))
    markets = _aggregate_markets(selected)
    event_counts_map: dict[str, int] = {}
    for item in selected:
        event_counts_map[item.event_type] = (
            event_counts_map.get(item.event_type, 0) + item.row_count
        )
    event_counts = tuple(sorted(event_counts_map.items()))
    manifest_digest = sha256()
    for item in selected:
        manifest_digest.update(f"{item.data_file}|{item.manifest_sha256}\n".encode())
    policy = research_policy or RawResearchReadinessPolicy()
    index = RawDataQualityIndex(
        generated_at_utc=now,
        storage_label=storage_label,
        manifest_set_sha256=manifest_digest.hexdigest(),
        measurement_status="VERIFIED_STORAGE" if selected else "INSUFFICIENT_SAMPLE",
        active_file_count=len(selected),
        active_row_count=sum(item.row_count for item in selected),
        active_byte_size=sum(item.byte_size for item in selected),
        verified_file_count=len(selected),
        scanned_file_count=scanned,
        reused_file_count=reused,
        retired_cache_entry_count=len(set(cached) - active_names),
        event_counts=event_counts,
        duplicate_message_count=sum(item.duplicate_message_count for item in selected),
        duplicate_event_identity_count=sum(
            item.duplicate_event_identity_count for item in selected
        ),
        received_time_regressions=sum(item.received_time_regressions for item in selected),
        local_sequence_regressions=sum(item.local_sequence_regressions for item in selected),
        quality_flagged_event_count=sum(item.quality_flagged_event_count for item in selected),
        files=selected,
        markets=markets,
        research_readiness=_research_readiness(markets, policy),
        limitation=(
            "Checksums, Parquet contracts, row counts, within-file identity uniqueness, and "
            "market availability are verified incrementally. Public exchange completeness and "
            "cross-file event identity uniqueness still require a bounded deterministic replay."
        ),
    )
    write_raw_data_quality_index(index, index_path)
    return index

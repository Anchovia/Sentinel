"""Secret-free, atomic runtime snapshots for later Work/Codex audits."""

import math
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.domain import TradeBar
from quantforge.features import FeatureSnapshot
from quantforge.replay import ReplayResult


class DataQualitySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    generated_at_utc: datetime
    data_schema_version: str = "raw-event-envelope-1"
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    total_inputs: int = Field(ge=0)
    delivered_events: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    out_of_order_count: int = Field(ge=0)
    reconnect_boundaries: int = Field(ge=0)
    parse_errors: int = Field(ge=0)
    checksum_failures: int = Field(ge=0)
    complete_bar_count: int = Field(ge=0)
    no_trade_bar_count: int = Field(ge=0)
    data_gap_bar_count: int = Field(ge=0)
    feature_snapshot_count: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0, le=1)
    feature_snapshot_hashes: tuple[str, ...]

    @field_validator("generated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("snapshot timestamp must be UTC-aware")
        return value

    @field_validator("coverage_ratio")
    @classmethod
    def require_finite_ratio(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("coverage ratio must be finite")
        return value

    @classmethod
    def from_phase2(
        cls,
        replay: ReplayResult,
        bars: list[TradeBar],
        features: list[FeatureSnapshot],
        *,
        parse_errors: int = 0,
        checksum_failures: int = 0,
        generated_at_utc: datetime | None = None,
    ) -> "DataQualitySnapshot":
        complete = sum(bar.is_complete for bar in bars)
        return cls(
            generated_at_utc=generated_at_utc or datetime.now(UTC),
            dataset_hash=replay.dataset_hash,
            total_inputs=replay.total_inputs,
            delivered_events=replay.delivered_events,
            gap_count=replay.delivered_gaps,
            duplicate_count=replay.skipped_duplicates,
            out_of_order_count=replay.out_of_order_events,
            reconnect_boundaries=replay.reconnect_boundaries,
            parse_errors=parse_errors,
            checksum_failures=checksum_failures,
            complete_bar_count=complete,
            no_trade_bar_count=sum(bar.no_trade for bar in bars),
            data_gap_bar_count=sum(bar.data_gap for bar in bars),
            feature_snapshot_count=len(features),
            coverage_ratio=complete / len(bars) if bars else 0.0,
            feature_snapshot_hashes=tuple(feature.snapshot_hash for feature in features),
        )


def write_data_quality_snapshot(snapshot: DataQualitySnapshot, output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / "latest.json"
    temporary = output_root / f".latest.{uuid4().hex}.tmp"
    payload = (
        orjson.dumps(
            snapshot.model_dump(mode="json"),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination

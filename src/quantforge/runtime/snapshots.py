"""Secret-free, atomic runtime snapshots for later Work/Codex audits."""

import math
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.domain import TradeBar
from quantforge.features import FeatureSnapshot
from quantforge.operations.exports import assert_runtime_export_safe
from quantforge.replay import ReplayResult
from quantforge.storage import RawDataQualityIndex


class DataQualityMarketCoverage(BaseModel):
    """Compact detailed-stream availability for research readiness reviews."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    trade_events: int = Field(ge=0)
    orderbook_events: int = Field(ge=0)
    detailed_span_seconds: float = Field(ge=0)


class DataQualitySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1, 2, 3] = 3
    generated_at_utc: datetime
    source_kind: Literal[
        "deterministic_replay",
        "public_paper_runtime",
        "public_paper_runtime_with_verified_storage",
    ] = "deterministic_replay"
    measurement_status: Literal[
        "COMPLETE", "VERIFIED_STORAGE", "PARTIAL", "INSUFFICIENT_SAMPLE"
    ] = "COMPLETE"
    data_schema_version: str = "raw-event-envelope-1"
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    dataset_hash_scope: Literal[
        "verified_replay", "live_counter_snapshot", "verified_incremental_index"
    ] = "verified_replay"
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
    monitored_market_count: int = Field(default=0, ge=0)
    observed_market_count: int = Field(default=0, ge=0)
    last_event_at_utc: datetime | None = None
    event_counts: tuple[tuple[str, int], ...] = ()
    storage_queue_depth: int = Field(default=0, ge=0)
    storage_queue_overflows: int = Field(default=0, ge=0)
    processing_budget_breaches: int = Field(default=0, ge=0)
    gap_measurement_supported: bool = True
    checksum_measurement_supported: bool = True
    indexed_file_count: int = Field(default=0, ge=0)
    indexed_event_count: int = Field(default=0, ge=0)
    indexed_byte_size: int = Field(default=0, ge=0)
    verified_manifest_count: int = Field(default=0, ge=0)
    duplicate_event_identity_count: int = Field(default=0, ge=0)
    local_sequence_regressions: int = Field(default=0, ge=0)
    quality_flagged_event_count: int = Field(default=0, ge=0)
    research_policy_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    research_eligible_markets: tuple[str, ...] = ()
    ready_for_new_preregistration: bool = False
    current_experiment_authorized: Literal[False] = False
    market_coverage: tuple[DataQualityMarketCoverage, ...] = ()
    limitation: str | None = None

    @field_validator("generated_at_utc", "last_event_at_utc")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
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

    @classmethod
    def from_live_runtime(
        cls,
        *,
        generated_at_utc: datetime,
        run_id: str,
        policy_hash: str,
        accepted_messages: int,
        processed_events: int,
        event_counts: tuple[tuple[str, int], ...],
        duplicate_count: int,
        reconnects: int,
        parse_errors: int,
        feature_frames: int,
        inference_ready_frames: int,
        monitored_market_count: int,
        observed_market_count: int,
        last_event_at_utc: datetime | None,
        storage_queue_depth: int,
        storage_queue_overflows: int,
        processing_budget_breaches: int,
        raw_quality_index: RawDataQualityIndex | None = None,
    ) -> "DataQualitySnapshot":
        values = {
            "accepted_messages": accepted_messages,
            "event_counts": event_counts,
            "generated_at_utc": generated_at_utc.isoformat(),
            "last_event_at_utc": (
                last_event_at_utc.isoformat() if last_event_at_utc is not None else None
            ),
            "policy_hash": policy_hash,
            "processed_events": processed_events,
            "run_id": run_id,
        }
        live_dataset_hash = sha256(orjson.dumps(values, option=orjson.OPT_SORT_KEYS)).hexdigest()
        coverage = inference_ready_frames / feature_frames if feature_frames else 0.0
        status = "PARTIAL" if processed_events else "INSUFFICIENT_SAMPLE"
        if raw_quality_index is not None and raw_quality_index.active_file_count:
            readiness = raw_quality_index.research_readiness
            detailed_coverage = tuple(
                DataQualityMarketCoverage(
                    market=item.market,
                    trade_events=item.trade_events,
                    orderbook_events=item.orderbook_events,
                    detailed_span_seconds=item.detailed_span_seconds,
                )
                for item in raw_quality_index.markets
                if item.trade_events or item.orderbook_events
            )
            return cls(
                source_kind="public_paper_runtime_with_verified_storage",
                measurement_status="VERIFIED_STORAGE",
                generated_at_utc=generated_at_utc,
                dataset_hash=raw_quality_index.manifest_set_sha256,
                dataset_hash_scope="verified_incremental_index",
                total_inputs=raw_quality_index.active_row_count,
                delivered_events=max(
                    0,
                    raw_quality_index.active_row_count - raw_quality_index.duplicate_message_count,
                ),
                gap_count=0,
                duplicate_count=raw_quality_index.duplicate_message_count,
                out_of_order_count=raw_quality_index.received_time_regressions,
                reconnect_boundaries=reconnects,
                parse_errors=parse_errors,
                checksum_failures=raw_quality_index.checksum_failures,
                complete_bar_count=0,
                no_trade_bar_count=0,
                data_gap_bar_count=0,
                feature_snapshot_count=feature_frames,
                coverage_ratio=coverage,
                feature_snapshot_hashes=(),
                monitored_market_count=monitored_market_count,
                observed_market_count=len(raw_quality_index.markets),
                last_event_at_utc=last_event_at_utc,
                event_counts=raw_quality_index.event_counts,
                storage_queue_depth=storage_queue_depth,
                storage_queue_overflows=storage_queue_overflows,
                processing_budget_breaches=processing_budget_breaches,
                gap_measurement_supported=False,
                checksum_measurement_supported=True,
                indexed_file_count=raw_quality_index.active_file_count,
                indexed_event_count=raw_quality_index.active_row_count,
                indexed_byte_size=raw_quality_index.active_byte_size,
                verified_manifest_count=raw_quality_index.verified_file_count,
                duplicate_event_identity_count=(raw_quality_index.duplicate_event_identity_count),
                local_sequence_regressions=raw_quality_index.local_sequence_regressions,
                quality_flagged_event_count=raw_quality_index.quality_flagged_event_count,
                research_policy_sha256=readiness.policy_sha256,
                research_eligible_markets=readiness.eligible_markets,
                ready_for_new_preregistration=readiness.ready_for_new_preregistration,
                market_coverage=detailed_coverage,
                limitation=raw_quality_index.limitation,
            )
        return cls(
            source_kind="public_paper_runtime",
            measurement_status=status,
            generated_at_utc=generated_at_utc,
            dataset_hash=live_dataset_hash,
            dataset_hash_scope="live_counter_snapshot",
            total_inputs=accepted_messages,
            delivered_events=processed_events,
            gap_count=0,
            duplicate_count=duplicate_count,
            out_of_order_count=0,
            reconnect_boundaries=reconnects,
            parse_errors=parse_errors,
            checksum_failures=0,
            complete_bar_count=0,
            no_trade_bar_count=0,
            data_gap_bar_count=0,
            feature_snapshot_count=feature_frames,
            coverage_ratio=coverage,
            feature_snapshot_hashes=(),
            monitored_market_count=monitored_market_count,
            observed_market_count=observed_market_count,
            last_event_at_utc=last_event_at_utc,
            event_counts=event_counts,
            storage_queue_depth=storage_queue_depth,
            storage_queue_overflows=storage_queue_overflows,
            processing_budget_breaches=processing_budget_breaches,
            gap_measurement_supported=False,
            checksum_measurement_supported=False,
            limitation=(
                "Live counters are fresh but do not replace deterministic gap and checksum replay."
            ),
        )


def write_data_quality_snapshot(snapshot: DataQualitySnapshot, output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / "latest.json"
    temporary = output_root / f".latest.{uuid4().hex}.tmp"
    values = snapshot.model_dump(mode="json")
    assert_runtime_export_safe(values)
    payload = (
        orjson.dumps(
            values,
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

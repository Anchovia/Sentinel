"""Bounded, Secret-free audit exports for report-only Work reviews."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.operations.exports import assert_runtime_export_safe
from quantforge.runtime.snapshots import DataQualitySnapshot


class AuditEvidenceState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AuditExportModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AuditSafety(AuditExportModel):
    authentication_used: Literal[False] = False
    private_network_used: Literal[False] = False
    real_order_submission_available: Literal[False] = False
    live_submission_allowed: Literal[False] = False


class WorkOperationsSnapshot(AuditExportModel):
    schema_version: Literal["work-ops-1", "work-ops-2", "work-ops-3"] = "work-ops-3"
    generated_at_utc: datetime
    source_run_id: UUID
    source_started_at_utc: datetime
    source_updated_at_utc: datetime
    runtime_state: str
    trading_mode: Literal["paper"] = "paper"
    code_version: str
    market_scope: str
    monitored_market_count: int = Field(ge=1)
    focused_market_count: int = Field(ge=1)
    warning_market_count: int = Field(ge=0)
    caution_market_count: int = Field(ge=0)
    public_websocket_state: str
    private_websocket_state: AuditEvidenceState = AuditEvidenceState.NOT_CONFIGURED
    last_event_at_utc: datetime | None = None
    market_event_age_seconds: float | None = Field(default=None, ge=0)
    accepted_messages: int = Field(ge=0)
    event_counts: tuple[tuple[str, int], ...]
    duplicate_messages: int = Field(ge=0)
    parser_errors: int = Field(ge=0)
    reconnects: int = Field(ge=0)
    storage_queue_depth: int = Field(ge=0)
    storage_queue_capacity: int = Field(ge=0)
    storage_queue_overflows: int = Field(ge=0)
    max_ingress_latency_ms: float | None = Field(default=None, ge=0)
    latest_ingress_latency_ms: float | None = None
    latest_exchange_clock_ahead_ms: float | None = Field(default=None, ge=0)
    feature_latency_p99_ms: float = Field(ge=0)
    decision_latency_p99_ms: float = Field(ge=0)
    rest_api_state: AuditEvidenceState = AuditEvidenceState.NOT_APPLICABLE
    rate_limit_state: AuditEvidenceState = AuditEvidenceState.NOT_APPLICABLE
    order_reconciliation_state: AuditEvidenceState = AuditEvidenceState.NOT_CONFIGURED
    incident_source_state: AuditEvidenceState = AuditEvidenceState.NOT_CONFIGURED
    database_state: AuditEvidenceState = AuditEvidenceState.NOT_CONFIGURED
    backup_state: AuditEvidenceState = AuditEvidenceState.NOT_CONFIGURED
    paper_orders: int = Field(ge=0)
    paper_fills: int = Field(ge=0)
    unknown_orders: int = Field(ge=0)
    ledger_records: int = Field(ge=0)
    recovery_status: str
    recovery_blocked: bool
    continuity_integrity: str = "NOT_CONFIGURED"
    continuity_measurement_started_at_utc: datetime | None = None
    current_session_uptime_seconds: float = Field(default=0, ge=0)
    previous_session_outcome: str = "UNKNOWN"
    last_shutdown_at_utc: datetime | None = None
    last_shutdown_reason: str | None = None
    unexpected_interruption_count: int = Field(default=0, ge=0)
    observed_websocket_gap_count: int = Field(default=0, ge=0)
    observed_stale_data_gap_count: int = Field(default=0, ge=0)
    current_gap_kind: str = "UNKNOWN"
    longest_current_session_gap_seconds: float = Field(default=0, ge=0)
    six_hour_baseline_ready: bool = False
    twelve_hour_baseline_ready: bool = False
    exchange_gap_completeness_claimed: Literal[False] = False
    gross_pnl_krw: Decimal
    net_pnl_krw: Decimal
    fees_krw: Decimal = Field(ge=0)
    spread_cost_krw: Decimal = Field(ge=0)
    slippage_cost_krw: Decimal = Field(ge=0)
    adverse_selection_cost_krw: Decimal = Field(ge=0)
    exposure_krw: Decimal = Field(ge=0)
    turnover_krw: Decimal = Field(ge=0)
    retained_files: int = Field(ge=0)
    retained_rows: int = Field(ge=0)
    retained_bytes: int = Field(ge=0)
    storage_retention_days: int = Field(ge=0)
    storage_max_bytes: int = Field(ge=0)
    storage_min_free_bytes: int = Field(ge=0)
    disk_free_bytes: int | None = Field(default=None, ge=0)
    storage_compaction_runs: int = Field(ge=0)
    storage_deleted_files: int = Field(ge=0)
    model_release_status: str
    model_approval_valid: bool
    safety: AuditSafety = AuditSafety()

    @field_validator(
        "generated_at_utc",
        "source_started_at_utc",
        "source_updated_at_utc",
        "last_event_at_utc",
        "continuity_measurement_started_at_utc",
        "last_shutdown_at_utc",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError("work operations timestamps must be UTC-aware")
        return value


class WorkIncidentSnapshot(AuditExportModel):
    schema_version: Literal["work-incidents-1"] = "work-incidents-1"
    generated_at_utc: datetime
    source_state: AuditEvidenceState
    complete: bool
    open_count: int = Field(ge=0)
    acknowledged_count: int = Field(ge=0)
    incidents: tuple[dict[str, object], ...] = ()
    limitation: str | None = None
    safety: AuditSafety = AuditSafety()

    @field_validator("generated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("work incident timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_completeness(self) -> "WorkIncidentSnapshot":
        if self.complete and self.source_state is not AuditEvidenceState.AVAILABLE:
            raise ValueError("complete incident evidence must be available")
        if not self.complete and not self.limitation:
            raise ValueError("incomplete incident evidence requires a limitation")
        return self


class WorkPerformanceSnapshot(AuditExportModel):
    schema_version: Literal["work-performance-1"] = "work-performance-1"
    generated_at_utc: datetime
    source_run_id: UUID
    window_started_at_utc: datetime
    sample_state: AuditEvidenceState
    representative: bool
    observed_market_count: int = Field(ge=0)
    paper_order_count: int = Field(ge=0)
    paper_fill_count: int = Field(ge=0)
    closed_trade_count: int | None = Field(default=None, ge=0)
    strategy_trade_proposals: int = Field(ge=0)
    risk_approvals: int = Field(ge=0)
    gross_pnl_krw: Decimal
    fees_krw: Decimal = Field(ge=0)
    spread_cost_krw: Decimal = Field(ge=0)
    slippage_cost_krw: Decimal = Field(ge=0)
    adverse_selection_cost_krw: Decimal = Field(ge=0)
    net_pnl_krw: Decimal
    turnover_krw: Decimal = Field(ge=0)
    exposure_krw: Decimal = Field(ge=0)
    win_rate: float | None = Field(default=None, ge=0, le=1)
    fill_ratio: float | None = Field(default=None, ge=0, le=1)
    maximum_drawdown_ratio: float | None = Field(default=None, ge=0)
    maker_taker_state: AuditEvidenceState = AuditEvidenceState.INSUFFICIENT_SAMPLE
    model_release_status: str
    model_approval_valid: bool
    paper_order_simulation_enabled: bool
    limitation: str
    safety: AuditSafety = AuditSafety()

    @field_validator("generated_at_utc", "window_started_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("work performance timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def prevent_unsupported_claims(self) -> "WorkPerformanceSnapshot":
        if self.representative and self.sample_state is not AuditEvidenceState.AVAILABLE:
            raise ValueError("representative performance requires available evidence")
        if not self.paper_fill_count and any(
            value is not None for value in (self.win_rate, self.fill_ratio)
        ):
            raise ValueError("empty paper performance cannot claim trade ratios")
        return self


class WorkModelSnapshot(AuditExportModel):
    schema_version: Literal["work-models-1"] = "work-models-1"
    generated_at_utc: datetime
    source_state: AuditEvidenceState
    active_approved_model_available: bool
    model_release_status: str
    model_approval_valid: bool
    active_artifacts: tuple[dict[str, object], ...] = ()
    observed_components: tuple[str, ...]
    inference_frames: int = Field(ge=0)
    inference_latency_p99_ms: float = Field(ge=0)
    feature_distribution_state: AuditEvidenceState
    prediction_distribution_state: AuditEvidenceState
    calibration_state: AuditEvidenceState
    drift_state: AuditEvidenceState
    drift_metrics: tuple[tuple[str, float], ...] = ()
    promotion_performed: Literal[False] = False
    limitation: str
    safety: AuditSafety = AuditSafety()

    @field_validator("generated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("work model timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def prevent_unapproved_active_model(self) -> "WorkModelSnapshot":
        if self.active_approved_model_available != self.model_approval_valid:
            raise ValueError("active model evidence and approval must agree")
        if not self.active_approved_model_available and self.active_artifacts:
            raise ValueError("unapproved runtime cannot export active artifacts")
        return self


class WorkAuditBaseline(AuditExportModel):
    schema_version: Literal["work-audit-baseline-1"] = "work-audit-baseline-1"
    generated_at_utc: datetime
    operations: WorkOperationsSnapshot
    data_quality: DataQualitySnapshot
    incidents: WorkIncidentSnapshot
    performance: WorkPerformanceSnapshot
    models: WorkModelSnapshot

    @field_validator("generated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("work baseline timestamp must be UTC-aware")
        return value


class WorkAuditExportWriter:
    """Write current inputs frequently and bounded immutable baselines periodically."""

    def __init__(
        self,
        output_root: Path,
        *,
        baseline_interval_seconds: int = 900,
        baseline_retention_days: int = 30,
        baseline_max_bytes: int = 100 * 1024**2,
    ) -> None:
        if (
            baseline_interval_seconds < 60
            or baseline_retention_days < 1
            or baseline_max_bytes < 1024
        ):
            raise ValueError("work audit baseline bounds are invalid")
        self.output_root = output_root
        self.baseline_interval = timedelta(seconds=baseline_interval_seconds)
        self.baseline_retention = timedelta(days=baseline_retention_days)
        self.baseline_max_bytes = baseline_max_bytes
        self._last_baseline_at_utc = self._find_latest_baseline_time()

    def write(self, baseline: WorkAuditBaseline) -> tuple[Path, ...]:
        latest = (
            ("ops/latest.json", baseline.operations),
            ("data_quality/latest.json", baseline.data_quality),
            ("incidents/open.json", baseline.incidents),
            ("performance/latest.json", baseline.performance),
            ("models/latest.json", baseline.models),
        )
        written = tuple(
            self._atomic_write(self.output_root / relative, model) for relative, model in latest
        )
        if self._baseline_due(baseline.generated_at_utc):
            history = self._baseline_path(baseline.generated_at_utc)
            self._atomic_write(history, baseline)
            self._last_baseline_at_utc = baseline.generated_at_utc
            self._maintain_history(baseline.generated_at_utc)
            return (*written, history)
        return written

    def _baseline_due(self, generated_at_utc: datetime) -> bool:
        return self._last_baseline_at_utc is None or (
            generated_at_utc - self._last_baseline_at_utc >= self.baseline_interval
        )

    def _baseline_path(self, generated_at_utc: datetime) -> Path:
        stamp = generated_at_utc.strftime("%Y%m%dT%H%M%S.%fZ")
        return (
            self.output_root
            / "baselines"
            / generated_at_utc.strftime("%Y")
            / generated_at_utc.strftime("%m")
            / generated_at_utc.strftime("%d")
            / f"{stamp}-audit-baseline.json"
        )

    def _find_latest_baseline_time(self) -> datetime | None:
        root = self.output_root / "baselines"
        latest: datetime | None = None
        for path in root.glob("**/*-audit-baseline.json") if root.exists() else ():
            try:
                stamp = path.name.removesuffix("-audit-baseline.json")
                parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=UTC)
            except ValueError:
                continue
            latest = parsed if latest is None or parsed > latest else latest
        return latest

    def _maintain_history(self, now_utc: datetime) -> None:
        root = self.output_root / "baselines"
        candidates: list[tuple[datetime, Path, int]] = []
        for path in root.glob("**/*-audit-baseline.json"):
            try:
                stamp = path.name.removesuffix("-audit-baseline.json")
                generated = datetime.strptime(stamp, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=UTC)
                size = path.stat().st_size
            except (OSError, ValueError):
                continue
            if now_utc - generated > self.baseline_retention:
                path.unlink(missing_ok=True)
                continue
            candidates.append((generated, path, size))
        total = sum(size for _, _, size in candidates)
        for _, path, size in sorted(candidates):
            if total <= self.baseline_max_bytes:
                break
            path.unlink(missing_ok=True)
            total -= size

    @staticmethod
    def _atomic_write(path: Path, model: BaseModel) -> Path:
        payload = model.model_dump(mode="json")
        assert_runtime_export_safe(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        encoded = (
            orjson.dumps(
                payload,
                option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
            )
            + b"\n"
        )
        try:
            temporary.write_bytes(encoded)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return path


def read_work_audit_baseline(path: Path) -> WorkAuditBaseline:
    payload = orjson.loads(path.read_bytes())
    assert_runtime_export_safe(payload)
    return WorkAuditBaseline.model_validate(payload)

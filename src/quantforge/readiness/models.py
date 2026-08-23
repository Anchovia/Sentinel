"""Versioned evidence, policy, and output contracts for manual canary review readiness."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("readiness timestamps must be UTC-aware")
    return value


class ReadinessModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReadinessStatus(StrEnum):
    NOT_READY = "NOT_READY"
    CONDITIONALLY_READY = "CONDITIONALLY_READY"
    READY_FOR_MANUAL_CANARY_REVIEW = "READY_FOR_MANUAL_CANARY_REVIEW"


class GateStatus(StrEnum):
    PASS = "PASS"  # noqa: S105 - evaluation status, not a credential
    CONDITIONAL = "CONDITIONAL"
    FAIL = "FAIL"


class GateName(StrEnum):
    PAPER_HISTORY = "paper_history"
    RECONCILIATION = "reconciliation"
    DATA_AVAILABILITY = "data_availability"
    INCIDENTS = "incidents"
    MODEL_STABILITY = "model_stability"
    DRAWDOWN_EXPECTANCY = "drawdown_expectancy"
    COST_MODEL = "cost_model"
    ORDER_TEST = "order_test"
    BACKUP_RESTORE = "backup_restore"
    SECURITY = "security"
    OPERATOR_RUNBOOK = "operator_runbook"
    LIVE_LOCKS = "live_locks"
    RELEASE_APPROVAL = "release_approval"


class EvidenceBase(ReadinessModel):
    observed_at_utc: datetime
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("observed_at_utc")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _require_utc(value)


class PaperHistoryEvidence(EvidenceBase):
    trading_mode: Literal["paper"] = "paper"
    actual_orders_executed: Literal[False] = False
    period_start_utc: datetime
    period_end_utc: datetime
    trade_count: Annotated[int, Field(ge=0)]
    observed_regimes: tuple[str, ...]

    @field_validator("period_start_utc", "period_end_utc")
    @classmethod
    def validate_period_time(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def validate_period(self) -> "PaperHistoryEvidence":
        if self.period_end_utc < self.period_start_utc:
            raise ValueError("paper period cannot end before it starts")
        if self.period_end_utc > self.observed_at_utc:
            raise ValueError("paper period cannot end after its observation")
        if len(self.observed_regimes) != len(set(self.observed_regimes)):
            raise ValueError("observed regimes must be unique")
        return self


class ReconciliationEvidence(EvidenceBase):
    window_days: Annotated[int, Field(ge=1)]
    successful_days: Annotated[int, Field(ge=0)]
    reconciliation_runs: Annotated[int, Field(ge=0)]
    mismatch_count: Annotated[int, Field(ge=0)]
    unknown_order_count: Annotated[int, Field(ge=0)]
    last_success_at_utc: datetime | None

    @field_validator("last_success_at_utc")
    @classmethod
    def validate_last_success(cls, value: datetime | None) -> datetime | None:
        return _require_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_counts(self) -> "ReconciliationEvidence":
        if self.successful_days > self.window_days:
            raise ValueError("successful reconciliation days cannot exceed the window")
        if self.successful_days > self.reconciliation_runs:
            raise ValueError("successful reconciliation days cannot exceed completed runs")
        if self.last_success_at_utc is not None and self.last_success_at_utc > self.observed_at_utc:
            raise ValueError("last reconciliation success cannot be in the future")
        return self


class DataAvailabilityEvidence(EvidenceBase):
    window_days: Annotated[int, Field(ge=1)]
    availability_ratio: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
    gap_count: Annotated[int, Field(ge=0)]
    checksum_failure_count: Annotated[int, Field(ge=0)]
    schema_compatible: bool
    freshest_event_at_utc: datetime | None

    @field_validator("freshest_event_at_utc")
    @classmethod
    def validate_freshest_event(cls, value: datetime | None) -> datetime | None:
        return _require_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_event_time(self) -> "DataAvailabilityEvidence":
        if self.freshest_event_at_utc is not None and (
            self.freshest_event_at_utc > self.observed_at_utc
        ):
            raise ValueError("freshest event cannot be later than its observation")
        return self


class IncidentEvidence(EvidenceBase):
    window_days: Annotated[int, Field(ge=1)]
    unresolved_critical: Annotated[int, Field(ge=0)]
    unresolved_high: Annotated[int, Field(ge=0)]
    critical_opened: Annotated[int, Field(ge=0)]
    high_opened: Annotated[int, Field(ge=0)]


class ModelStabilityEvidence(EvidenceBase):
    stability_days: Annotated[int, Field(ge=0)]
    calibration_error: Annotated[Decimal, Field(ge=Decimal("0"))]
    drift_score: Annotated[Decimal, Field(ge=Decimal("0"))]
    artifact_integrity_verified: bool
    active_artifact_hashes: tuple[str, ...] = Field(min_length=1)

    @field_validator("active_artifact_hashes")
    @classmethod
    def validate_artifact_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(
            len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
            for item in value
        ):
            raise ValueError("active artifact hashes must be unique lowercase SHA-256 values")
        return value


class PerformanceEvidence(EvidenceBase):
    paper_trade_count: Annotated[int, Field(ge=0)]
    maximum_drawdown_ratio: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
    cost_adjusted_expectancy_lower_bps: Decimal
    all_costs_included: bool


class CostModelEvidence(EvidenceBase):
    observation_count: Annotated[int, Field(ge=0)]
    mean_absolute_error_bps: Annotated[Decimal, Field(ge=Decimal("0"))]
    includes_fees: bool
    includes_spread: bool
    includes_slippage: bool
    includes_latency: bool
    includes_adverse_selection: bool


class OrderTestEvidence(EvidenceBase):
    endpoint_supported_by_manifest: bool
    dry_run_verified: bool
    completed_at_utc: datetime | None
    real_order_created: Literal[False] = False

    @field_validator("completed_at_utc")
    @classmethod
    def validate_completed_at(cls, value: datetime | None) -> datetime | None:
        return _require_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_completion_time(self) -> "OrderTestEvidence":
        if self.completed_at_utc is not None and self.completed_at_utc > self.observed_at_utc:
            raise ValueError("order-test completion cannot be later than its observation")
        return self


class BackupRestoreEvidence(EvidenceBase):
    restore_verified: bool
    checksum_verified: bool
    isolated_target: bool
    production_grade: bool
    encrypted: bool
    off_host: bool
    objectives_measured: bool
    tested_at_utc: datetime | None

    @field_validator("tested_at_utc")
    @classmethod
    def validate_tested_at(cls, value: datetime | None) -> datetime | None:
        return _require_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_test_time(self) -> "BackupRestoreEvidence":
        if self.tested_at_utc is not None and self.tested_at_utc > self.observed_at_utc:
            raise ValueError("restore test cannot be later than its observation")
        return self


class SecurityEvidence(EvidenceBase):
    audit_passed: bool
    high_or_critical_findings: Annotated[int, Field(ge=0)]
    secret_scan_passed: bool
    dependency_audit_passed: bool
    dashboard_auth_reviewed: bool
    network_policy_reviewed: bool
    withdrawal_permission_disabled: bool
    api_key_ip_allowlist_reviewed: bool
    live_gates_tested: bool
    completed_at_utc: datetime | None

    @field_validator("completed_at_utc")
    @classmethod
    def validate_completed_at(cls, value: datetime | None) -> datetime | None:
        return _require_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_completion_time(self) -> "SecurityEvidence":
        if self.completed_at_utc is not None and self.completed_at_utc > self.observed_at_utc:
            raise ValueError("security audit cannot be later than its observation")
        return self


class OperatorRunbookEvidence(EvidenceBase):
    verified: bool
    reviewed_operator_count: Annotated[int, Field(ge=0)]
    incident_drill_passed: bool
    cancel_only_drill_passed: bool
    reconciliation_drill_passed: bool
    recovery_drill_passed: bool
    completed_at_utc: datetime | None

    @field_validator("completed_at_utc")
    @classmethod
    def validate_completed_at(cls, value: datetime | None) -> datetime | None:
        return _require_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_completion_time(self) -> "OperatorRunbookEvidence":
        if self.completed_at_utc is not None and self.completed_at_utc > self.observed_at_utc:
            raise ValueError("runbook review cannot be later than its observation")
        return self


class LiveLockEvidence(EvidenceBase):
    default_mode_paper: bool
    order_submission_default_false: bool
    six_gate_guard_verified: bool
    single_flag_cannot_enable_live: bool
    operator_unlock_absent: bool
    live_adapter_implemented_and_reviewed: bool
    order_network_allowlist_reviewed: bool
    validator_has_order_capability: Literal[False] = False
    runtime_settings_changed: Literal[False] = False


class CanaryPlanEvidence(ReadinessModel):
    markets: tuple[str, ...] = Field(min_length=1)
    maximum_order_notional_krw: Annotated[Decimal, Field(gt=Decimal("0"))]
    maximum_total_exposure_krw: Annotated[Decimal, Field(gt=Decimal("0"))]
    maximum_duration_minutes: Annotated[int, Field(gt=0)]
    manual_monitoring: Literal[True] = True
    cancel_only_verified: Literal[True] = True
    post_canary_reconciliation_required: Literal[True] = True
    automatic_code_or_model_change: Literal[False] = False

    @field_validator("markets")
    @classmethod
    def validate_markets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(
            not item.startswith("KRW-")
            or not item.removeprefix("KRW-").isascii()
            or not item.removeprefix("KRW-").isalnum()
            or item != item.upper()
            for item in value
        ):
            raise ValueError("canary markets must be unique KRW spot market codes")
        return value


class ReleaseApprovalEvidence(EvidenceBase):
    release_manifest_approval_id: str = Field(min_length=1, max_length=100)
    risk_policy_approval_id: str = Field(min_length=1, max_length=100)
    model_release_approval_id: str = Field(min_length=1, max_length=100)
    operator_canary_review_id: str = Field(min_length=1, max_length=100)
    approved_code_revision: str = Field(pattern=r"^[a-f0-9]{7,64}$")
    approved_model_hashes: tuple[str, ...] = Field(min_length=1)
    canary_plan: CanaryPlanEvidence

    @field_validator("approved_model_hashes")
    @classmethod
    def validate_model_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(
            len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
            for item in value
        ):
            raise ValueError("approved model hashes must be unique lowercase SHA-256 values")
        return value

    @model_validator(mode="after")
    def require_independent_approvals(self) -> "ReleaseApprovalEvidence":
        approvals = (
            self.release_manifest_approval_id,
            self.risk_policy_approval_id,
            self.model_release_approval_id,
            self.operator_canary_review_id,
        )
        if len(set(approvals)) != len(approvals):
            raise ValueError("release, risk, model, and operator approvals must be distinct")
        return self


class ReadinessEvidence(ReadinessModel):
    schema_version: Literal["readiness-evidence-1"] = "readiness-evidence-1"
    evidence_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    generated_at_utc: datetime
    source_revision: str = Field(pattern=r"^[a-f0-9]{7,64}$")
    paper_history: PaperHistoryEvidence | None = None
    reconciliation: ReconciliationEvidence | None = None
    data_availability: DataAvailabilityEvidence | None = None
    incidents: IncidentEvidence | None = None
    model_stability: ModelStabilityEvidence | None = None
    performance: PerformanceEvidence | None = None
    cost_model: CostModelEvidence | None = None
    order_test: OrderTestEvidence | None = None
    backup_restore: BackupRestoreEvidence | None = None
    security: SecurityEvidence | None = None
    operator_runbook: OperatorRunbookEvidence | None = None
    live_locks: LiveLockEvidence | None = None
    release_approval: ReleaseApprovalEvidence | None = None

    @field_validator("generated_at_utc")
    @classmethod
    def validate_generated_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def validate_cross_contracts(self) -> "ReadinessEvidence":
        if (
            self.paper_history is not None
            and self.performance is not None
            and self.paper_history.trade_count != self.performance.paper_trade_count
        ):
            raise ValueError("paper and performance trade counts must match")
        if self.release_approval is not None:
            if self.release_approval.approved_code_revision != self.source_revision:
                raise ValueError("release approval must bind the evidence source revision")
            if (
                self.model_stability is not None
                and self.release_approval.approved_model_hashes
                != self.model_stability.active_artifact_hashes
            ):
                raise ValueError("release approval must bind every active model artifact")
        return self


class ReadinessPolicy(ReadinessModel):
    schema_version: Literal["readiness-policy-1"] = "readiness-policy-1"
    policy_version: str = Field(min_length=1, max_length=100)
    hard_minimum_paper_days: Annotated[int, Field(ge=1)]
    preferred_minimum_paper_days: Annotated[int, Field(ge=1)]
    hard_minimum_paper_trades: Annotated[int, Field(ge=1)]
    preferred_minimum_paper_trades: Annotated[int, Field(ge=1)]
    hard_minimum_regime_count: Annotated[int, Field(ge=1)]
    preferred_minimum_regime_count: Annotated[int, Field(ge=1)]
    hard_minimum_reconciliation_days: Annotated[int, Field(ge=1)]
    preferred_minimum_reconciliation_days: Annotated[int, Field(ge=1)]
    hard_minimum_data_availability_ratio: Annotated[
        Decimal, Field(ge=Decimal("0"), le=Decimal("1"))
    ]
    preferred_minimum_data_availability_ratio: Annotated[
        Decimal, Field(ge=Decimal("0"), le=Decimal("1"))
    ]
    maximum_unresolved_high_incidents: Annotated[int, Field(ge=0)]
    preferred_unresolved_high_incidents: Annotated[int, Field(ge=0)]
    hard_maximum_high_incidents_per_30_days: Annotated[Decimal, Field(ge=Decimal("0"))]
    preferred_maximum_high_incidents_per_30_days: Annotated[Decimal, Field(ge=Decimal("0"))]
    maximum_critical_incidents_in_window: Annotated[int, Field(ge=0)]
    preferred_critical_incidents_in_window: Annotated[int, Field(ge=0)]
    hard_minimum_model_stability_days: Annotated[int, Field(ge=1)]
    preferred_minimum_model_stability_days: Annotated[int, Field(ge=1)]
    hard_maximum_calibration_error: Annotated[Decimal, Field(ge=Decimal("0"))]
    preferred_maximum_calibration_error: Annotated[Decimal, Field(ge=Decimal("0"))]
    hard_maximum_model_drift_score: Annotated[Decimal, Field(ge=Decimal("0"))]
    preferred_maximum_model_drift_score: Annotated[Decimal, Field(ge=Decimal("0"))]
    hard_maximum_drawdown_ratio: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
    preferred_maximum_drawdown_ratio: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
    hard_minimum_expectancy_lower_bps: Decimal
    preferred_minimum_expectancy_lower_bps: Decimal
    hard_minimum_cost_observations: Annotated[int, Field(ge=1)]
    preferred_minimum_cost_observations: Annotated[int, Field(ge=1)]
    hard_maximum_cost_error_bps: Annotated[Decimal, Field(ge=Decimal("0"))]
    preferred_maximum_cost_error_bps: Annotated[Decimal, Field(ge=Decimal("0"))]
    maximum_evidence_age_hours: Annotated[int, Field(ge=1)]
    maximum_order_test_age_days: Annotated[int, Field(ge=1)]
    maximum_restore_age_days: Annotated[int, Field(ge=1)]
    maximum_security_audit_age_days: Annotated[int, Field(ge=1)]
    maximum_runbook_review_age_days: Annotated[int, Field(ge=1)]
    maximum_data_event_age_seconds: Annotated[int, Field(ge=1)]
    minimum_reviewed_operators: Annotated[int, Field(ge=1)]
    maximum_canary_markets: Annotated[int, Field(ge=1)]
    maximum_canary_order_notional_krw: Annotated[Decimal, Field(gt=Decimal("0"))]
    maximum_canary_total_exposure_krw: Annotated[Decimal, Field(gt=Decimal("0"))]
    maximum_canary_duration_minutes: Annotated[int, Field(ge=1)]
    maximum_future_skew_seconds: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def require_preferred_thresholds_to_be_stricter(self) -> "ReadinessPolicy":
        minimum_pairs = (
            (self.hard_minimum_paper_days, self.preferred_minimum_paper_days),
            (self.hard_minimum_paper_trades, self.preferred_minimum_paper_trades),
            (self.hard_minimum_regime_count, self.preferred_minimum_regime_count),
            (
                self.hard_minimum_reconciliation_days,
                self.preferred_minimum_reconciliation_days,
            ),
            (
                self.hard_minimum_data_availability_ratio,
                self.preferred_minimum_data_availability_ratio,
            ),
            (
                self.hard_minimum_model_stability_days,
                self.preferred_minimum_model_stability_days,
            ),
            (
                self.hard_minimum_expectancy_lower_bps,
                self.preferred_minimum_expectancy_lower_bps,
            ),
            (self.hard_minimum_cost_observations, self.preferred_minimum_cost_observations),
        )
        maximum_pairs = (
            (
                self.maximum_unresolved_high_incidents,
                self.preferred_unresolved_high_incidents,
            ),
            (
                self.maximum_critical_incidents_in_window,
                self.preferred_critical_incidents_in_window,
            ),
            (
                self.hard_maximum_high_incidents_per_30_days,
                self.preferred_maximum_high_incidents_per_30_days,
            ),
            (self.hard_maximum_calibration_error, self.preferred_maximum_calibration_error),
            (self.hard_maximum_model_drift_score, self.preferred_maximum_model_drift_score),
            (self.hard_maximum_drawdown_ratio, self.preferred_maximum_drawdown_ratio),
            (self.hard_maximum_cost_error_bps, self.preferred_maximum_cost_error_bps),
        )
        if any(preferred < hard for hard, preferred in minimum_pairs):
            raise ValueError("preferred minimum thresholds cannot be weaker than hard minimums")
        if any(preferred > hard for hard, preferred in maximum_pairs):
            raise ValueError("preferred maximum thresholds cannot be weaker than hard maximums")
        return self


class GateEvaluation(ReadinessModel):
    gate: GateName
    status: GateStatus
    observed: tuple[tuple[str, str], ...]
    required: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]


class ReadinessSafety(ReadinessModel):
    real_orders_executed: Literal[False] = False
    order_network_used: Literal[False] = False
    production_secrets_accessed: Literal[False] = False
    runtime_settings_changed: Literal[False] = False
    live_mode_activated: Literal[False] = False
    risk_limits_changed: Literal[False] = False
    model_promoted: Literal[False] = False
    deployment_performed: Literal[False] = False


class ReadinessReport(ReadinessModel):
    schema_version: Literal["readiness-report-1"] = "readiness-report-1"
    evaluated_at_utc: datetime
    evidence_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    source_revision: str = Field(pattern=r"^[a-f0-9]{7,64}$")
    policy_version: str = Field(min_length=1, max_length=100)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ReadinessStatus
    gates: tuple[GateEvaluation, ...]
    human_approval_required: Literal[True] = True
    activation_performed: Literal[False] = False
    safety: ReadinessSafety = ReadinessSafety()

    @field_validator("evaluated_at_utc")
    @classmethod
    def validate_evaluated_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def validate_status_matches_gates(self) -> "ReadinessReport":
        statuses = tuple(gate.status for gate in self.gates)
        if len(self.gates) != len(GateName) or {gate.gate for gate in self.gates} != set(GateName):
            raise ValueError("readiness report must contain every gate exactly once")
        expected = (
            ReadinessStatus.NOT_READY
            if GateStatus.FAIL in statuses
            else ReadinessStatus.CONDITIONALLY_READY
            if GateStatus.CONDITIONAL in statuses
            else ReadinessStatus.READY_FOR_MANUAL_CANARY_REVIEW
        )
        if self.status is not expected:
            raise ValueError("readiness status must be derived from gate results")
        return self

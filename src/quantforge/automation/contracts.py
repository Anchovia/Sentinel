"""Versioned, Secret-free automation reports and Work-to-Codex triggers."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.operations.exports import assert_runtime_export_safe


class AutomationActor(StrEnum):
    WORK = "work"
    CODEX = "codex"


class AutomationSeverity(StrEnum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AutomationOutcome(StrEnum):
    NO_ACTION = "NO_ACTION"
    REPORT_ONLY = "REPORT_ONLY"
    CHANGE_CANDIDATE = "CHANGE_CANDIDATE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class SkillName(StrEnum):
    OPS_AUDIT = "quantforge-ops-audit"
    PERFORMANCE_REVIEW = "quantforge-performance-review"
    DATA_QUALITY = "quantforge-data-quality"
    MODEL_DRIFT = "quantforge-model-drift"
    INCIDENT_TRIAGE = "quantforge-incident-triage"
    CODE_AUDIT = "quantforge-code-audit"
    STRATEGY_RESEARCH = "quantforge-strategy-research"
    DEPENDENCY_REVIEW = "quantforge-dependency-review"
    DISASTER_RECOVERY = "quantforge-disaster-recovery"


WORK_SKILLS = frozenset(
    {
        SkillName.OPS_AUDIT,
        SkillName.PERFORMANCE_REVIEW,
        SkillName.DATA_QUALITY,
        SkillName.MODEL_DRIFT,
        SkillName.STRATEGY_RESEARCH,
    }
)
CODEX_SKILLS = frozenset(
    {
        SkillName.INCIDENT_TRIAGE,
        SkillName.CODE_AUDIT,
        SkillName.STRATEGY_RESEARCH,
        SkillName.DEPENDENCY_REVIEW,
        SkillName.DISASTER_RECOVERY,
    }
)


def _validate_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or normalized.startswith("/"):
        raise ValueError("path must be repository-relative")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("path traversal and ambiguous path components are forbidden")
    if ":" in path.parts[0] or "\x00" in normalized:
        raise ValueError("drive-qualified and NUL-containing paths are forbidden")
    return path.as_posix()


class AutomationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EvidenceRecord(AutomationModel):
    evidence_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    source_path: str
    source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    observation: str = Field(min_length=1, max_length=1000)

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, value: str) -> str:
        return _validate_relative_path(value)


class AutomationSafety(AutomationModel):
    real_orders_executed: Literal[False] = False
    order_network_used: Literal[False] = False
    production_secrets_accessed: Literal[False] = False
    live_mode_changed: Literal[False] = False
    risk_limits_changed: Literal[False] = False
    model_promoted: Literal[False] = False
    auto_merge_performed: Literal[False] = False
    auto_deploy_performed: Literal[False] = False


class WorktreeProof(AutomationModel):
    dedicated_worktree: Literal[True] = True
    main_checkout_modified: Literal[False] = False
    base_branch: Literal["main"] = "main"
    base_revision: str = Field(pattern=r"^[a-f0-9]{7,64}$")
    candidate_branch: str | None = Field(default=None, max_length=200)

    @field_validator("candidate_branch")
    @classmethod
    def reject_main_candidate(cls, value: str | None) -> str | None:
        if value in {"main", "refs/heads/main"}:
            raise ValueError("a change candidate cannot use the main branch")
        return value


class AutomationReport(AutomationModel):
    schema_version: Literal["automation-report-1"] = "automation-report-1"
    run_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    task_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9.-]+$")
    actor: AutomationActor
    skill: SkillName
    started_at_utc: datetime
    completed_at_utc: datetime
    source_revision: str = Field(pattern=r"^[a-f0-9]{7,64}$")
    severity: AutomationSeverity
    outcome: AutomationOutcome
    summary: str = Field(min_length=1, max_length=1000)
    report_path: str
    writes: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[EvidenceRecord, ...] = ()
    validation: tuple[str, ...] = ()
    requires_operator: bool = False
    requires_codex: bool = False
    first_three_runs_review: bool = True
    worktree: WorktreeProof | None = None
    safety: AutomationSafety = AutomationSafety()

    @field_validator("started_at_utc", "completed_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("automation timestamps must be UTC-aware")
        return value

    @field_validator("report_path")
    @classmethod
    def validate_report_path(cls, value: str) -> str:
        return _validate_relative_path(value)

    @field_validator("writes")
    @classmethod
    def validate_writes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_validate_relative_path(item) for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("write paths must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_actor_boundary(self) -> "AutomationReport":
        if self.completed_at_utc < self.started_at_utc:
            raise ValueError("automation run cannot complete before it starts")
        if self.report_path not in self.writes:
            raise ValueError("report_path must be included in writes")
        if (
            self.outcome is AutomationOutcome.NO_ACTION
            and self.severity is not AutomationSeverity.NORMAL
        ):
            raise ValueError("NO_ACTION is reserved for a NORMAL no-op result")
        if self.actor is AutomationActor.WORK:
            if self.skill not in WORK_SKILLS:
                raise ValueError("selected skill is not available to Work")
            if not self.report_path.startswith("reports/work/"):
                raise ValueError("Work reports must stay under reports/work")
            if self.outcome is AutomationOutcome.CHANGE_CANDIDATE:
                raise ValueError("Work cannot produce source change candidates")
            if self.worktree is not None:
                raise ValueError("Work report jobs do not claim a Codex worktree")
        else:
            if self.skill not in CODEX_SKILLS:
                raise ValueError("selected skill is not available to Codex")
            if not self.report_path.startswith("reports/codex/"):
                raise ValueError("Codex reports must stay under reports/codex")
            if self.worktree is None:
                raise ValueError("Codex scheduled work requires a dedicated worktree proof")
            if self.outcome is AutomationOutcome.CHANGE_CANDIDATE:
                if self.worktree.candidate_branch is None:
                    raise ValueError("a change candidate requires a non-main candidate branch")
                if not self.evidence or not self.validation:
                    raise ValueError("a change candidate requires evidence and validation")
        return self


class TriggerClass(StrEnum):
    INCIDENT = "incident"
    CODE_DEFECT = "code_defect"
    RESEARCH_HYPOTHESIS = "research_hypothesis"
    DEPENDENCY_SECURITY = "dependency_security"
    DISASTER_RECOVERY = "disaster_recovery"


class Reproducibility(StrEnum):
    REPRODUCED = "reproduced"
    EVIDENCE_AVAILABLE = "evidence_available"
    INSUFFICIENT = "insufficient"


class AutomationTrigger(AutomationModel):
    schema_version: Literal["automation-trigger-1"] = "automation-trigger-1"
    trigger_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    origin_report: str
    created_at_utc: datetime
    severity: AutomationSeverity
    trigger_class: TriggerClass
    requested_skill: SkillName
    reproducibility: Reproducibility
    evidence: tuple[EvidenceRecord, ...] = Field(min_length=1)
    requested_write_paths: tuple[str, ...]
    requires_codex: Literal[True] = True
    operator_approval_required: Literal[True] = True

    @field_validator("created_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("trigger timestamp must be UTC-aware")
        return value

    @field_validator("origin_report")
    @classmethod
    def validate_origin_report(cls, value: str) -> str:
        normalized = _validate_relative_path(value)
        if not normalized.startswith("reports/work/"):
            raise ValueError("Codex triggers must originate from a Work report")
        return normalized

    @field_validator("requested_write_paths")
    @classmethod
    def validate_requested_writes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validate_relative_path(item) for item in value)

    @model_validator(mode="after")
    def require_codex_skill(self) -> "AutomationTrigger":
        if self.requested_skill not in CODEX_SKILLS:
            raise ValueError("trigger must request a Codex-capable skill")
        return self


def _load_safe_json(path: Path) -> object:
    payload: object = orjson.loads(path.read_bytes())
    assert_runtime_export_safe(payload)
    return payload


def load_report(path: Path) -> AutomationReport:
    return AutomationReport.model_validate(_load_safe_json(path))


def load_trigger(path: Path) -> AutomationTrigger:
    return AutomationTrigger.model_validate(_load_safe_json(path))

"""Pre-registered experiment and trial ledger with immutable negative results."""

import math
import os
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import deterministic_execution_id
from quantforge.portfolio.ledger import ZERO_HASH
from quantforge.research.splits import SplitRole


class ExperimentLedgerError(ValueError):
    """Raised before research state could violate preregistration rules."""


class ExperimentStatus(StrEnum):
    PREREGISTERED = "preregistered"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    HELD = "held"


class TrialStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExperimentDecision(StrEnum):
    ACCEPT_FOR_FURTHER_RESEARCH = "accept_for_further_research"
    REJECT = "reject"
    HOLD = "hold"


class ExperimentRecordType(StrEnum):
    REGISTRATION = "registration"
    TRIAL = "trial"
    HOLDOUT_ACCESS = "holdout_access"
    DECISION = "decision"


class ExperimentRegistration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: UUID
    hypothesis_id: str = Field(min_length=1)
    created_at_utc: datetime
    researcher: str = Field(min_length=1)
    code_version: str = Field(min_length=1)
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    feature_set: str = Field(min_length=1)
    label_version: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    hyperparameter_space: tuple[tuple[str, tuple[str, ...]], ...]
    planned_metrics: tuple[str, ...] = Field(min_length=1)
    planned_splits: tuple[SplitRole, ...] = Field(min_length=1)
    planned_cost_model: str = Field(min_length=1)
    final_holdout_planned: bool = False
    status: ExperimentStatus = ExperimentStatus.PREREGISTERED

    @field_validator("created_at_utc")
    @classmethod
    def require_created_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("experiment timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_registration(self) -> "ExperimentRegistration":
        names = tuple(name for name, _ in self.hyperparameter_space)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("hyperparameter space must have sorted unique names")
        if any(not values for _, values in self.hyperparameter_space):
            raise ValueError("hyperparameter candidates cannot be empty")
        if len(self.planned_metrics) != len(set(self.planned_metrics)):
            raise ValueError("planned metrics must be unique")
        if len(self.planned_splits) != len(set(self.planned_splits)):
            raise ValueError("planned splits must be unique")
        if SplitRole.FINAL_HOLDOUT in self.planned_splits and not self.final_holdout_planned:
            raise ValueError("final holdout split requires explicit preregistration")
        if self.status is not ExperimentStatus.PREREGISTERED:
            raise ValueError("new experiments must start preregistered")
        return self

    @property
    def digest(self) -> str:
        return _model_digest(self)


class TrialResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trial_id: UUID
    experiment_id: UUID
    started_at_utc: datetime
    ended_at_utc: datetime
    random_seed: int
    split_role: SplitRole
    split_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hyperparameters: tuple[tuple[str, str], ...]
    metrics: tuple[tuple[str, float], ...] = ()
    status: TrialStatus
    failure_reason: str | None = None
    artifact_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    holdout_used: bool = False
    approved_review_id: str | None = None

    @field_validator("started_at_utc", "ended_at_utc")
    @classmethod
    def require_trial_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("trial timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_trial(self) -> "TrialResult":
        if self.ended_at_utc < self.started_at_utc:
            raise ValueError("trial cannot end before it starts")
        names = tuple(name for name, _ in self.hyperparameters)
        metric_names = tuple(name for name, _ in self.metrics)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("trial hyperparameters must have sorted unique names")
        if metric_names != tuple(sorted(metric_names)) or len(metric_names) != len(
            set(metric_names)
        ):
            raise ValueError("trial metrics must have sorted unique names")
        if any(not math.isfinite(value) for _, value in self.metrics):
            raise ValueError("trial metrics must be finite")
        if self.status is TrialStatus.FAILED and not self.failure_reason:
            raise ValueError("failed trial requires a reason")
        if self.status is TrialStatus.SUCCEEDED and self.failure_reason is not None:
            raise ValueError("successful trial cannot have a failure reason")
        if self.status is TrialStatus.SUCCEEDED and self.artifact_hash is None:
            raise ValueError("successful trial requires an artifact hash")
        if self.holdout_used != (self.split_role is SplitRole.FINAL_HOLDOUT):
            raise ValueError("holdout flag must match split role")
        if self.holdout_used and not self.approved_review_id:
            raise ValueError("holdout trial requires an approved review id")
        return self


class ExperimentSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: UUID
    closed_at_utc: datetime
    trial_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    oos_metrics: tuple[tuple[str, float], ...]
    holdout_used: bool
    decision: ExperimentDecision
    reason: str = Field(min_length=1)

    @field_validator("closed_at_utc")
    @classmethod
    def require_closed_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("experiment close timestamp must be UTC-aware")
        return value

    @field_validator("oos_metrics")
    @classmethod
    def require_summary_metrics(
        cls, values: tuple[tuple[str, float], ...]
    ) -> tuple[tuple[str, float], ...]:
        names = tuple(name for name, _ in values)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("summary metrics must have sorted unique names")
        if any(not math.isfinite(value) for _, value in values):
            raise ValueError("summary metrics must be finite")
        return values


class ExperimentLedgerRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int = Field(ge=1)
    record_id: UUID
    record_type: ExperimentRecordType
    experiment_id: UUID
    trial_id: UUID | None = None
    recorded_at_utc: datetime
    payload_json: str = Field(min_length=2)
    previous_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("recorded_at_utc")
    @classmethod
    def require_recorded_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("experiment ledger timestamp must be UTC-aware")
        return value


class ExperimentLedgerSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    records: tuple[ExperimentLedgerRecord, ...]
    chain_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ExperimentLedger:
    def __init__(self) -> None:
        self._records: list[ExperimentLedgerRecord] = []
        self._registrations: dict[UUID, ExperimentRegistration] = {}
        self._trials: dict[UUID, list[TrialResult]] = {}
        self._summaries: dict[UUID, ExperimentSummary] = {}

    @property
    def records(self) -> tuple[ExperimentLedgerRecord, ...]:
        return tuple(self._records)

    def preregister(self, registration: ExperimentRegistration) -> ExperimentLedgerRecord:
        if registration.experiment_id in self._registrations:
            raise ExperimentLedgerError("experiment is already registered")
        self._registrations[registration.experiment_id] = registration
        self._trials[registration.experiment_id] = []
        return self._append(
            ExperimentRecordType.REGISTRATION,
            registration.experiment_id,
            registration.created_at_utc,
            registration,
        )

    def record_trial(self, trial: TrialResult) -> ExperimentLedgerRecord:
        registration = self._registrations.get(trial.experiment_id)
        if registration is None:
            raise ExperimentLedgerError("trial requires prior experiment registration")
        if trial.experiment_id in self._summaries:
            raise ExperimentLedgerError("closed experiment cannot accept more trials")
        if trial.started_at_utc < registration.created_at_utc:
            raise ExperimentLedgerError("trial started before preregistration")
        if trial.split_role not in registration.planned_splits:
            raise ExperimentLedgerError("trial split was not preregistered")
        planned_parameters = {
            name: set(values) for name, values in registration.hyperparameter_space
        }
        if {name for name, _ in trial.hyperparameters} != set(planned_parameters):
            raise ExperimentLedgerError("trial must bind every preregistered hyperparameter")
        for name, value in trial.hyperparameters:
            if name not in planned_parameters or value not in planned_parameters[name]:
                raise ExperimentLedgerError("trial hyperparameter was not preregistered")
        if any(name not in registration.planned_metrics for name, _ in trial.metrics):
            raise ExperimentLedgerError("trial metric was not preregistered")
        if trial.holdout_used:
            if not registration.final_holdout_planned:
                raise ExperimentLedgerError("final holdout use was not preregistered")
            if any(existing.holdout_used for existing in self._trials[trial.experiment_id]):
                raise ExperimentLedgerError("final holdout can be used only once")
            self._append(
                ExperimentRecordType.HOLDOUT_ACCESS,
                trial.experiment_id,
                trial.started_at_utc,
                trial,
                trial_id=trial.trial_id,
            )
        self._trials[trial.experiment_id].append(trial)
        return self._append(
            ExperimentRecordType.TRIAL,
            trial.experiment_id,
            trial.ended_at_utc,
            trial,
            trial_id=trial.trial_id,
        )

    def close(self, summary: ExperimentSummary) -> ExperimentLedgerRecord:
        registration = self._registrations.get(summary.experiment_id)
        if registration is None:
            raise ExperimentLedgerError("cannot close an unregistered experiment")
        if summary.experiment_id in self._summaries:
            raise ExperimentLedgerError("experiment is already closed")
        trials = self._trials[summary.experiment_id]
        if summary.trial_count != len(trials):
            raise ExperimentLedgerError("summary trial count does not reconcile")
        if summary.failure_count != sum(trial.status is TrialStatus.FAILED for trial in trials):
            raise ExperimentLedgerError("summary failure count does not reconcile")
        if summary.holdout_used != any(trial.holdout_used for trial in trials):
            raise ExperimentLedgerError("summary holdout use does not reconcile")
        if summary.closed_at_utc < registration.created_at_utc:
            raise ExperimentLedgerError("experiment closed before preregistration")
        self._summaries[summary.experiment_id] = summary
        return self._append(
            ExperimentRecordType.DECISION,
            summary.experiment_id,
            summary.closed_at_utc,
            summary,
        )

    def trials_for(self, experiment_id: UUID) -> tuple[TrialResult, ...]:
        try:
            return tuple(self._trials[experiment_id])
        except KeyError as exc:
            raise ExperimentLedgerError("unknown experiment") from exc

    def snapshot(self) -> ExperimentLedgerSnapshot:
        return ExperimentLedgerSnapshot(
            records=self.records,
            chain_hash=self._records[-1].record_hash if self._records else ZERO_HASH,
        )

    def verify(self) -> None:
        previous = ZERO_HASH
        for sequence, record in enumerate(self._records, start=1):
            if record.sequence != sequence or record.previous_hash != previous:
                raise ExperimentLedgerError("experiment ledger sequence is invalid")
            expected = _record_hash(record.model_dump(exclude={"record_hash"}))
            if record.record_hash != expected:
                raise ExperimentLedgerError("experiment ledger hash is invalid")
            previous = record.record_hash

    def _append(
        self,
        record_type: ExperimentRecordType,
        experiment_id: UUID,
        recorded_at_utc: datetime,
        payload: BaseModel,
        *,
        trial_id: UUID | None = None,
    ) -> ExperimentLedgerRecord:
        sequence = len(self._records) + 1
        previous_hash = self._records[-1].record_hash if self._records else ZERO_HASH
        payload_json = orjson.dumps(
            payload.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS
        ).decode()
        values: dict[str, object] = {
            "sequence": sequence,
            "record_id": deterministic_execution_id(
                "experiment-ledger", experiment_id, sequence, record_type, trial_id
            ),
            "record_type": record_type,
            "experiment_id": experiment_id,
            "trial_id": trial_id,
            "recorded_at_utc": recorded_at_utc,
            "payload_json": payload_json,
            "previous_hash": previous_hash,
        }
        record = ExperimentLedgerRecord(**values, record_hash=_record_hash(values))
        self._records.append(record)
        return record


def new_experiment_id(hypothesis_id: str, dataset_hash: str, created_at_utc: datetime) -> UUID:
    return deterministic_execution_id(
        "experiment", hypothesis_id, dataset_hash, created_at_utc.isoformat()
    )


def write_experiment_ledger(snapshot: ExperimentLedgerSnapshot, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    payload = (
        orjson.dumps(
            snapshot.model_dump(mode="json"), option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
        )
        + b"\n"
    )
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _model_digest(model: BaseModel) -> str:
    payload = orjson.dumps(model.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    return sha256(payload).hexdigest()


def _record_hash(values: dict[str, object]) -> str:
    payload = orjson.dumps(values, default=str, option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z)
    return sha256(payload).hexdigest()

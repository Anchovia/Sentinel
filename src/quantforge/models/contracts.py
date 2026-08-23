"""Immutable prediction and model-artifact contracts."""

import math
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain.money import MonetaryDecimal


class Regime(StrEnum):
    UPTREND_LOW_VOL = "UPTREND_LOW_VOL"
    UPTREND_HIGH_VOL = "UPTREND_HIGH_VOL"
    DOWNTREND_LOW_VOL = "DOWNTREND_LOW_VOL"
    DOWNTREND_HIGH_VOL = "DOWNTREND_HIGH_VOL"
    RANGE_LOW_VOL = "RANGE_LOW_VOL"
    RANGE_HIGH_VOL = "RANGE_HIGH_VOL"
    LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
    MARKET_DISLOCATION = "MARKET_DISLOCATION"
    UNCERTAIN = "UNCERTAIN"


class DecisionAction(StrEnum):
    TRADE = "TRADE"
    HOLD = "HOLD"
    ABSTAIN = "ABSTAIN"


class ModelFamily(StrEnum):
    REGIME_RULE = "regime_rule"
    REGIME_GAUSSIAN_MIXTURE = "regime_gaussian_mixture"
    ALPHA_ALWAYS_NEUTRAL = "alpha_always_neutral"
    ALPHA_LOGISTIC = "alpha_logistic"
    ALPHA_BOOSTED_STUMPS = "alpha_boosted_stumps"
    EXECUTION_RULE = "execution_rule"


class ModelReleaseStatus(StrEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    VALIDATED = "VALIDATED"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    CHAMPION = "CHAMPION"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


def _validate_probabilities(values: tuple[tuple[str, float], ...]) -> None:
    names = tuple(name for name, _ in values)
    if not values or names != tuple(sorted(names)) or len(names) != len(set(names)):
        raise ValueError("probabilities must have sorted unique class names")
    probabilities = tuple(value for _, value in values)
    if any(not math.isfinite(value) or value < 0 or value > 1 for value in probabilities):
        raise ValueError("probabilities must be finite and between zero and one")
    if not math.isclose(sum(probabilities), 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("probabilities must sum to one")


class RegimePrediction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction_id: UUID
    market: str
    predicted_at_utc: datetime
    valid_until_utc: datetime
    probabilities: tuple[tuple[str, float], ...]
    selected_regime: Regime
    confidence: float = Field(ge=0, le=1)
    uncertainty: float = Field(ge=0, le=1)
    change_point_score: float = Field(ge=0, le=1)
    expected_duration_seconds: float | None = Field(default=None, gt=0)
    feature_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_version: str
    artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("predicted_at_utc", "valid_until_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("prediction timestamp must be UTC-aware")
        return value

    @field_validator("probabilities")
    @classmethod
    def validate_probabilities(
        cls, values: tuple[tuple[str, float], ...]
    ) -> tuple[tuple[str, float], ...]:
        _validate_probabilities(values)
        return values

    @model_validator(mode="after")
    def validate_prediction(self) -> "RegimePrediction":
        if self.valid_until_utc <= self.predicted_at_utc:
            raise ValueError("prediction validity must end after prediction time")
        probability_map = dict(self.probabilities)
        if self.selected_regime.value not in probability_map:
            raise ValueError("selected regime is absent from probabilities")
        if self.confidence != probability_map[self.selected_regime.value]:
            raise ValueError("regime confidence must match selected probability")
        return self


class AlphaPrediction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction_id: UUID
    market: str
    predicted_at_utc: datetime
    valid_until_utc: datetime
    horizon_seconds: int = Field(gt=0)
    p_down: float = Field(ge=0, le=1)
    p_neutral: float = Field(ge=0, le=1)
    p_up: float = Field(ge=0, le=1)
    expected_gross_return_bps: MonetaryDecimal
    estimated_round_trip_cost_bps: MonetaryDecimal = Field(ge=0)
    expected_net_return_bps: MonetaryDecimal
    prediction_interval_bps: tuple[MonetaryDecimal, MonetaryDecimal]
    uncertainty: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    action: DecisionAction
    abstention_reasons: tuple[str, ...] = ()
    feature_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_version: str
    artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("predicted_at_utc", "valid_until_utc")
    @classmethod
    def require_alpha_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("alpha prediction timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_alpha(self) -> "AlphaPrediction":
        if not math.isclose(
            self.p_down + self.p_neutral + self.p_up,
            1.0,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError("alpha probabilities must sum to one")
        if self.valid_until_utc <= self.predicted_at_utc:
            raise ValueError("alpha validity must end after prediction time")
        if self.expected_net_return_bps != (
            self.expected_gross_return_bps - self.estimated_round_trip_cost_bps
        ):
            raise ValueError("expected net return does not reconcile")
        if self.prediction_interval_bps[0] > self.prediction_interval_bps[1]:
            raise ValueError("prediction interval is reversed")
        if self.action is DecisionAction.ABSTAIN and not self.abstention_reasons:
            raise ValueError("abstention requires at least one reason")
        if self.action is not DecisionAction.ABSTAIN and self.abstention_reasons:
            raise ValueError("non-abstention cannot carry abstention reasons")
        return self


class ExecutionPrediction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction_id: UUID
    market: str
    predicted_at_utc: datetime
    limit_fill_probability: float = Field(ge=0, le=1)
    partial_fill_probability: float = Field(ge=0, le=1)
    full_fill_probability: float = Field(ge=0, le=1)
    expected_time_to_first_fill_ms: float | None = Field(default=None, ge=0)
    expected_time_to_full_fill_ms: float | None = Field(default=None, ge=0)
    market_slippage_bps: MonetaryDecimal = Field(ge=0)
    best_slippage_bps: MonetaryDecimal = Field(ge=0)
    post_only_cancel_probability: float = Field(ge=0, le=1)
    adverse_selection_bps: MonetaryDecimal = Field(ge=0)
    maker_expected_cost_bps: MonetaryDecimal = Field(ge=0)
    taker_expected_cost_bps: MonetaryDecimal = Field(ge=0)
    uncertainty: float = Field(ge=0, le=1)
    model_version: str
    artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("predicted_at_utc")
    @classmethod
    def require_execution_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("execution prediction timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_fill_probabilities(self) -> "ExecutionPrediction":
        if self.full_fill_probability > self.limit_fill_probability:
            raise ValueError("full fill probability cannot exceed any-fill probability")
        if self.partial_fill_probability > self.limit_fill_probability:
            raise ValueError("partial fill probability cannot exceed any-fill probability")
        if self.full_fill_probability + self.partial_fill_probability > (
            self.limit_fill_probability + 1e-9
        ):
            raise ValueError("partial and full probabilities exceed any-fill probability")
        return self


class ModelArtifactMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: UUID
    model_family: ModelFamily
    model_version: str = Field(min_length=1)
    training_code_version: str = Field(min_length=1)
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    feature_version: str = Field(min_length=1)
    label_version: str = Field(min_length=1)
    training_period: tuple[datetime, datetime]
    validation_period: tuple[datetime, datetime]
    test_period: tuple[datetime, datetime]
    hyperparameters: tuple[tuple[str, str], ...]
    random_seed: int
    metrics: tuple[tuple[str, float], ...]
    calibration_metrics: tuple[tuple[str, float], ...]
    market_scope: tuple[str, ...]
    regime_scope: tuple[Regime, ...]
    inference_schema: str = Field(min_length=1)
    artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at_utc: datetime
    approved_by: str | None = None
    release_status: ModelReleaseStatus = ModelReleaseStatus.EXPERIMENTAL

    @field_validator("created_at_utc")
    @classmethod
    def require_artifact_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("model artifact timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_artifact(self) -> "ModelArtifactMetadata":
        for name, period in (
            ("training", self.training_period),
            ("validation", self.validation_period),
            ("test", self.test_period),
        ):
            if (
                any(
                    value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
                    for value in period
                )
                or period[1] <= period[0]
            ):
                raise ValueError(f"{name} period is invalid")
        if not (
            self.training_period[1]
            <= self.validation_period[0]
            <= self.validation_period[1]
            <= self.test_period[0]
        ):
            raise ValueError("model periods are not chronological")
        if (
            self.release_status
            not in {
                ModelReleaseStatus.EXPERIMENTAL,
                ModelReleaseStatus.REJECTED,
            }
            and not self.approved_by
        ):
            raise ValueError("non-experimental model status requires human approval")
        for label, values in (
            ("hyperparameters", self.hyperparameters),
            ("metrics", self.metrics),
            ("calibration metrics", self.calibration_metrics),
        ):
            names = tuple(name for name, _ in values)
            if names != tuple(sorted(names)) or len(names) != len(set(names)):
                raise ValueError(f"model {label} must have sorted unique names")
        for values in (self.metrics, self.calibration_metrics):
            if any(not math.isfinite(value) for _, value in values):
                raise ValueError("model metrics must be finite")
        if not self.market_scope or len(self.market_scope) != len(set(self.market_scope)):
            raise ValueError("model market scope must be non-empty and unique")
        if len(self.regime_scope) != len(set(self.regime_scope)):
            raise ValueError("model regime scope must be unique")
        return self

    @property
    def metadata_hash(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()

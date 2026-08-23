"""Dependency-light calibration, uncertainty, and abstention primitives."""

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantforge.models.contracts import DecisionAction
from quantforge.research.datasets import AlphaClass

CLASS_ORDER = (AlphaClass.DOWN, AlphaClass.NEUTRAL, AlphaClass.UP)
EPSILON = 1e-15


class CalibrationBin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)
    count: int = Field(ge=0)
    mean_confidence: float = Field(ge=0, le=1)
    empirical_accuracy: float = Field(ge=0, le=1)


class CalibrationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_count: int = Field(gt=0)
    multiclass_brier_score: float = Field(ge=0)
    expected_calibration_error: float = Field(ge=0, le=1)
    negative_log_likelihood: float = Field(ge=0)
    class_brier_scores: tuple[tuple[str, float], ...]
    reliability_bins: tuple[CalibrationBin, ...]
    insufficient_sample_warning: bool


class UncertaintyEstimate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    confidence: float = Field(ge=0, le=1)
    normalized_entropy: float = Field(ge=0, le=1)
    probability_margin: float = Field(ge=0, le=1)


class AbstentionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_confidence: float = Field(default=0.55, ge=0, le=1)
    max_uncertainty: float = Field(default=0.85, ge=0, le=1)
    feature_ranges: tuple[tuple[str, float, float], ...] = ()

    @model_validator(mode="after")
    def validate_ranges(self) -> "AbstentionPolicy":
        names = tuple(name for name, _, _ in self.feature_ranges)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("feature ranges must have sorted unique names")
        if any(lower >= upper for _, lower, upper in self.feature_ranges):
            raise ValueError("feature range lower bound must be below upper bound")
        return self

    def decide(
        self,
        probabilities: tuple[float, float, float],
        features: tuple[tuple[str, float], ...],
    ) -> tuple[DecisionAction, tuple[str, ...], UncertaintyEstimate]:
        uncertainty = uncertainty_from_probabilities(probabilities)
        reasons: list[str] = []
        if uncertainty.confidence < self.min_confidence:
            reasons.append("LOW_CONFIDENCE")
        if uncertainty.normalized_entropy > self.max_uncertainty:
            reasons.append("HIGH_UNCERTAINTY")
        feature_map = dict(features)
        for name, lower, upper in self.feature_ranges:
            value = feature_map.get(name)
            if value is None or not lower <= value <= upper:
                reasons.append(f"OUT_OF_DISTRIBUTION:{name}")
        if reasons:
            return DecisionAction.ABSTAIN, tuple(reasons), uncertainty
        selected = max(range(3), key=probabilities.__getitem__)
        action = DecisionAction.HOLD if selected == 1 else DecisionAction.TRADE
        return action, (), uncertainty


class TemperatureScaler:
    """Validation-only scalar calibration selected from a deterministic grid."""

    def __init__(self, temperatures: Sequence[float] | None = None) -> None:
        self.temperatures = tuple(temperatures or (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0))
        if not self.temperatures or any(value <= 0 for value in self.temperatures):
            raise ValueError("temperature candidates must be positive")
        self.temperature: float | None = None

    def fit(
        self,
        probabilities: Sequence[tuple[float, float, float]],
        labels: Sequence[AlphaClass],
    ) -> "TemperatureScaler":
        if not probabilities or len(probabilities) != len(labels):
            raise ValueError("calibration requires aligned non-empty validation data")
        candidates = (
            (self._nll(self._transform_many(probabilities, value), labels), value)
            for value in self.temperatures
        )
        self.temperature = min(candidates)[1]
        return self

    def transform(self, probabilities: tuple[float, float, float]) -> tuple[float, float, float]:
        if self.temperature is None:
            raise ValueError("temperature scaler is not fitted")
        return self._transform_one(probabilities, self.temperature)

    @classmethod
    def _transform_many(
        cls,
        probabilities: Sequence[tuple[float, float, float]],
        temperature: float,
    ) -> tuple[tuple[float, float, float], ...]:
        return tuple(cls._transform_one(values, temperature) for values in probabilities)

    @staticmethod
    def _transform_one(
        probabilities: tuple[float, float, float], temperature: float
    ) -> tuple[float, float, float]:
        powered = tuple(max(value, EPSILON) ** (1.0 / temperature) for value in probabilities)
        total = sum(powered)
        return powered[0] / total, powered[1] / total, powered[2] / total

    @staticmethod
    def _nll(
        probabilities: Sequence[tuple[float, float, float]], labels: Sequence[AlphaClass]
    ) -> float:
        indices = {label: index for index, label in enumerate(CLASS_ORDER)}
        return -sum(
            math.log(max(values[indices[label]], EPSILON))
            for values, label in zip(probabilities, labels, strict=True)
        ) / len(labels)


def uncertainty_from_probabilities(
    probabilities: tuple[float, float, float],
) -> UncertaintyEstimate:
    if any(value < 0 or value > 1 or not math.isfinite(value) for value in probabilities):
        raise ValueError("probabilities must be finite and bounded")
    if not math.isclose(sum(probabilities), 1.0, abs_tol=1e-9):
        raise ValueError("probabilities must sum to one")
    ordered = sorted(probabilities, reverse=True)
    entropy = -sum(value * math.log(max(value, EPSILON)) for value in probabilities)
    return UncertaintyEstimate(
        confidence=ordered[0],
        normalized_entropy=min(1.0, entropy / math.log(3)),
        probability_margin=ordered[0] - ordered[1],
    )


def calibration_report(
    probabilities: Sequence[tuple[float, float, float]],
    labels: Sequence[AlphaClass],
    *,
    bin_count: int = 10,
    minimum_samples: int = 30,
) -> CalibrationReport:
    if not probabilities or len(probabilities) != len(labels):
        raise ValueError("calibration report requires aligned non-empty data")
    if bin_count < 2:
        raise ValueError("calibration report requires at least two bins")
    indices = {label: index for index, label in enumerate(CLASS_ORDER)}
    brier_by_class = []
    for class_index, label_name in enumerate(CLASS_ORDER):
        score = sum(
            (values[class_index] - float(label is label_name)) ** 2
            for values, label in zip(probabilities, labels, strict=True)
        ) / len(labels)
        brier_by_class.append((label_name.value, score))
    multiclass_brier = sum(value for _, value in brier_by_class)
    nll = -sum(
        math.log(max(values[indices[label]], EPSILON))
        for values, label in zip(probabilities, labels, strict=True)
    ) / len(labels)

    bin_members: list[list[tuple[float, bool]]] = [[] for _ in range(bin_count)]
    for values, label in zip(probabilities, labels, strict=True):
        selected = max(range(3), key=values.__getitem__)
        confidence = values[selected]
        bin_index = min(int(confidence * bin_count), bin_count - 1)
        bin_members[bin_index].append((confidence, selected == indices[label]))
    bins: list[CalibrationBin] = []
    weighted_error = 0.0
    for index, members in enumerate(bin_members):
        count = len(members)
        mean_confidence = sum(value for value, _ in members) / count if count else 0.0
        accuracy = sum(correct for _, correct in members) / count if count else 0.0
        weighted_error += count / len(labels) * abs(mean_confidence - accuracy)
        bins.append(
            CalibrationBin(
                lower=index / bin_count,
                upper=(index + 1) / bin_count,
                count=count,
                mean_confidence=mean_confidence,
                empirical_accuracy=accuracy,
            )
        )
    return CalibrationReport(
        sample_count=len(labels),
        multiclass_brier_score=multiclass_brier,
        expected_calibration_error=weighted_error,
        negative_log_likelihood=nll,
        class_brier_scores=tuple(brier_by_class),
        reliability_bins=tuple(bins),
        insufficient_sample_warning=len(labels) < minimum_samples,
    )

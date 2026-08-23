"""Cost-adjusted out-of-sample evaluation that refuses the final holdout."""

import math
import os
from collections.abc import Sequence
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantforge.domain import deterministic_execution_id
from quantforge.models.calibration import (
    AbstentionPolicy,
    CalibrationReport,
    TemperatureScaler,
    calibration_report,
)
from quantforge.models.contracts import DecisionAction
from quantforge.research.datasets import AlphaClass
from quantforge.research.splits import DatasetPartition, SplitRole

type ProbabilityTriple = tuple[float, float, float]


class AlphaProbabilityModel(Protocol):
    def predict_proba(self, values: tuple[tuple[str, float], ...]) -> ProbabilityTriple: ...

    @property
    def artifact_bytes(self) -> bytes: ...


class EvaluatedPrediction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction_id: UUID
    example_id: UUID
    p_down: float = Field(ge=0, le=1)
    p_neutral: float = Field(ge=0, le=1)
    p_up: float = Field(ge=0, le=1)
    predicted_class: AlphaClass
    actual_class: AlphaClass
    action: DecisionAction
    abstention_reasons: tuple[str, ...]
    realized_gross_return_bps: float
    realized_cost_bps: float = Field(ge=0)
    realized_net_return_bps: float


class AlphaEvaluationMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_count: int = Field(gt=0)
    accuracy: float = Field(ge=0, le=1)
    trade_count: int = Field(ge=0)
    abstention_count: int = Field(ge=0)
    abstention_rate: float = Field(ge=0, le=1)
    directional_win_rate: float | None = Field(default=None, ge=0, le=1)
    gross_return_bps: float
    transaction_cost_bps: float = Field(ge=0)
    net_return_bps: float
    average_net_return_per_trade_bps: float | None
    insufficient_sample_warning: bool

    @model_validator(mode="after")
    def validate_metrics(self) -> "AlphaEvaluationMetrics":
        if self.trade_count + self.abstention_count > self.sample_count:
            raise ValueError("evaluation decision counts exceed samples")
        if not math.isclose(
            self.net_return_bps,
            self.gross_return_bps - self.transaction_cost_bps,
            abs_tol=1e-9,
        ):
            raise ValueError("evaluation net return does not reconcile")
        return self


class AlphaEvaluationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    partition_role: SplitRole
    partition_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    cost_bps_per_trade: float = Field(gt=0)
    calibration: CalibrationReport
    metrics: AlphaEvaluationMetrics
    predictions: tuple[EvaluatedPrediction, ...]

    @model_validator(mode="after")
    def refuse_holdout(self) -> "AlphaEvaluationReport":
        if self.partition_role is SplitRole.FINAL_HOLDOUT:
            raise ValueError("ordinary evaluation cannot contain the final holdout")
        return self

    @property
    def output_hash(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()


class BaselineComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    partition_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reports: tuple[AlphaEvaluationReport, ...] = Field(min_length=2)
    net_return_ranking: tuple[str, ...]
    calibration_ranking: tuple[str, ...]
    comparison_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def evaluate_alpha_partition(
    model: AlphaProbabilityModel,
    partition: DatasetPartition,
    *,
    cost_bps_per_trade: Decimal,
    abstention_policy: AbstentionPolicy,
    calibrator: TemperatureScaler | None = None,
    minimum_samples: int = 30,
) -> AlphaEvaluationReport:
    if partition.role is SplitRole.FINAL_HOLDOUT:
        raise PermissionError("ordinary evaluation cannot access the final holdout")
    if cost_bps_per_trade <= 0:
        raise ValueError("cost-adjusted evaluation requires a positive cost")
    probabilities: list[ProbabilityTriple] = []
    predictions: list[EvaluatedPrediction] = []
    labels = tuple(example.alpha_class for example in partition.examples)
    cost = float(cost_bps_per_trade)
    for example in partition.examples:
        values = model.predict_proba(example.values)
        if calibrator is not None:
            values = calibrator.transform(values)
        _require_probabilities(values)
        probabilities.append(values)
        action, reasons, _ = abstention_policy.decide(values, example.values)
        selected = max(range(3), key=values.__getitem__)
        predicted_class = (AlphaClass.DOWN, AlphaClass.NEUTRAL, AlphaClass.UP)[selected]
        direction = -1.0 if selected == 0 else 1.0 if selected == 2 else 0.0
        traded = action is DecisionAction.TRADE
        gross = direction * example.future_return_bps if traded else 0.0
        realized_cost = cost if traded else 0.0
        predictions.append(
            EvaluatedPrediction(
                prediction_id=deterministic_execution_id(
                    "evaluated-alpha",
                    sha256(model.artifact_bytes).hexdigest(),
                    partition.partition_hash,
                    example.example_id,
                ),
                example_id=example.example_id,
                p_down=values[0],
                p_neutral=values[1],
                p_up=values[2],
                predicted_class=predicted_class,
                actual_class=example.alpha_class,
                action=action,
                abstention_reasons=reasons,
                realized_gross_return_bps=gross,
                realized_cost_bps=realized_cost,
                realized_net_return_bps=gross - realized_cost,
            )
        )
    calibration = calibration_report(
        probabilities,
        labels,
        minimum_samples=minimum_samples,
    )
    correct = sum(
        prediction.predicted_class is prediction.actual_class for prediction in predictions
    )
    traded_predictions = [
        prediction for prediction in predictions if prediction.action is DecisionAction.TRADE
    ]
    abstention_count = sum(
        prediction.action is DecisionAction.ABSTAIN for prediction in predictions
    )
    gross_return = sum(prediction.realized_gross_return_bps for prediction in predictions)
    transaction_cost = sum(prediction.realized_cost_bps for prediction in predictions)
    wins = sum(prediction.realized_net_return_bps > 0 for prediction in traded_predictions)
    trade_count = len(traded_predictions)
    metrics = AlphaEvaluationMetrics(
        sample_count=len(predictions),
        accuracy=correct / len(predictions),
        trade_count=trade_count,
        abstention_count=abstention_count,
        abstention_rate=abstention_count / len(predictions),
        directional_win_rate=wins / trade_count if trade_count else None,
        gross_return_bps=gross_return,
        transaction_cost_bps=transaction_cost,
        net_return_bps=gross_return - transaction_cost,
        average_net_return_per_trade_bps=(
            (gross_return - transaction_cost) / trade_count if trade_count else None
        ),
        insufficient_sample_warning=len(predictions) < minimum_samples,
    )
    return AlphaEvaluationReport(
        partition_role=partition.role,
        partition_hash=partition.partition_hash,
        model_artifact_hash=sha256(model.artifact_bytes).hexdigest(),
        cost_bps_per_trade=cost,
        calibration=calibration,
        metrics=metrics,
        predictions=tuple(predictions),
    )


def compare_alpha_baselines(
    reports: Sequence[AlphaEvaluationReport],
) -> BaselineComparison:
    if len(reports) < 2:
        raise ValueError("baseline comparison requires at least two reports")
    partition_hashes = {report.partition_hash for report in reports}
    if len(partition_hashes) != 1:
        raise ValueError("baseline reports use different partitions")
    ordered = tuple(sorted(reports, key=lambda report: report.model_artifact_hash))
    net_ranking = tuple(
        report.model_artifact_hash
        for report in sorted(
            ordered,
            key=lambda report: (
                -report.metrics.net_return_bps,
                report.model_artifact_hash,
            ),
        )
    )
    calibration_ranking = tuple(
        report.model_artifact_hash
        for report in sorted(
            ordered,
            key=lambda report: (
                report.calibration.expected_calibration_error,
                report.model_artifact_hash,
            ),
        )
    )
    values = {
        "partition_hash": ordered[0].partition_hash,
        "report_hashes": [report.output_hash for report in ordered],
        "net_return_ranking": net_ranking,
        "calibration_ranking": calibration_ranking,
    }
    comparison_hash = sha256(orjson.dumps(values, option=orjson.OPT_SORT_KEYS)).hexdigest()
    return BaselineComparison(
        partition_hash=ordered[0].partition_hash,
        reports=ordered,
        net_return_ranking=net_ranking,
        calibration_ranking=calibration_ranking,
        comparison_hash=comparison_hash,
    )


def write_model_evaluation_report(
    report: AlphaEvaluationReport | BaselineComparison, destination: Path
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    payload = (
        orjson.dumps(
            report.model_dump(mode="json"),
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


def _require_probabilities(values: ProbabilityTriple) -> None:
    if any(not math.isfinite(value) or value < 0 or value > 1 for value in values):
        raise ValueError("model emitted invalid probabilities")
    if not math.isclose(sum(values), 1.0, abs_tol=1e-9):
        raise ValueError("model probabilities do not sum to one")

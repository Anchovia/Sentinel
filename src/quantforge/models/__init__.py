"""Versioned baseline model contracts, calibration, evaluation, and registry."""

from quantforge.models.baselines import (
    AlwaysNeutralAlphaBaseline,
    BoostedStumpAlphaCandidate,
    DiagonalGaussianMixtureBaseline,
    ExecutionRuleBaseline,
    MultinomialLogisticAlphaBaseline,
    RuleRegimeBaseline,
    Standardizer,
)
from quantforge.models.calibration import (
    AbstentionPolicy,
    CalibrationBin,
    CalibrationReport,
    TemperatureScaler,
    UncertaintyEstimate,
    calibration_report,
    uncertainty_from_probabilities,
)
from quantforge.models.contracts import (
    AlphaPrediction,
    DecisionAction,
    ExecutionPrediction,
    ModelArtifactMetadata,
    ModelFamily,
    ModelReleaseStatus,
    Regime,
    RegimePrediction,
)
from quantforge.models.evaluation import (
    AlphaEvaluationMetrics,
    AlphaEvaluationReport,
    BaselineComparison,
    EvaluatedPrediction,
    compare_alpha_baselines,
    evaluate_alpha_partition,
    write_model_evaluation_report,
)
from quantforge.models.registry import (
    ModelRegistry,
    ModelRegistryError,
    RegisteredModelArtifact,
)

__all__ = [
    "AbstentionPolicy",
    "AlphaEvaluationMetrics",
    "AlphaEvaluationReport",
    "AlphaPrediction",
    "AlwaysNeutralAlphaBaseline",
    "BaselineComparison",
    "BoostedStumpAlphaCandidate",
    "CalibrationBin",
    "CalibrationReport",
    "DecisionAction",
    "DiagonalGaussianMixtureBaseline",
    "EvaluatedPrediction",
    "ExecutionPrediction",
    "ExecutionRuleBaseline",
    "ModelArtifactMetadata",
    "ModelFamily",
    "ModelRegistry",
    "ModelRegistryError",
    "ModelReleaseStatus",
    "MultinomialLogisticAlphaBaseline",
    "Regime",
    "RegimePrediction",
    "RegisteredModelArtifact",
    "RuleRegimeBaseline",
    "Standardizer",
    "TemperatureScaler",
    "UncertaintyEstimate",
    "calibration_report",
    "compare_alpha_baselines",
    "evaluate_alpha_partition",
    "uncertainty_from_probabilities",
    "write_model_evaluation_report",
]

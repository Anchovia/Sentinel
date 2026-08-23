from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from factories import BASE_TIME, make_labeled_examples
from quantforge.models import (
    AbstentionPolicy,
    AlwaysNeutralAlphaBaseline,
    ModelArtifactMetadata,
    ModelFamily,
    ModelRegistry,
    ModelRegistryError,
    ModelReleaseStatus,
    MultinomialLogisticAlphaBaseline,
    Regime,
    TemperatureScaler,
    compare_alpha_baselines,
    evaluate_alpha_partition,
    write_model_evaluation_report,
)
from quantforge.research import DatasetPartition, SplitRole


def _partition(role: SplitRole, start: int, end: int) -> DatasetPartition:
    return DatasetPartition(
        role=role,
        examples=make_labeled_examples()[start:end],
        partition_hash=sha256(f"{role}:{start}:{end}".encode()).hexdigest(),
    )


def _trained_model() -> MultinomialLogisticAlphaBaseline:
    return MultinomialLogisticAlphaBaseline(("x", "volatility")).fit(make_labeled_examples()[:50])


def test_validation_calibration_and_cost_adjusted_test_are_separate() -> None:
    model = _trained_model()
    validation = _partition(SplitRole.VALIDATION, 50, 70)
    raw_validation = tuple(model.predict_proba(example.values) for example in validation.examples)
    labels = tuple(example.alpha_class for example in validation.examples)
    calibrator = TemperatureScaler().fit(raw_validation, labels)
    test = _partition(SplitRole.TEST, 70, 90)
    report = evaluate_alpha_partition(
        model,
        test,
        cost_bps_per_trade=Decimal(5),
        abstention_policy=AbstentionPolicy(min_confidence=0.5, max_uncertainty=1.0),
        calibrator=calibrator,
    )

    assert report.partition_role is SplitRole.TEST
    assert report.metrics.trade_count > 0
    assert report.metrics.transaction_cost_bps == report.metrics.trade_count * 5
    assert report.metrics.net_return_bps == pytest.approx(
        report.metrics.gross_return_bps - report.metrics.transaction_cost_bps
    )
    assert report.calibration.sample_count == len(test.examples)
    assert report.output_hash == report.output_hash


def test_neutral_baseline_comparison_and_holdout_refusal() -> None:
    test = _partition(SplitRole.TEST, 70, 90)
    policy = AbstentionPolicy(min_confidence=0.5, max_uncertainty=1.0)
    neutral = evaluate_alpha_partition(
        AlwaysNeutralAlphaBaseline(),
        test,
        cost_bps_per_trade=Decimal(5),
        abstention_policy=policy,
    )
    logistic = evaluate_alpha_partition(
        _trained_model(),
        test,
        cost_bps_per_trade=Decimal(5),
        abstention_policy=policy,
    )
    comparison = compare_alpha_baselines((neutral, logistic))
    assert comparison.partition_hash == test.partition_hash
    assert comparison.net_return_ranking[0] == logistic.model_artifact_hash

    holdout = _partition(SplitRole.FINAL_HOLDOUT, 70, 90)
    with pytest.raises(PermissionError, match="final holdout"):
        evaluate_alpha_partition(
            _trained_model(),
            holdout,
            cost_bps_per_trade=Decimal(5),
            abstention_policy=policy,
        )


def test_model_comparison_report_is_atomic(tmp_path: Path) -> None:
    test = _partition(SplitRole.TEST, 70, 90)
    policy = AbstentionPolicy(min_confidence=0.5, max_uncertainty=1.0)
    reports = (
        evaluate_alpha_partition(
            AlwaysNeutralAlphaBaseline(),
            test,
            cost_bps_per_trade=Decimal(5),
            abstention_policy=policy,
        ),
        evaluate_alpha_partition(
            _trained_model(),
            test,
            cost_bps_per_trade=Decimal(5),
            abstention_policy=policy,
        ),
    )
    comparison = compare_alpha_baselines(reports)
    destination = write_model_evaluation_report(comparison, tmp_path / "baseline-comparison.json")

    assert destination.read_bytes().endswith(b"\n")
    assert not list(tmp_path.glob("*.tmp"))
    with pytest.raises(ValueError, match="positive cost"):
        evaluate_alpha_partition(
            _trained_model(),
            test,
            cost_bps_per_trade=Decimal(0),
            abstention_policy=policy,
        )


def _metadata(artifact_bytes: bytes, **overrides: object) -> ModelArtifactMetadata:
    values: dict[str, object] = {
        "model_id": UUID(int=707),
        "model_family": ModelFamily.ALPHA_LOGISTIC,
        "model_version": "1.0.0",
        "training_code_version": "phase4-test",
        "dataset_hash": "d" * 64,
        "feature_version": "features-v1",
        "label_version": "alpha-v1",
        "training_period": (BASE_TIME, BASE_TIME + timedelta(seconds=10)),
        "validation_period": (
            BASE_TIME + timedelta(seconds=10),
            BASE_TIME + timedelta(seconds=20),
        ),
        "test_period": (
            BASE_TIME + timedelta(seconds=20),
            BASE_TIME + timedelta(seconds=30),
        ),
        "hyperparameters": (("learning_rate", "0.05"),),
        "random_seed": 7,
        "metrics": (("net_return_bps", 10.0),),
        "calibration_metrics": (("ece", 0.1),),
        "market_scope": ("KRW-BTC",),
        "regime_scope": (Regime.UNCERTAIN,),
        "inference_schema": "alpha-probabilities-v1",
        "artifact_hash": sha256(artifact_bytes).hexdigest(),
        "created_at_utc": BASE_TIME + timedelta(seconds=31),
        "release_status": ModelReleaseStatus.EXPERIMENTAL,
    }
    values.update(overrides)
    return ModelArtifactMetadata(**values)


def test_registry_roundtrip_is_immutable_and_checksum_verified(tmp_path: Path) -> None:
    artifact = _trained_model().artifact_bytes
    metadata = _metadata(artifact)
    registry = ModelRegistry(tmp_path / "registry")
    registered = registry.register(metadata, artifact)
    loaded_metadata, loaded_artifact, loaded_manifest = registry.load(
        metadata.model_id, metadata.model_version
    )

    assert loaded_metadata == metadata
    assert loaded_artifact == artifact
    assert loaded_manifest == registered
    with pytest.raises(ModelRegistryError, match="already exists"):
        registry.register(metadata, artifact)

    model_root = tmp_path / "registry" / str(metadata.model_id)
    artifact_path = model_root / metadata.model_version / "artifact.bin"
    artifact_path.write_bytes(b"tampered")
    with pytest.raises(ModelRegistryError, match="checksum"):
        registry.load(metadata.model_id, metadata.model_version)


def test_registry_rejects_hash_mismatch_path_traversal_and_unapproved_status(
    tmp_path: Path,
) -> None:
    artifact = b"model"
    registry = ModelRegistry(tmp_path)
    with pytest.raises(ModelRegistryError, match="hash"):
        registry.register(_metadata(artifact, artifact_hash="0" * 64), artifact)
    with pytest.raises(ModelRegistryError, match="path-safe"):
        registry.load(UUID(int=1), "../escape")
    with pytest.raises(ValidationError, match="human approval"):
        _metadata(artifact, release_status=ModelReleaseStatus.CHAMPION)

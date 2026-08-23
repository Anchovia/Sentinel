from datetime import timedelta
from decimal import Decimal
from hashlib import sha256

import pytest

from factories import BASE_TIME, make_labeled_examples
from quantforge.models import (
    AbstentionPolicy,
    AlwaysNeutralAlphaBaseline,
    BoostedStumpAlphaCandidate,
    DecisionAction,
    DiagonalGaussianMixtureBaseline,
    ExecutionRuleBaseline,
    MultinomialLogisticAlphaBaseline,
    Regime,
    RuleRegimeBaseline,
    TemperatureScaler,
    calibration_report,
    uncertainty_from_probabilities,
)
from quantforge.research import AlphaClass


def test_neutral_logistic_and_boosting_baselines_are_deterministic() -> None:
    examples = make_labeled_examples()
    neutral = AlwaysNeutralAlphaBaseline()
    assert neutral.predict_proba(examples[0].values) == (0.0, 1.0, 0.0)

    first = MultinomialLogisticAlphaBaseline(("x", "volatility")).fit(examples)
    second = MultinomialLogisticAlphaBaseline(("x", "volatility")).fit(examples)
    assert first.artifact_bytes == second.artifact_bytes
    assert first.predict_proba(examples[0].values) == second.predict_proba(examples[0].values)
    assert max(range(3), key=first.predict_proba(examples[0].values).__getitem__) == 0
    assert max(range(3), key=first.predict_proba(examples[-1].values).__getitem__) == 2

    booster = BoostedStumpAlphaCandidate(("x",), rounds=10).fit(examples)
    assert max(range(3), key=booster.predict_proba(examples[0].values).__getitem__) == 0
    assert max(range(3), key=booster.predict_proba(examples[-1].values).__getitem__) == 2
    assert sha256(booster.artifact_bytes).hexdigest()


def test_standardization_is_fitted_only_from_supplied_training_examples() -> None:
    training = make_labeled_examples(60)
    model = MultinomialLogisticAlphaBaseline(("x",)).fit(training)
    means_before = model.standardizer.means
    extreme_test = make_labeled_examples(90)[-1].model_copy(
        update={"values": (("volatility", 0.0), ("x", 1e9))}
    )

    model.predict_proba(extreme_test.values)
    assert model.standardizer.means == means_before


def test_rule_and_gaussian_mixture_regime_baselines() -> None:
    rule = RuleRegimeBaseline()
    features = (("spread_bps", 2.0), ("trend_bps", 20.0), ("volatility_bps", 10.0))
    prediction = rule.predict(
        features,
        market="KRW-BTC",
        predicted_at_utc=BASE_TIME,
        valid_for=timedelta(seconds=60),
        feature_snapshot_hash="f" * 64,
    )
    assert prediction.selected_regime is Regime.UPTREND_LOW_VOL
    assert sum(value for _, value in prediction.probabilities) == pytest.approx(1.0)

    rows = tuple((("cluster", float(value)),) for value in (-5, -4.8, -5.2, 4.8, 5, 5.2))
    first = DiagonalGaussianMixtureBaseline(("cluster",)).fit(rows)
    second = DiagonalGaussianMixtureBaseline(("cluster",)).fit(rows)
    assert first.artifact_bytes == second.artifact_bytes
    assert first.predict_proba(rows[0])[0] > 0.99
    assert first.predict_proba(rows[-1])[1] > 0.99


def test_execution_rule_exposes_fill_cost_and_uncertainty() -> None:
    model = ExecutionRuleBaseline(depth_haircut=Decimal("0.5"))
    prediction = model.predict(
        market="KRW-BTC",
        predicted_at_utc=BASE_TIME,
        requested_quantity=Decimal(2),
        opposing_depth=Decimal(1),
        spread_bps=Decimal(10),
        queue_ahead=Decimal(1),
        latency_ms=100,
        maker_fee_bps=Decimal(5),
        taker_fee_bps=Decimal(5),
        slippage_bps=Decimal(2),
        adverse_selection_bps=Decimal(3),
    )

    assert 0 < prediction.limit_fill_probability < 1
    assert prediction.full_fill_probability + prediction.partial_fill_probability == pytest.approx(
        prediction.limit_fill_probability
    )
    assert prediction.taker_expected_cost_bps == Decimal(20)
    assert prediction.maker_expected_cost_bps == Decimal(8)


def test_calibration_uncertainty_temperature_and_abstention() -> None:
    probabilities = ((0.8, 0.1, 0.1), (0.1, 0.2, 0.7), (0.2, 0.6, 0.2))
    labels = (AlphaClass.DOWN, AlphaClass.UP, AlphaClass.NEUTRAL)
    report = calibration_report(probabilities, labels, bin_count=3)
    assert report.sample_count == 3
    assert report.insufficient_sample_warning
    assert report.multiclass_brier_score >= 0

    scaler = TemperatureScaler().fit(probabilities, labels)
    calibrated = scaler.transform(probabilities[0])
    assert sum(calibrated) == pytest.approx(1.0)
    uncertainty = uncertainty_from_probabilities((1 / 3, 1 / 3, 1 / 3))
    assert uncertainty.normalized_entropy == pytest.approx(1.0)

    policy = AbstentionPolicy(
        min_confidence=0.6,
        max_uncertainty=0.9,
        feature_ranges=(("x", -2.0, 2.0),),
    )
    action, reasons, _ = policy.decide((0.34, 0.33, 0.33), (("x", 0.0),))
    assert action is DecisionAction.ABSTAIN
    assert "LOW_CONFIDENCE" in reasons
    action, reasons, _ = policy.decide((0.1, 0.1, 0.8), (("x", 99.0),))
    assert action is DecisionAction.ABSTAIN
    assert reasons == ("OUT_OF_DISTRIBUTION:x",)
    action, reasons, _ = policy.decide((0.1, 0.1, 0.8), (("x", 1.0),))
    assert action is DecisionAction.TRADE
    assert reasons == ()

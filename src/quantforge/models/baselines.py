"""Deterministic, dependency-light baselines that complex models must beat."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from itertools import pairwise

import orjson

from quantforge.domain import deterministic_execution_id
from quantforge.models.contracts import (
    ExecutionPrediction,
    Regime,
    RegimePrediction,
)
from quantforge.research.datasets import AlphaClass, LabeledExample

type ProbabilityTriple = tuple[float, float, float]

CLASS_ORDER = (AlphaClass.DOWN, AlphaClass.NEUTRAL, AlphaClass.UP)
CLASS_INDEX = {label: index for index, label in enumerate(CLASS_ORDER)}


def _softmax(values: Sequence[float]) -> tuple[float, ...]:
    maximum = max(values)
    exponentials = tuple(math.exp(value - maximum) for value in values)
    total = sum(exponentials)
    return tuple(value / total for value in exponentials)


def _feature_vector(
    values: tuple[tuple[str, float], ...], names: tuple[str, ...]
) -> tuple[float, ...]:
    mapping = dict(values)
    try:
        return tuple(mapping[name] for name in names)
    except KeyError as exc:
        raise ValueError(f"missing model feature: {exc.args[0]}") from exc


class Standardizer:
    def __init__(self) -> None:
        self.means: tuple[float, ...] | None = None
        self.scales: tuple[float, ...] | None = None

    def fit(self, vectors: Sequence[tuple[float, ...]]) -> "Standardizer":
        if not vectors or not vectors[0]:
            raise ValueError("standardizer requires non-empty training vectors")
        width = len(vectors[0])
        if any(len(vector) != width for vector in vectors):
            raise ValueError("training vectors have inconsistent width")
        means = tuple(
            sum(vector[index] for vector in vectors) / len(vectors) for index in range(width)
        )
        variances = tuple(
            sum((vector[index] - means[index]) ** 2 for vector in vectors) / len(vectors)
            for index in range(width)
        )
        self.means = means
        self.scales = tuple(math.sqrt(value) if value > 1e-12 else 1.0 for value in variances)
        return self

    def transform(self, vector: tuple[float, ...]) -> tuple[float, ...]:
        if self.means is None or self.scales is None:
            raise ValueError("standardizer is not fitted")
        if len(vector) != len(self.means):
            raise ValueError("vector width does not match fitted standardizer")
        return tuple(
            (value - mean) / scale
            for value, mean, scale in zip(vector, self.means, self.scales, strict=True)
        )

    def state(self) -> dict[str, list[float]]:
        if self.means is None or self.scales is None:
            raise ValueError("standardizer is not fitted")
        return {"means": list(self.means), "scales": list(self.scales)}


class AlwaysNeutralAlphaBaseline:
    model_version = "always-neutral-v1"

    @staticmethod
    def predict_proba(values: tuple[tuple[str, float], ...]) -> ProbabilityTriple:
        del values
        return 0.0, 1.0, 0.0

    @property
    def artifact_bytes(self) -> bytes:
        return orjson.dumps(
            {"family": "alpha_always_neutral", "version": self.model_version},
            option=orjson.OPT_SORT_KEYS,
        )


class MultinomialLogisticAlphaBaseline:
    model_version = "multinomial-logistic-v1"

    def __init__(
        self,
        feature_names: Sequence[str],
        *,
        learning_rate: float = 0.05,
        epochs: int = 400,
        l2: float = 0.001,
    ) -> None:
        self.feature_names = tuple(sorted(feature_names))
        if not self.feature_names or len(self.feature_names) != len(set(self.feature_names)):
            raise ValueError("logistic baseline requires unique features")
        if learning_rate <= 0 or epochs < 1 or l2 < 0:
            raise ValueError("logistic hyperparameters are invalid")
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.l2 = l2
        self.standardizer = Standardizer()
        self.weights: tuple[tuple[float, ...], ...] | None = None

    def fit(self, examples: Sequence[LabeledExample]) -> "MultinomialLogisticAlphaBaseline":
        if not examples:
            raise ValueError("logistic baseline requires training examples")
        raw_vectors = tuple(
            _feature_vector(example.values, self.feature_names) for example in examples
        )
        self.standardizer.fit(raw_vectors)
        vectors = tuple((1.0, *self.standardizer.transform(vector)) for vector in raw_vectors)
        weights = [[0.0 for _ in vectors[0]] for _ in CLASS_ORDER]
        for _ in range(self.epochs):
            gradient = [[0.0 for _ in vectors[0]] for _ in CLASS_ORDER]
            for vector, example in zip(vectors, examples, strict=True):
                probabilities = _softmax(
                    [
                        sum(weight * value for weight, value in zip(row, vector, strict=True))
                        for row in weights
                    ]
                )
                target = CLASS_INDEX[example.alpha_class]
                for class_index in range(len(CLASS_ORDER)):
                    error = probabilities[class_index] - float(class_index == target)
                    for feature_index, value in enumerate(vector):
                        gradient[class_index][feature_index] += error * value
            count = len(vectors)
            for class_index, row in enumerate(weights):
                for feature_index, weight in enumerate(row):
                    penalty = 0.0 if feature_index == 0 else self.l2 * weight
                    weights[class_index][feature_index] -= self.learning_rate * (
                        gradient[class_index][feature_index] / count + penalty
                    )
        self.weights = tuple(tuple(row) for row in weights)
        return self

    def predict_proba(self, values: tuple[tuple[str, float], ...]) -> ProbabilityTriple:
        if self.weights is None:
            raise ValueError("logistic baseline is not fitted")
        vector = (1.0, *self.standardizer.transform(_feature_vector(values, self.feature_names)))
        logits = tuple(
            sum(weight * value for weight, value in zip(row, vector, strict=True))
            for row in self.weights
        )
        probabilities = _softmax(logits)
        return probabilities[0], probabilities[1], probabilities[2]

    @property
    def artifact_bytes(self) -> bytes:
        if self.weights is None:
            raise ValueError("logistic baseline is not fitted")
        return orjson.dumps(
            {
                "family": "alpha_logistic",
                "version": self.model_version,
                "feature_names": self.feature_names,
                "learning_rate": self.learning_rate,
                "epochs": self.epochs,
                "l2": self.l2,
                "standardizer": self.standardizer.state(),
                "weights": self.weights,
            },
            option=orjson.OPT_SORT_KEYS,
        )


@dataclass(frozen=True)
class _Stump:
    feature_index: int
    threshold: float
    left_value: float
    right_value: float


class BoostedStumpAlphaCandidate:
    """Small squared-error gradient boosting candidate, never an automatic promotion target."""

    model_version = "boosted-stumps-v1"

    def __init__(
        self,
        feature_names: Sequence[str],
        *,
        rounds: int = 20,
        learning_rate: float = 0.1,
    ) -> None:
        self.feature_names = tuple(sorted(feature_names))
        if not self.feature_names or rounds < 1 or learning_rate <= 0:
            raise ValueError("boosted-stump configuration is invalid")
        self.rounds = rounds
        self.learning_rate = learning_rate
        self.stumps: tuple[_Stump, ...] | None = None

    def fit(self, examples: Sequence[LabeledExample]) -> "BoostedStumpAlphaCandidate":
        if not examples:
            raise ValueError("boosted stumps require training examples")
        vectors = tuple(_feature_vector(example.values, self.feature_names) for example in examples)
        targets = tuple(float(CLASS_INDEX[example.alpha_class] - 1) for example in examples)
        predictions = [0.0 for _ in examples]
        stumps: list[_Stump] = []
        for _ in range(self.rounds):
            residuals = tuple(
                target - prediction for target, prediction in zip(targets, predictions, strict=True)
            )
            best: tuple[float, int, float, float, float] | None = None
            for feature_index in range(len(self.feature_names)):
                unique = sorted({vector[feature_index] for vector in vectors})
                thresholds = tuple((left + right) / 2 for left, right in pairwise(unique)) or (
                    unique[0],
                )
                for threshold in thresholds:
                    left_indices = [
                        index
                        for index, vector in enumerate(vectors)
                        if vector[feature_index] <= threshold
                    ]
                    right_indices = [
                        index
                        for index, vector in enumerate(vectors)
                        if vector[feature_index] > threshold
                    ]
                    left_value = (
                        sum(residuals[index] for index in left_indices) / len(left_indices)
                        if left_indices
                        else 0.0
                    )
                    right_value = (
                        sum(residuals[index] for index in right_indices) / len(right_indices)
                        if right_indices
                        else 0.0
                    )
                    error = sum(
                        (
                            residuals[index]
                            - (left_value if vector[feature_index] <= threshold else right_value)
                        )
                        ** 2
                        for index, vector in enumerate(vectors)
                    )
                    candidate = (error, feature_index, threshold, left_value, right_value)
                    if best is None or candidate < best:
                        best = candidate
            if best is None:
                break
            _, feature_index, threshold, left_value, right_value = best
            stump = _Stump(
                feature_index,
                threshold,
                left_value * self.learning_rate,
                right_value * self.learning_rate,
            )
            stumps.append(stump)
            for index, vector in enumerate(vectors):
                predictions[index] += (
                    stump.left_value if vector[feature_index] <= threshold else stump.right_value
                )
        self.stumps = tuple(stumps)
        return self

    def predict_proba(self, values: tuple[tuple[str, float], ...]) -> ProbabilityTriple:
        if self.stumps is None:
            raise ValueError("boosted stumps are not fitted")
        vector = _feature_vector(values, self.feature_names)
        score = sum(
            stump.left_value
            if vector[stump.feature_index] <= stump.threshold
            else stump.right_value
            for stump in self.stumps
        )
        raw = (math.exp(-score), math.exp(-abs(score)), math.exp(score))
        total = sum(raw)
        return raw[0] / total, raw[1] / total, raw[2] / total

    @property
    def artifact_bytes(self) -> bytes:
        if self.stumps is None:
            raise ValueError("boosted stumps are not fitted")
        return orjson.dumps(
            {
                "family": "alpha_boosted_stumps",
                "version": self.model_version,
                "feature_names": self.feature_names,
                "rounds": self.rounds,
                "learning_rate": self.learning_rate,
                "stumps": [stump.__dict__ for stump in self.stumps],
            },
            option=orjson.OPT_SORT_KEYS,
        )


class RuleRegimeBaseline:
    model_version = "regime-rule-v1"

    def __init__(
        self,
        *,
        trend_threshold_bps: float = 5,
        high_volatility_bps: float = 30,
        liquidity_stress_spread_bps: float = 50,
        dislocation_return_bps: float = 200,
    ) -> None:
        self.trend_threshold_bps = trend_threshold_bps
        self.high_volatility_bps = high_volatility_bps
        self.liquidity_stress_spread_bps = liquidity_stress_spread_bps
        self.dislocation_return_bps = dislocation_return_bps

    def selected_regime(self, features: tuple[tuple[str, float], ...]) -> Regime:
        values = dict(features)
        trend = values.get("trend_bps")
        volatility = values.get("volatility_bps")
        spread = values.get("spread_bps")
        if trend is None or volatility is None or spread is None:
            return Regime.UNCERTAIN
        if spread >= self.liquidity_stress_spread_bps:
            return Regime.LIQUIDITY_STRESS
        if abs(trend) >= self.dislocation_return_bps:
            return Regime.MARKET_DISLOCATION
        high_volatility = volatility >= self.high_volatility_bps
        if abs(trend) < self.trend_threshold_bps:
            return Regime.RANGE_HIGH_VOL if high_volatility else Regime.RANGE_LOW_VOL
        if trend > 0:
            return Regime.UPTREND_HIGH_VOL if high_volatility else Regime.UPTREND_LOW_VOL
        return Regime.DOWNTREND_HIGH_VOL if high_volatility else Regime.DOWNTREND_LOW_VOL

    def predict(
        self,
        features: tuple[tuple[str, float], ...],
        *,
        market: str,
        predicted_at_utc: datetime,
        valid_for: timedelta,
        feature_snapshot_hash: str,
    ) -> RegimePrediction:
        selected = self.selected_regime(features)
        confidence = 0.55 if selected is Regime.UNCERTAIN else 0.75
        remaining = (1.0 - confidence) / (len(Regime) - 1)
        probabilities = tuple(
            sorted(
                (regime.value, confidence if regime is selected else remaining) for regime in Regime
            )
        )
        artifact_hash = sha256(self.artifact_bytes).hexdigest()
        return RegimePrediction(
            prediction_id=deterministic_execution_id(
                "regime-prediction", artifact_hash, market, predicted_at_utc.isoformat()
            ),
            market=market,
            predicted_at_utc=predicted_at_utc,
            valid_until_utc=predicted_at_utc + valid_for,
            probabilities=probabilities,
            selected_regime=selected,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            change_point_score=min(1.0, abs(dict(features).get("trend_bps", 0.0)) / 200),
            expected_duration_seconds=None,
            feature_snapshot_hash=feature_snapshot_hash,
            model_version=self.model_version,
            artifact_hash=artifact_hash,
        )

    @property
    def artifact_bytes(self) -> bytes:
        return orjson.dumps(
            {
                "family": "regime_rule",
                "version": self.model_version,
                "trend_threshold_bps": self.trend_threshold_bps,
                "high_volatility_bps": self.high_volatility_bps,
                "liquidity_stress_spread_bps": self.liquidity_stress_spread_bps,
                "dislocation_return_bps": self.dislocation_return_bps,
            },
            option=orjson.OPT_SORT_KEYS,
        )


class DiagonalGaussianMixtureBaseline:
    """Small deterministic diagonal Gaussian mixture for regime comparison."""

    model_version = "diagonal-gmm-v1"

    def __init__(self, feature_names: Sequence[str], *, components: int = 2, iterations: int = 40):
        self.feature_names = tuple(sorted(feature_names))
        if not self.feature_names or components < 2 or iterations < 1:
            raise ValueError("Gaussian mixture configuration is invalid")
        self.components = components
        self.iterations = iterations
        self.weights: tuple[float, ...] | None = None
        self.means: tuple[tuple[float, ...], ...] | None = None
        self.variances: tuple[tuple[float, ...], ...] | None = None

    def fit(
        self, feature_rows: Sequence[tuple[tuple[str, float], ...]]
    ) -> "DiagonalGaussianMixtureBaseline":
        vectors = tuple(_feature_vector(values, self.feature_names) for values in feature_rows)
        if len(vectors) < self.components:
            raise ValueError("Gaussian mixture has fewer rows than components")
        ordered = sorted(vectors, key=lambda vector: (vector[0], vector))
        means = [
            list(ordered[min(len(ordered) - 1, index * len(ordered) // self.components)])
            for index in range(self.components)
        ]
        global_variance = [
            max(
                sum(
                    (vector[index] - sum(row[index] for row in vectors) / len(vectors)) ** 2
                    for vector in vectors
                )
                / len(vectors),
                1e-6,
            )
            for index in range(len(self.feature_names))
        ]
        variances = [global_variance.copy() for _ in range(self.components)]
        weights = [1.0 / self.components for _ in range(self.components)]
        for _ in range(self.iterations):
            responsibilities = [
                self._responsibilities(vector, weights, means, variances) for vector in vectors
            ]
            for component in range(self.components):
                mass = max(sum(row[component] for row in responsibilities), 1e-12)
                weights[component] = mass / len(vectors)
                for feature in range(len(self.feature_names)):
                    means[component][feature] = (
                        sum(
                            row[component] * vector[feature]
                            for row, vector in zip(responsibilities, vectors, strict=True)
                        )
                        / mass
                    )
                    variances[component][feature] = max(
                        sum(
                            row[component] * (vector[feature] - means[component][feature]) ** 2
                            for row, vector in zip(responsibilities, vectors, strict=True)
                        )
                        / mass,
                        1e-6,
                    )
        ordering = sorted(range(self.components), key=lambda index: tuple(means[index]))
        self.weights = tuple(weights[index] for index in ordering)
        self.means = tuple(tuple(means[index]) for index in ordering)
        self.variances = tuple(tuple(variances[index]) for index in ordering)
        return self

    def predict_proba(self, values: tuple[tuple[str, float], ...]) -> tuple[float, ...]:
        if self.weights is None or self.means is None or self.variances is None:
            raise ValueError("Gaussian mixture is not fitted")
        vector = _feature_vector(values, self.feature_names)
        return tuple(self._responsibilities(vector, self.weights, self.means, self.variances))

    @staticmethod
    def _responsibilities(
        vector: tuple[float, ...],
        weights: Sequence[float],
        means: Sequence[Sequence[float]],
        variances: Sequence[Sequence[float]],
    ) -> list[float]:
        log_scores = []
        for weight, mean, variance in zip(weights, means, variances, strict=True):
            log_density = math.log(max(weight, 1e-15))
            for value, center, spread in zip(vector, mean, variance, strict=True):
                log_density += -0.5 * (
                    math.log(2 * math.pi * spread) + (value - center) ** 2 / spread
                )
            log_scores.append(log_density)
        probabilities = _softmax(log_scores)
        return list(probabilities)

    @property
    def artifact_bytes(self) -> bytes:
        if self.weights is None or self.means is None or self.variances is None:
            raise ValueError("Gaussian mixture is not fitted")
        return orjson.dumps(
            {
                "family": "regime_gaussian_mixture",
                "version": self.model_version,
                "feature_names": self.feature_names,
                "components": self.components,
                "iterations": self.iterations,
                "weights": self.weights,
                "means": self.means,
                "variances": self.variances,
            },
            option=orjson.OPT_SORT_KEYS,
        )


class ExecutionRuleBaseline:
    model_version = "execution-rule-v1"

    def __init__(
        self,
        *,
        depth_haircut: Decimal = Decimal("0.8"),
        latency_decay_ms: int = 2_000,
    ) -> None:
        if depth_haircut <= 0 or depth_haircut > 1 or latency_decay_ms <= 0:
            raise ValueError("execution baseline configuration is invalid")
        self.depth_haircut = depth_haircut
        self.latency_decay_ms = latency_decay_ms

    def predict(
        self,
        *,
        market: str,
        predicted_at_utc: datetime,
        requested_quantity: Decimal,
        opposing_depth: Decimal,
        spread_bps: Decimal,
        queue_ahead: Decimal,
        latency_ms: int,
        maker_fee_bps: Decimal,
        taker_fee_bps: Decimal,
        slippage_bps: Decimal,
        adverse_selection_bps: Decimal,
    ) -> ExecutionPrediction:
        if requested_quantity <= 0 or opposing_depth < 0 or queue_ahead < 0 or latency_ms < 0:
            raise ValueError("execution inputs are invalid")
        latency_factor = math.exp(-latency_ms / self.latency_decay_ms)
        depth_ratio = float(opposing_depth * self.depth_haircut / requested_quantity)
        any_fill = max(0.0, min(1.0, depth_ratio * latency_factor))
        full_fill = max(0.0, min(any_fill, (depth_ratio - 0.1) * latency_factor))
        partial_fill = max(0.0, any_fill - full_fill)
        queue_penalty = min(1.0, float(queue_ahead / requested_quantity))
        limit_fill = any_fill * (1.0 - 0.5 * queue_penalty)
        full_share = full_fill / any_fill if any_fill else 0.0
        full_fill = limit_fill * full_share
        partial_fill = limit_fill - full_fill
        maker_cost = maker_fee_bps + adverse_selection_bps
        taker_cost = taker_fee_bps + spread_bps + slippage_bps + adverse_selection_bps
        artifact_hash = sha256(self.artifact_bytes).hexdigest()
        return ExecutionPrediction(
            prediction_id=deterministic_execution_id(
                "execution-prediction",
                artifact_hash,
                market,
                predicted_at_utc.isoformat(),
                requested_quantity,
            ),
            market=market,
            predicted_at_utc=predicted_at_utc,
            limit_fill_probability=limit_fill,
            partial_fill_probability=partial_fill,
            full_fill_probability=full_fill,
            expected_time_to_first_fill_ms=(latency_ms / max(limit_fill, 1e-9)),
            expected_time_to_full_fill_ms=(latency_ms / full_fill if full_fill > 0 else None),
            market_slippage_bps=slippage_bps,
            best_slippage_bps=slippage_bps / Decimal(2),
            post_only_cancel_probability=1.0 - limit_fill,
            adverse_selection_bps=adverse_selection_bps,
            maker_expected_cost_bps=maker_cost,
            taker_expected_cost_bps=taker_cost,
            uncertainty=1.0 - min(1.0, float(opposing_depth / requested_quantity)),
            model_version=self.model_version,
            artifact_hash=artifact_hash,
        )

    @property
    def artifact_bytes(self) -> bytes:
        return orjson.dumps(
            {
                "family": "execution_rule",
                "version": self.model_version,
                "depth_haircut": str(self.depth_haircut),
                "latency_decay_ms": self.latency_decay_ms,
            },
            option=orjson.OPT_SORT_KEYS,
        )

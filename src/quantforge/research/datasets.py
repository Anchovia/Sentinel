"""Versioned feature rows and forward labels with explicit availability lineage."""

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import MonetaryDecimal, deterministic_execution_id
from quantforge.features import FeatureSnapshot


class AlphaClass(StrEnum):
    DOWN = "down"
    NEUTRAL = "neutral"
    UP = "up"


class AlphaLabelSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(min_length=1)
    horizon_seconds: int = Field(gt=0)
    reference_feature: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    estimated_round_trip_cost_bps: MonetaryDecimal = Field(ge=0)
    safety_margin_bps: MonetaryDecimal = Field(ge=0)

    @property
    def threshold_bps(self) -> Decimal:
        return self.estimated_round_trip_cost_bps + self.safety_margin_bps

    @property
    def digest(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()


class FeatureRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    row_id: UUID
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    event_time_utc: datetime
    available_at_utc: datetime
    feature_set: str
    feature_version: str
    values: tuple[tuple[str, float], ...]
    reference_price: MonetaryDecimal = Field(gt=0)
    source_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("event_time_utc", "available_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("feature row timestamps must be UTC-aware")
        return value

    @field_validator("values")
    @classmethod
    def require_sorted_finite_values(
        cls, values: tuple[tuple[str, float], ...]
    ) -> tuple[tuple[str, float], ...]:
        names = tuple(name for name, _ in values)
        if not values or names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("feature row values must be non-empty, unique, and sorted")
        if any(not name or not math.isfinite(value) for name, value in values):
            raise ValueError("feature row names and values must be valid and finite")
        return values

    @model_validator(mode="after")
    def validate_availability(self) -> "FeatureRow":
        if self.available_at_utc < self.event_time_utc:
            raise ValueError("feature row cannot be available before event time")
        return self

    @property
    def feature_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.values)


class FeatureDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    dataset_id: UUID
    market: str
    feature_set: str
    feature_version: str
    code_version: str
    created_at_utc: datetime
    rows: tuple[FeatureRow, ...]

    @field_validator("created_at_utc")
    @classmethod
    def require_created_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("dataset timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_rows(self) -> "FeatureDataset":
        if not self.rows:
            raise ValueError("feature dataset cannot be empty")
        ordered = tuple(
            sorted(
                self.rows,
                key=lambda row: (
                    row.event_time_utc,
                    row.available_at_utc,
                    str(row.row_id),
                ),
            )
        )
        if self.rows != ordered:
            raise ValueError("feature dataset rows must be chronological")
        schemas = {row.feature_names for row in self.rows}
        if len(schemas) != 1:
            raise ValueError("all feature rows must share one schema")
        if any(
            row.market != self.market
            or row.feature_set != self.feature_set
            or row.feature_version != self.feature_version
            for row in self.rows
        ):
            raise ValueError("feature row lineage does not match dataset")
        return self

    @property
    def dataset_hash(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()


class LabeledExample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    example_id: UUID
    source_row_id: UUID
    market: str
    event_time_utc: datetime
    features_available_at_utc: datetime
    label_end_utc: datetime
    label_available_at_utc: datetime
    values: tuple[tuple[str, float], ...]
    alpha_class: AlphaClass
    future_return_bps: float
    current_reference_price: MonetaryDecimal = Field(gt=0)
    future_reference_price: MonetaryDecimal = Field(gt=0)

    @field_validator(
        "event_time_utc",
        "features_available_at_utc",
        "label_end_utc",
        "label_available_at_utc",
    )
    @classmethod
    def require_example_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("labeled example timestamps must be UTC-aware")
        return value

    @field_validator("future_return_bps")
    @classmethod
    def require_finite_return(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("future return must be finite")
        return value

    @model_validator(mode="after")
    def validate_label_timing(self) -> "LabeledExample":
        if self.label_end_utc <= self.event_time_utc:
            raise ValueError("label horizon must end after feature event")
        if self.label_available_at_utc < max(self.features_available_at_utc, self.label_end_utc):
            raise ValueError("label availability would leak future information")
        return self


class LabeledDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    source_dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    label_spec: AlphaLabelSpec
    examples: tuple[LabeledExample, ...]

    @model_validator(mode="after")
    def validate_examples(self) -> "LabeledDataset":
        if not self.examples:
            raise ValueError("labeled dataset cannot be empty")
        ordered = tuple(
            sorted(
                self.examples,
                key=lambda item: (item.event_time_utc, str(item.example_id)),
            )
        )
        if self.examples != ordered:
            raise ValueError("labeled examples must be chronological")
        return self

    @property
    def dataset_hash(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()


def build_feature_dataset(
    snapshots: Sequence[FeatureSnapshot],
    *,
    required_features: Sequence[str],
    reference_feature: str,
    code_version: str,
    created_at_utc: datetime,
) -> FeatureDataset:
    if not snapshots or not required_features:
        raise ValueError("feature dataset requires snapshots and requested features")
    requested = tuple(sorted(set(required_features)))
    if len(requested) != len(required_features):
        raise ValueError("required features must be unique")
    first = snapshots[0]
    rows: list[FeatureRow] = []
    for snapshot in sorted(
        snapshots, key=lambda item: (item.event_time_utc, item.available_at_utc, item.snapshot_hash)
    ):
        if (
            snapshot.market != first.market
            or snapshot.feature_set != first.feature_set
            or snapshot.feature_version != first.feature_version
        ):
            raise ValueError("feature snapshots do not share lineage")
        required_names = (*requested, reference_feature)
        missing = [name for name in required_names if snapshot.values.get(name) is None]
        if missing:
            missing_names = sorted(set(missing))
            raise ValueError(f"feature snapshot has missing required values: {missing_names}")
        values = tuple((name, float(snapshot.values[name])) for name in requested)  # type: ignore[arg-type]
        reference = Decimal(str(snapshot.values[reference_feature]))
        rows.append(
            FeatureRow(
                row_id=deterministic_execution_id("feature-row", snapshot.snapshot_hash, requested),
                market=snapshot.market,
                event_time_utc=snapshot.event_time_utc,
                available_at_utc=snapshot.available_at_utc,
                feature_set=snapshot.feature_set,
                feature_version=snapshot.feature_version,
                values=values,
                reference_price=reference,
                source_snapshot_hash=snapshot.snapshot_hash,
            )
        )
    identity = "|".join(
        (
            first.market,
            first.feature_set,
            first.feature_version,
            code_version,
            *(str(row.row_id) for row in rows),
        )
    )
    return FeatureDataset(
        dataset_id=deterministic_execution_id(
            "feature-dataset",
            sha256(identity.encode()).hexdigest(),
        ),
        market=first.market,
        feature_set=first.feature_set,
        feature_version=first.feature_version,
        code_version=code_version,
        created_at_utc=created_at_utc,
        rows=tuple(rows),
    )


def build_forward_labels(dataset: FeatureDataset, spec: AlphaLabelSpec) -> LabeledDataset:
    examples: list[LabeledExample] = []
    horizon = timedelta(seconds=spec.horizon_seconds)
    future_index = 1
    for index, current in enumerate(dataset.rows):
        future_index = max(future_index, index + 1)
        target_time = current.event_time_utc + horizon
        while (
            future_index < len(dataset.rows)
            and dataset.rows[future_index].event_time_utc < target_time
        ):
            future_index += 1
        if future_index >= len(dataset.rows):
            break
        future = dataset.rows[future_index]
        return_bps = math.log(float(future.reference_price / current.reference_price)) * 10_000
        threshold = float(spec.threshold_bps)
        if return_bps > threshold:
            alpha_class = AlphaClass.UP
        elif return_bps < -threshold:
            alpha_class = AlphaClass.DOWN
        else:
            alpha_class = AlphaClass.NEUTRAL
        examples.append(
            LabeledExample(
                example_id=deterministic_execution_id(
                    "alpha-label", current.row_id, future.row_id, spec.digest
                ),
                source_row_id=current.row_id,
                market=current.market,
                event_time_utc=current.event_time_utc,
                features_available_at_utc=current.available_at_utc,
                label_end_utc=future.event_time_utc,
                label_available_at_utc=max(
                    current.available_at_utc,
                    future.available_at_utc,
                    future.event_time_utc,
                ),
                values=current.values,
                alpha_class=alpha_class,
                future_return_bps=return_bps,
                current_reference_price=current.reference_price,
                future_reference_price=future.reference_price,
            )
        )
    return LabeledDataset(
        source_dataset_hash=dataset.dataset_hash,
        label_spec=spec,
        examples=tuple(examples),
    )

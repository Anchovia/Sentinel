"""Chronological train/validation/test/final-holdout partitions with purge and embargo."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from itertools import pairwise
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import deterministic_execution_id
from quantforge.research.datasets import LabeledDataset, LabeledExample


class SplitRole(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    FINAL_HOLDOUT = "final_holdout"


class DatasetPartition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: SplitRole
    examples: tuple[LabeledExample, ...]
    partition_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ChronologicalSplit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    source_dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    purge_seconds: int = Field(ge=0)
    embargo_seconds: int = Field(ge=0)
    train: DatasetPartition
    validation: DatasetPartition
    test: DatasetPartition
    final_holdout: DatasetPartition

    @model_validator(mode="after")
    def validate_roles_and_order(self) -> "ChronologicalSplit":
        partitions = (self.train, self.validation, self.test, self.final_holdout)
        expected = tuple(SplitRole)
        if tuple(partition.role for partition in partitions) != expected:
            raise ValueError("split roles are invalid")
        if any(not partition.examples for partition in partitions):
            raise ValueError("every chronological partition must be non-empty")
        for left, right in pairwise(partitions):
            if left.examples[-1].event_time_utc >= right.examples[0].event_time_utc:
                raise ValueError("chronological partitions overlap or are out of order")
        return self


class HoldoutAccessRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    access_id: UUID
    partition_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_review_id: str = Field(min_length=1)
    accessed_at_utc: datetime

    @field_validator("accessed_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("holdout access timestamp must be UTC-aware")
        return value


class FinalHoldoutVault:
    """In-process one-shot guard; durable access must also be written to the trial ledger."""

    def __init__(self, partition: DatasetPartition) -> None:
        if partition.role is not SplitRole.FINAL_HOLDOUT:
            raise ValueError("vault accepts only the final holdout partition")
        self._partition = partition
        self._access: HoldoutAccessRecord | None = None

    @property
    def is_sealed(self) -> bool:
        return self._access is None

    @property
    def access_record(self) -> HoldoutAccessRecord | None:
        return self._access

    def open_once(
        self, *, approved_review_id: str, accessed_at_utc: datetime
    ) -> tuple[LabeledExample, ...]:
        if self._access is not None:
            raise PermissionError("final holdout was already accessed")
        self._access = HoldoutAccessRecord(
            access_id=deterministic_execution_id(
                "holdout-access", self._partition.partition_hash, approved_review_id
            ),
            partition_hash=self._partition.partition_hash,
            approved_review_id=approved_review_id,
            accessed_at_utc=accessed_at_utc,
        )
        return self._partition.examples


def chronological_four_way_split(
    dataset: LabeledDataset,
    *,
    train_fraction: float = 0.5,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
    final_holdout_fraction: float = 0.1,
    purge_seconds: int = 0,
    embargo_seconds: int = 0,
) -> ChronologicalSplit:
    fractions = (
        train_fraction,
        validation_fraction,
        test_fraction,
        final_holdout_fraction,
    )
    if any(value <= 0 or value >= 1 for value in fractions):
        raise ValueError("split fractions must be strictly between zero and one")
    if not math_isclose(sum(fractions), 1.0):
        raise ValueError("split fractions must sum to one")
    if purge_seconds < 0 or embargo_seconds < 0:
        raise ValueError("purge and embargo cannot be negative")
    count = len(dataset.examples)
    train_end = int(count * train_fraction)
    validation_end = train_end + int(count * validation_fraction)
    test_end = validation_end + int(count * test_fraction)
    if (
        train_end < 1
        or validation_end <= train_end
        or test_end <= validation_end
        or test_end >= count
    ):
        raise ValueError("dataset is too small for four non-empty partitions")

    raw = (
        dataset.examples[:train_end],
        dataset.examples[train_end:validation_end],
        dataset.examples[validation_end:test_end],
        dataset.examples[test_end:],
    )
    embargo = timedelta(seconds=embargo_seconds)
    purge = timedelta(seconds=purge_seconds)
    cleaned: list[tuple[LabeledExample, ...]] = []
    for index, examples in enumerate(raw):
        start = examples[0].event_time_utc + (embargo if index > 0 else timedelta(0))
        kept = tuple(example for example in examples if example.event_time_utc >= start)
        if index < len(raw) - 1:
            next_start = raw[index + 1][0].event_time_utc - purge
            kept = tuple(example for example in kept if example.label_end_utc < next_start)
        if not kept:
            raise ValueError("purge or embargo emptied a chronological partition")
        cleaned.append(kept)

    roles = tuple(SplitRole)
    partitions = tuple(
        _partition(role, examples) for role, examples in zip(roles, cleaned, strict=True)
    )
    plan_payload = {
        "source_dataset_hash": dataset.dataset_hash,
        "fractions": fractions,
        "purge_seconds": purge_seconds,
        "embargo_seconds": embargo_seconds,
        "partitions": [partition.partition_hash for partition in partitions],
    }
    plan_hash = sha256(orjson.dumps(plan_payload, option=orjson.OPT_SORT_KEYS)).hexdigest()
    return ChronologicalSplit(
        source_dataset_hash=dataset.dataset_hash,
        plan_hash=plan_hash,
        purge_seconds=purge_seconds,
        embargo_seconds=embargo_seconds,
        train=partitions[0],
        validation=partitions[1],
        test=partitions[2],
        final_holdout=partitions[3],
    )


def _partition(role: SplitRole, examples: tuple[LabeledExample, ...]) -> DatasetPartition:
    payload = orjson.dumps(
        {
            "role": role,
            "example_ids": [str(example.example_id) for example in examples],
        },
        option=orjson.OPT_SORT_KEYS,
    )
    return DatasetPartition(
        role=role,
        examples=examples,
        partition_hash=sha256(payload).hexdigest(),
    )


def math_isclose(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-12

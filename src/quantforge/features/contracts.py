"""Versioned feature output with explicit availability time."""

import math
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LookaheadViolation(ValueError):
    """Raised when a calculation attempts to use unavailable input."""


class FeatureSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    feature_set: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    market: str = Field(pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    event_time_utc: datetime
    available_at_utc: datetime
    computed_at_utc: datetime
    values: dict[str, float | None]
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    quality_flags: tuple[str, ...] = ()

    @field_validator("event_time_utc", "available_at_utc", "computed_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("feature timestamps must be UTC-aware")
        return value

    @field_validator("values")
    @classmethod
    def require_finite_values(cls, values: dict[str, float | None]) -> dict[str, float | None]:
        if not values:
            raise ValueError("feature snapshot cannot be empty")
        for name, value in values.items():
            if not name or (value is not None and not math.isfinite(value)):
                raise ValueError("feature names must be non-empty and values must be finite")
        return values

    @model_validator(mode="after")
    def validate_availability(self) -> "FeatureSnapshot":
        if self.computed_at_utc < self.available_at_utc:
            raise ValueError("feature cannot be computed before all inputs are available")
        if len(set(self.quality_flags)) != len(self.quality_flags):
            raise ValueError("feature quality flags must be unique")
        return self

    @property
    def snapshot_hash(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()

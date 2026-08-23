"""Explicit market-data coverage and gap contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DataGapReason(StrEnum):
    CONNECTION_LOST = "connection_lost"
    STORAGE_FAILURE = "storage_failure"
    PROCESSING_FAILURE = "processing_failure"
    CHECKSUM_FAILURE = "checksum_failure"
    UNKNOWN_COVERAGE = "unknown_coverage"


class DataGap(BaseModel):
    """An interval whose source data cannot be asserted complete."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["data_gap"] = "data_gap"
    schema_version: Annotated[int, Field(ge=1)] = 1
    market: str = Field(pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    start_utc: datetime
    end_utc: datetime
    known_at_utc: datetime
    reason: DataGapReason
    details: str = Field(min_length=1, max_length=500)

    @field_validator("start_utc", "end_utc", "known_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("gap timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> "DataGap":
        if self.end_utc <= self.start_utc:
            raise ValueError("gap end must be after start")
        if self.known_at_utc < self.end_utc:
            raise ValueError("a gap cannot be known before its interval ends")
        return self

    @property
    def availability_time(self) -> datetime:
        return self.known_at_utc

    def fingerprint(self) -> str:
        payload = "|".join(
            (
                self.kind,
                str(self.schema_version),
                self.market,
                self.start_utc.isoformat(),
                self.end_utc.isoformat(),
                self.known_at_utc.isoformat(),
                self.reason.value,
                self.details,
            )
        )
        return sha256(payload.encode()).hexdigest()


class CoverageWindow(BaseModel):
    """Positive evidence that collection was continuously healthy for an interval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str = Field(pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    start_utc: datetime
    end_utc: datetime
    asserted_at_utc: datetime
    source: Literal["collector_health"] = "collector_health"

    @field_validator("start_utc", "end_utc", "asserted_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("coverage timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> "CoverageWindow":
        if self.end_utc <= self.start_utc:
            raise ValueError("coverage end must be after start")
        if self.asserted_at_utc < self.end_utc:
            raise ValueError("coverage cannot be asserted before its interval ends")
        return self

"""Deterministic, liquidity-aware KRW spot universe selection."""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UniverseCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    market_active: bool
    warning_active: bool
    data_age_ms: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0, le=1)
    quote_volume_24h: Decimal = Field(ge=0)
    relative_spread_bps: Decimal = Field(ge=0)
    depth_notional: Decimal = Field(ge=0)


class UniversePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_markets: int = Field(gt=0)
    max_data_age_ms: int = Field(gt=0)
    min_coverage_ratio: float = Field(ge=0, le=1)
    min_quote_volume_24h: Decimal = Field(ge=0)
    max_relative_spread_bps: Decimal = Field(ge=0)
    min_depth_notional: Decimal = Field(ge=0)


class UniverseSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selected_at_utc: datetime
    selected_markets: tuple[str, ...]
    rejected: tuple[tuple[str, tuple[str, ...]], ...]
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("selected_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("universe selection timestamp must be UTC-aware")
        return value


class UniverseSelector:
    def __init__(self, policy: UniversePolicy) -> None:
        self.policy = policy

    def select(
        self, candidates: tuple[UniverseCandidate, ...], *, selected_at_utc: datetime
    ) -> UniverseSelection:
        accepted: list[UniverseCandidate] = []
        rejected: list[tuple[str, tuple[str, ...]]] = []
        for candidate in sorted(candidates, key=lambda item: item.market):
            reasons: list[str] = []
            if not candidate.market_active:
                reasons.append("INACTIVE")
            if candidate.warning_active:
                reasons.append("WARNING")
            if candidate.data_age_ms > self.policy.max_data_age_ms:
                reasons.append("STALE")
            if candidate.coverage_ratio < self.policy.min_coverage_ratio:
                reasons.append("LOW_COVERAGE")
            if candidate.quote_volume_24h < self.policy.min_quote_volume_24h:
                reasons.append("LOW_VOLUME")
            if candidate.relative_spread_bps > self.policy.max_relative_spread_bps:
                reasons.append("WIDE_SPREAD")
            if candidate.depth_notional < self.policy.min_depth_notional:
                reasons.append("LOW_DEPTH")
            if reasons:
                rejected.append((candidate.market, tuple(reasons)))
            else:
                accepted.append(candidate)
        ranked = sorted(
            accepted,
            key=lambda item: (
                -item.quote_volume_24h,
                item.relative_spread_bps,
                -item.depth_notional,
                item.market,
            ),
        )
        selected = tuple(item.market for item in ranked[: self.policy.max_markets])
        for candidate in ranked[self.policy.max_markets :]:
            rejected.append((candidate.market, ("CAPACITY",)))
        policy_payload = orjson.dumps(
            self.policy.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS
        )
        return UniverseSelection(
            selected_at_utc=selected_at_utc,
            selected_markets=selected,
            rejected=tuple(sorted(rejected)),
            policy_hash=sha256(policy_payload).hexdigest(),
        )

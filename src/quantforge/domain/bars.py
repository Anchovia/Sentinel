"""Immutable time-bar contracts with explicit no-trade and data-gap semantics."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain.money import MonetaryDecimal

type SupportedInterval = Literal[1, 5, 15, 60]


class TradeBar(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bar_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    schema_version: Annotated[int, Field(ge=1)] = 1
    market: str = Field(pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    interval_seconds: SupportedInterval
    start_utc: datetime
    end_utc: datetime
    available_at_utc: datetime
    open: MonetaryDecimal | None
    high: MonetaryDecimal | None
    low: MonetaryDecimal | None
    close: MonetaryDecimal | None
    volume: MonetaryDecimal | None
    quote_volume: MonetaryDecimal | None
    trade_count: Annotated[int, Field(ge=0)] | None
    aggressive_buy_volume: MonetaryDecimal | None
    aggressive_sell_volume: MonetaryDecimal | None
    vwap: MonetaryDecimal | None
    first_trade_timestamp: datetime | None
    last_trade_timestamp: datetime | None
    is_complete: bool
    no_trade: bool
    data_gap: bool
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    quality_flags: tuple[str, ...] = ()

    @field_validator(
        "start_utc",
        "end_utc",
        "available_at_utc",
        "first_trade_timestamp",
        "last_trade_timestamp",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError("bar timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> "TradeBar":
        if self.end_utc != self.start_utc + timedelta(seconds=self.interval_seconds):
            raise ValueError("bar end must equal start plus interval")
        if int(self.start_utc.timestamp()) % self.interval_seconds:
            raise ValueError("bar start must be aligned to its interval")
        if self.available_at_utc < self.end_utc:
            raise ValueError("a bar cannot be available before it closes")
        if self.no_trade and self.data_gap:
            raise ValueError("no-trade and data-gap are mutually exclusive")

        values = (
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
            self.quote_volume,
            self.trade_count,
            self.aggressive_buy_volume,
            self.aggressive_sell_volume,
            self.vwap,
            self.first_trade_timestamp,
            self.last_trade_timestamp,
        )
        if self.data_gap:
            if self.is_complete or any(value is not None for value in values):
                raise ValueError("data-gap bars must be incomplete and must not contain zero fills")
            return self
        if self.no_trade:
            expected_none = (
                self.open,
                self.high,
                self.low,
                self.close,
                self.vwap,
                self.first_trade_timestamp,
                self.last_trade_timestamp,
            )
            if not self.is_complete or any(value is not None for value in expected_none):
                raise ValueError("no-trade bars are complete but have no fabricated prices")
            if (
                self.volume != Decimal(0)
                or self.quote_volume != Decimal(0)
                or self.trade_count != 0
                or self.aggressive_buy_volume != Decimal(0)
                or self.aggressive_sell_volume != Decimal(0)
            ):
                raise ValueError("no-trade bar volumes and count must be exact zero")
            return self

        if not self.is_complete or any(value is None for value in values):
            raise ValueError("traded bars require complete OHLCV and timing fields")
        assert self.trade_count is not None
        assert self.volume is not None
        assert self.high is not None
        assert self.low is not None
        assert self.open is not None
        assert self.close is not None
        if self.trade_count < 1 or self.volume <= 0:
            raise ValueError("traded bars require positive volume and at least one trade")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC ordering is inconsistent")
        return self


def deterministic_bar_id(market: str, interval_seconds: int, start_utc: datetime) -> str:
    identity = f"{market}|{interval_seconds}|{start_utc.isoformat()}|bar-v1"
    return sha256(identity.encode()).hexdigest()[:32]

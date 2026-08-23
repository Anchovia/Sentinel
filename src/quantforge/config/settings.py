"""Typed configuration with fail-closed trading defaults."""

from enum import StrEnum
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PAPER = "paper"
    PRODUCTION = "production"


class TradingMode(StrEnum):
    BACKTEST = "backtest"
    REPLAY = "replay"
    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


class QuantForgeSettings(BaseSettings):
    """Application settings.

    No single option can enable live order submission. The runtime guard checks
    every live gate again at the execution boundary.
    """

    model_config = SettingsConfigDict(
        env_prefix="QF_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    environment: Environment = Environment.DEVELOPMENT
    trading_mode: TradingMode = TradingMode.PAPER

    allow_order_submission: bool = False
    live_release_manifest_valid: bool = False
    risk_policy_approved: bool = False
    model_release_approved: bool = False
    operator_unlock_present: bool = False

    database_url: str = "postgresql+asyncpg://quantforge:quantforge@localhost:5432/quantforge"
    log_level: str = "INFO"
    display_timezone: str = "Asia/Seoul"

    upbit_access_key: SecretStr | None = Field(default=None, repr=False)
    upbit_secret_key: SecretStr | None = Field(default=None, repr=False)

    @field_validator("display_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {value}") from exc
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"unsupported log level: {value}")
        return normalized

    @model_validator(mode="after")
    def require_complete_credential_pair(self) -> "QuantForgeSettings":
        has_access = self.upbit_access_key is not None
        has_secret = self.upbit_secret_key is not None
        if has_access != has_secret:
            raise ValueError("Upbit access and secret keys must be configured as a pair")
        return self


@lru_cache(maxsize=1)
def get_settings() -> QuantForgeSettings:
    """Return the process-wide immutable configuration snapshot."""

    return QuantForgeSettings()

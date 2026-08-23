"""Typed configuration with fail-closed trading defaults."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
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
    runtime_export_root: Path = Path("runtime_exports")
    operations_state_root: Path = Path("data/operations")
    paper_data_host_path: Path = Path("data/paper")
    paper_data_label: str = "local-paper-data"

    upbit_access_key: SecretStr | None = Field(default=None, repr=False)
    upbit_secret_key: SecretStr | None = Field(default=None, repr=False)
    dashboard_access_token: SecretStr | None = Field(default=None, repr=False)
    dashboard_csrf_secret: SecretStr | None = Field(default=None, repr=False)

    @field_validator(
        "upbit_access_key",
        "upbit_secret_key",
        "dashboard_access_token",
        "dashboard_csrf_secret",
        mode="before",
    )
    @classmethod
    def normalize_blank_secrets(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

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

    @field_validator("paper_data_label")
    @classmethod
    def validate_paper_data_label(cls, value: str) -> str:
        if not value.strip() or len(value) > 200 or any(ord(character) < 32 for character in value):
            raise ValueError("paper data label is invalid")
        return value

    @model_validator(mode="after")
    def require_complete_credential_pair(self) -> "QuantForgeSettings":
        has_access = self.upbit_access_key is not None
        has_secret = self.upbit_secret_key is not None
        if has_access != has_secret:
            raise ValueError("Upbit access and secret keys must be configured as a pair")
        has_dashboard_token = self.dashboard_access_token is not None
        has_csrf_secret = self.dashboard_csrf_secret is not None
        if has_dashboard_token != has_csrf_secret:
            raise ValueError("dashboard access and CSRF secrets must be configured as a pair")
        if self.dashboard_access_token is not None and self.dashboard_csrf_secret is not None:
            if len(self.dashboard_access_token.get_secret_value()) < 32:
                raise ValueError("dashboard access token must contain at least 32 characters")
            if len(self.dashboard_csrf_secret.get_secret_value()) < 32:
                raise ValueError("dashboard CSRF secret must contain at least 32 characters")
        return self


@lru_cache(maxsize=1)
def get_settings() -> QuantForgeSettings:
    """Return the process-wide immutable configuration snapshot."""

    return QuantForgeSettings()

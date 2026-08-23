"""Typed loader for the reviewed Upbit capability manifest."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConnectionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    idle_timeout_seconds: int = Field(gt=0)
    ping_interval_seconds: int = Field(gt=0)
    ping_timeout_seconds: int = Field(gt=0)
    open_timeout_seconds: int = Field(gt=0)
    close_timeout_seconds: int = Field(gt=0)
    reconnect_backoff_initial_seconds: int = Field(gt=0)
    reconnect_backoff_max_seconds: int = Field(gt=0)
    reconnect_jitter_ratio: str


class PublicWebSocketCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    enabled: bool
    authentication: Literal["none"]
    endpoint: str = Field(pattern=r"^wss://")
    format: Literal["DEFAULT"]
    connection_policy: ConnectionPolicy


class DisabledCapability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    enabled: Literal[False]
    reason: str = Field(min_length=1)


class PublicRestCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    enabled: Literal[True]
    authentication: Literal["none"]
    base_url: str = Field(pattern=r"^https://")
    startup_only: Literal[True]
    credentials_sent: Literal[False]
    order_capability: Literal[False]


class UpbitCapabilityManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    schema_version: int = Field(ge=1)
    exchange: Literal["upbit"]
    source_snapshot: str
    public_websocket: PublicWebSocketCapabilities
    public_rest: PublicRestCapabilities
    private_websocket: DisabledCapability
    rest_api: DisabledCapability

    @model_validator(mode="after")
    def require_public_only(self) -> "UpbitCapabilityManifest":
        if not self.public_websocket.enabled:
            raise ValueError("Phase 1 requires the reviewed public WebSocket capability")
        if not self.public_rest.enabled:
            raise ValueError("all-KRW discovery requires reviewed credential-free public REST")
        return self


def load_upbit_capabilities(path: Path) -> UpbitCapabilityManifest:
    """Load only local reviewed YAML; this function never fetches remote content."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("capability manifest root must be a mapping")
    return UpbitCapabilityManifest.model_validate(raw)

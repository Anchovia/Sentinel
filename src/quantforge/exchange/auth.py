"""Secret-isolated authenticated-request contracts; no credential source is implemented."""

from collections.abc import Sequence
from hashlib import sha512
from typing import Protocol
from urllib.parse import unquote, urlencode
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class AuthenticatedCapabilityDisabled(RuntimeError):
    """Raised when a private capability is intentionally unavailable."""


def build_query_string(parameters: Sequence[tuple[str, str]]) -> str:
    """Preserve parameter order and repeated keys exactly as reviewed in Upbit docs."""

    if any(not key for key, _ in parameters):
        raise ValueError("authenticated parameter names cannot be empty")
    return unquote(urlencode(list(parameters), doseq=True))


class AuthRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: str = Field(pattern=r"^(GET|POST|DELETE)$")
    path: str = Field(pattern=r"^/v1/[a-z0-9/_-]+$")
    nonce: UUID
    ordered_parameters: tuple[tuple[str, str], ...] = ()

    @field_validator("ordered_parameters")
    @classmethod
    def validate_parameters(
        cls, values: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        if any(not key for key, _ in values):
            raise ValueError("authenticated parameter names cannot be empty")
        return values

    @property
    def query_string(self) -> str:
        return build_query_string(self.ordered_parameters)

    @property
    def query_hash(self) -> str | None:
        if not self.query_string:
            return None
        return sha512(self.query_string.encode("utf-8")).hexdigest()


class AuthorizationHeader(BaseModel):
    """Opaque header value whose representation never reveals the bearer token."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: SecretStr = Field(repr=False)

    @property
    def redacted(self) -> str:
        return "Bearer ***"


class AuthorizationProvider(Protocol):
    """Implemented by a separately injected Secret-owning boundary in a future phase."""

    async def create_header(self, request: AuthRequest) -> AuthorizationHeader: ...


class DisabledAuthorizationProvider:
    async def create_header(self, request: AuthRequest) -> AuthorizationHeader:
        del request
        raise AuthenticatedCapabilityDisabled("authenticated signing is disabled")

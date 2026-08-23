"""Structured log redaction for secrets and authorization material."""

import re
from collections.abc import Mapping, Sequence
from typing import Final

REDACTED: Final = "[REDACTED]"

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "apikey",
        "access_key",
        "secret",
        "secret_key",
        "jwt",
        "token",
        "password",
        "request_signature",
    }
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+\-/]+=*")
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith("_secret")


def _redact_text(value: str) -> str:
    value = _BEARER_PATTERN.sub(REDACTED, value)
    return _JWT_PATTERN.sub(REDACTED, value)


def redact(value: object) -> object:
    """Return a recursively redacted copy suitable for logs and runtime exports."""

    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_sensitive_key(key) else redact(item) for key, item in value.items()
        }
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact(item) for item in value]
    return value

"""Atomic, redacted runtime exports outside the production data plane."""

import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import uuid4

import orjson

from quantforge.operations.models import DashboardSnapshot

_SENSITIVE_NAMES = frozenset(
    {
        "authorization",
        "api_key",
        "access_key",
        "secret",
        "secret_key",
        "jwt",
        "token",
        "password",
        "request_signature",
        "account_uuid",
    }
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+\-/]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


class UnsafeRuntimeExport(ValueError):
    """Raised when an export contains credential-shaped material."""


def assert_runtime_export_safe(value: object, *, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _SENSITIVE_NAMES or normalized.endswith("_secret"):
                raise UnsafeRuntimeExport(f"sensitive field is forbidden at {path}.{key}")
            assert_runtime_export_safe(item, path=f"{path}.{key}")
        return
    if isinstance(value, str):
        if _BEARER.search(value) or _JWT.search(value):
            raise UnsafeRuntimeExport(f"credential-shaped text is forbidden at {path}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for index, item in enumerate(value):
            assert_runtime_export_safe(item, path=f"{path}[{index}]")


def write_dashboard_snapshot(snapshot: DashboardSnapshot, output_root: Path) -> Path:
    payload = snapshot.model_dump(mode="json")
    assert_runtime_export_safe(payload)
    destination_dir = output_root / "ops"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "dashboard.json"
    temporary = destination_dir / f".dashboard.{uuid4().hex}.tmp"
    encoded = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def read_dashboard_snapshot(path: Path) -> DashboardSnapshot:
    payload = orjson.loads(path.read_bytes())
    assert_runtime_export_safe(payload)
    return DashboardSnapshot.model_validate(payload)

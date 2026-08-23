"""Secret-rejecting readiness input loading and atomic report export."""

import os
from pathlib import Path
from uuid import uuid4

import orjson
import yaml

from quantforge.operations.exports import assert_runtime_export_safe
from quantforge.readiness.models import ReadinessEvidence, ReadinessPolicy, ReadinessReport


def load_readiness_evidence(path: Path) -> ReadinessEvidence:
    payload: object = orjson.loads(path.read_bytes())
    assert_runtime_export_safe(payload)
    return ReadinessEvidence.model_validate(payload)


def load_readiness_policy(path: Path) -> ReadinessPolicy:
    payload: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert_runtime_export_safe(payload)
    return ReadinessPolicy.model_validate(payload)


def write_readiness_report(report: ReadinessReport, output_root: Path) -> Path:
    payload = report.model_dump(mode="json")
    assert_runtime_export_safe(payload)
    destination_dir = output_root / "readiness"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "latest.json"
    temporary = destination_dir / f".readiness.{uuid4().hex}.tmp"
    encoded = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def read_readiness_report(path: Path) -> ReadinessReport:
    payload: object = orjson.loads(path.read_bytes())
    assert_runtime_export_safe(payload)
    return ReadinessReport.model_validate(payload)

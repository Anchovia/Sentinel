"""Checksummed atomic persistence for replay checkpoints."""

import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import orjson

from quantforge.replay.engine import ReplayCheckpoint


def save_checkpoint(checkpoint: ReplayCheckpoint, path: Path) -> None:
    payload = orjson.dumps(checkpoint.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    envelope = (
        orjson.dumps(
            {"checkpoint": orjson.loads(payload), "sha256": sha256(payload).hexdigest()},
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(envelope)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_checkpoint(path: Path) -> ReplayCheckpoint:
    try:
        envelope = orjson.loads(path.read_bytes())
        raw_checkpoint = envelope["checkpoint"]
        expected = envelope["sha256"]
    except (KeyError, TypeError, orjson.JSONDecodeError) as exc:
        raise ValueError("checkpoint envelope is malformed") from exc
    payload = orjson.dumps(raw_checkpoint, option=orjson.OPT_SORT_KEYS)
    if not isinstance(expected, str) or sha256(payload).hexdigest() != expected:
        raise ValueError("checkpoint checksum mismatch")
    return ReplayCheckpoint.model_validate(raw_checkpoint)

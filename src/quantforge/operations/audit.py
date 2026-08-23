"""Fsynced hash-chain audit records for consequential operator activity."""

import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.domain import deterministic_execution_id
from quantforge.security import redact

ZERO_HASH = "0" * 64


class AuditIntegrityError(ValueError):
    """Raised when an audit chain cannot be trusted."""


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: Annotated[int, Field(ge=1)]
    event_id: UUID
    occurred_at_utc: datetime
    actor_ref: str = Field(pattern=r"^[a-f0-9]{16}$")
    action: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=160)
    outcome: str = Field(min_length=1, max_length=40)
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    details: tuple[tuple[str, str], ...] = ()
    previous_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("occurred_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("audit timestamp must be UTC-aware")
        return value

    @field_validator("details")
    @classmethod
    def require_canonical_details(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        names = tuple(name for name, _ in value)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("audit details must have sorted unique names")
        return value


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._events: list[AuditEvent] = []
        if path is not None and path.exists():
            self._load()

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def append(
        self,
        *,
        occurred_at_utc: datetime,
        actor_ref: str,
        action: str,
        target: str,
        outcome: str,
        request_fingerprint: str,
        idempotency_key: str,
        details: tuple[tuple[str, str], ...] = (),
    ) -> AuditEvent:
        sequence = len(self._events) + 1
        previous_hash = self._events[-1].event_hash if self._events else ZERO_HASH
        values = {
            "sequence": sequence,
            "event_id": deterministic_execution_id(
                "operations-audit", sequence, request_fingerprint, outcome, previous_hash
            ),
            "occurred_at_utc": occurred_at_utc,
            "actor_ref": actor_ref,
            "action": action,
            "target": target,
            "outcome": outcome,
            "request_fingerprint": request_fingerprint,
            "idempotency_key_hash": sha256(idempotency_key.encode()).hexdigest(),
            "details": tuple(
                sorted(
                    (str(redact(name))[:80], str(redact(value))[:500]) for name, value in details
                )
            ),
            "previous_hash": previous_hash,
        }
        event = AuditEvent(**values, event_hash=self._hash_values(values))
        if self.path is not None:
            self._persist(event)
        self._events.append(event)
        return event

    def verify(self) -> None:
        previous_hash = ZERO_HASH
        for sequence, event in enumerate(self._events, start=1):
            if event.sequence != sequence or event.previous_hash != previous_hash:
                raise AuditIntegrityError("audit sequence/hash link is invalid")
            if event.event_hash != self._hash_event(event):
                raise AuditIntegrityError("audit event hash is invalid")
            previous_hash = event.event_hash

    def _persist(self, event: AuditEvent) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as handle:
            handle.write(
                orjson.dumps(event.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS) + b"\n"
            )
            handle.flush()
            os.fsync(handle.fileno())

    def _load(self) -> None:
        assert self.path is not None
        try:
            self._events = [
                AuditEvent.model_validate(orjson.loads(line))
                for line in self.path.read_bytes().splitlines()
            ]
            self.verify()
        except (OSError, orjson.JSONDecodeError, ValueError) as exc:
            if isinstance(exc, AuditIntegrityError):
                raise
            raise AuditIntegrityError("audit log could not be safely loaded") from exc

    @staticmethod
    def _hash_values(values: dict[str, object]) -> str:
        return sha256(orjson.dumps(values, option=orjson.OPT_SORT_KEYS, default=str)).hexdigest()

    @classmethod
    def _hash_event(cls, event: AuditEvent) -> str:
        return cls._hash_values(event.model_dump(exclude={"event_hash"}))

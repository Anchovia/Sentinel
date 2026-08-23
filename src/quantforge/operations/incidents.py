"""Append-only incident lifecycle with redacted evidence and integrity checks."""

import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.domain import deterministic_execution_id
from quantforge.operations.models import IncidentStatus, IncidentView
from quantforge.security import redact

ZERO_HASH = "0" * 64


class IncidentIntegrityError(ValueError):
    """Raised when incident evidence is damaged or contradictory."""


class IncidentEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: Annotated[int, Field(ge=1)]
    event_id: UUID
    occurred_at_utc: datetime
    mutation: str = Field(pattern=r"^(OPENED|ACKNOWLEDGED|RESOLVED)$")
    actor_ref: str = Field(pattern=r"^[a-f0-9]{16}$")
    incident: IncidentView
    previous_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("occurred_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("incident event timestamp must be UTC-aware")
        return value


class IncidentStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._events: list[IncidentEvent] = []
        self._current: dict[str, IncidentView] = {}
        if path is not None and path.exists():
            self._load()

    @property
    def events(self) -> tuple[IncidentEvent, ...]:
        return tuple(self._events)

    def list_current(self) -> tuple[IncidentView, ...]:
        return tuple(sorted(self._current.values(), key=lambda item: item.incident_id))

    def get(self, incident_id: str) -> IncidentView | None:
        return self._current.get(incident_id)

    def open(self, incident: IncidentView, *, actor_ref: str) -> IncidentEvent:
        if incident.incident_id in self._current:
            raise IncidentIntegrityError("incident identifier already exists")
        if incident.status is not IncidentStatus.OPEN:
            raise IncidentIntegrityError("new incident must be OPEN")
        sanitized = self._sanitize(incident)
        return self._append("OPENED", sanitized, actor_ref, incident.opened_at_utc)

    def acknowledge(
        self, incident_id: str, *, actor_ref: str, occurred_at_utc: datetime
    ) -> IncidentEvent:
        current = self._require_current(incident_id)
        if current.status is not IncidentStatus.OPEN:
            raise IncidentIntegrityError("only an OPEN incident can be acknowledged")
        updated = current.model_copy(
            update={"status": IncidentStatus.ACKNOWLEDGED, "owner": actor_ref}
        )
        return self._append("ACKNOWLEDGED", updated, actor_ref, occurred_at_utc)

    def resolve(
        self,
        incident_id: str,
        *,
        actor_ref: str,
        resolution: str,
        occurred_at_utc: datetime,
    ) -> IncidentEvent:
        current = self._require_current(incident_id)
        if current.status is IncidentStatus.RESOLVED:
            raise IncidentIntegrityError("incident is already resolved")
        if (
            current.severity.value == "CRITICAL"
            and current.status is not IncidentStatus.ACKNOWLEDGED
        ):
            raise IncidentIntegrityError("critical incident must be acknowledged before resolution")
        updated = current.model_copy(
            update={
                "status": IncidentStatus.RESOLVED,
                "owner": actor_ref,
                "resolution": str(redact(resolution))[:500],
            }
        )
        return self._append("RESOLVED", updated, actor_ref, occurred_at_utc)

    def verify(self) -> None:
        previous_hash = ZERO_HASH
        current: dict[str, IncidentView] = {}
        latest_times: dict[str, datetime] = {}
        for sequence, event in enumerate(self._events, start=1):
            if event.sequence != sequence or event.previous_hash != previous_hash:
                raise IncidentIntegrityError("incident sequence/hash link is invalid")
            if event.event_hash != self._hash_event(event):
                raise IncidentIntegrityError("incident event hash is invalid")
            prior = current.get(event.incident.incident_id)
            if prior is None:
                if event.mutation != "OPENED" or event.incident.status is not IncidentStatus.OPEN:
                    raise IncidentIntegrityError("incident history has no OPENED event")
            else:
                if event.occurred_at_utc < latest_times[event.incident.incident_id]:
                    raise IncidentIntegrityError("incident history time moved backwards")
                if event.incident.opened_at_utc != prior.opened_at_utc:
                    raise IncidentIntegrityError("incident opening identity changed")
                expected = {
                    "ACKNOWLEDGED": IncidentStatus.ACKNOWLEDGED,
                    "RESOLVED": IncidentStatus.RESOLVED,
                }.get(event.mutation)
                if expected is None or event.incident.status is not expected:
                    raise IncidentIntegrityError("incident mutation and status disagree")
                if prior.status is IncidentStatus.RESOLVED:
                    raise IncidentIntegrityError("resolved incident history cannot continue")
                if event.mutation == "ACKNOWLEDGED" and prior.status is not IncidentStatus.OPEN:
                    raise IncidentIntegrityError("incident acknowledgement transition is invalid")
            current[event.incident.incident_id] = event.incident
            latest_times[event.incident.incident_id] = event.occurred_at_utc
            previous_hash = event.event_hash

    def _require_current(self, incident_id: str) -> IncidentView:
        current = self._current.get(incident_id)
        if current is None:
            raise IncidentIntegrityError("incident does not exist")
        return current

    @staticmethod
    def _sanitize(incident: IncidentView) -> IncidentView:
        evidence = tuple(
            sorted((str(name)[:80], str(redact(value))[:500]) for name, value in incident.evidence)
        )
        return incident.model_copy(
            update={
                "category": str(redact(incident.category))[:80],
                "component": str(redact(incident.component))[:80],
                "summary": str(redact(incident.summary))[:500],
                "evidence": evidence,
                "automatic_actions": tuple(
                    str(redact(item))[:160] for item in incident.automatic_actions
                ),
                "model_versions": tuple(
                    (str(redact(name))[:80], str(redact(version))[:160])
                    for name, version in incident.model_versions
                ),
                "owner": str(redact(incident.owner))[:80] if incident.owner else None,
                "resolution": (
                    str(redact(incident.resolution))[:500] if incident.resolution else None
                ),
            }
        )

    def _append(
        self,
        mutation: str,
        incident: IncidentView,
        actor_ref: str,
        occurred_at_utc: datetime,
    ) -> IncidentEvent:
        sequence = len(self._events) + 1
        previous_hash = self._events[-1].event_hash if self._events else ZERO_HASH
        values = {
            "sequence": sequence,
            "event_id": deterministic_execution_id(
                "incident", sequence, incident.incident_id, mutation, previous_hash
            ),
            "occurred_at_utc": occurred_at_utc,
            "mutation": mutation,
            "actor_ref": actor_ref,
            "incident": incident,
            "previous_hash": previous_hash,
        }
        event = IncidentEvent(**values, event_hash=self._hash_values(values))
        if self.path is not None:
            self._persist(event)
        self._events.append(event)
        self._current[incident.incident_id] = incident
        return event

    def _persist(self, event: IncidentEvent) -> None:
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
                IncidentEvent.model_validate(orjson.loads(line))
                for line in self.path.read_bytes().splitlines()
            ]
            self.verify()
        except (OSError, orjson.JSONDecodeError, ValueError) as exc:
            if isinstance(exc, IncidentIntegrityError):
                raise
            raise IncidentIntegrityError("incident log could not be safely loaded") from exc
        self._current = {event.incident.incident_id: event.incident for event in self._events}

    @staticmethod
    def _hash_values(values: dict[str, object]) -> str:
        def serialize(value: object) -> object:
            if isinstance(value, BaseModel):
                return value.model_dump(mode="python")
            return str(value)

        return sha256(
            orjson.dumps(values, option=orjson.OPT_SORT_KEYS, default=serialize)
        ).hexdigest()

    @classmethod
    def _hash_event(cls, event: IncidentEvent) -> str:
        return cls._hash_values(event.model_dump(exclude={"event_hash"}))

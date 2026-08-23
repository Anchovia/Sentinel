"""Confirmed, idempotent emergency-control request boundary with no order transport."""

import os
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Protocol
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.domain import deterministic_execution_id
from quantforge.operations.audit import AuditLog
from quantforge.operations.incidents import IncidentStore
from quantforge.risk import KillSwitch, KillSwitchMode
from quantforge.security import redact

ZERO_HASH = "0" * 64


class ControlAction(StrEnum):
    ACTIVATE_CANCEL_ONLY = "activate_cancel_only"
    PAUSE_STRATEGY_REQUEST = "pause_strategy_request"
    ACKNOWLEDGE_INCIDENT = "acknowledge_incident"
    CANCEL_ALL_ORDERS_REQUEST = "cancel_all_orders_request"


CONFIRMATIONS = {
    ControlAction.ACTIVATE_CANCEL_ONLY: "CONFIRM ACTIVATE CANCEL ONLY",
    ControlAction.PAUSE_STRATEGY_REQUEST: "CONFIRM PAUSE STRATEGY",
    ControlAction.ACKNOWLEDGE_INCIDENT: "CONFIRM ACKNOWLEDGE INCIDENT",
    ControlAction.CANCEL_ALL_ORDERS_REQUEST: "CONFIRM REQUEST CANCEL ALL",
}


class ControlStatus(StrEnum):
    REQUESTED = "REQUESTED"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ControlRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ControlAction
    target: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=500)
    confirmation: str = Field(min_length=1, max_length=80)

    @field_validator("target", "reason")
    @classmethod
    def redact_untrusted_text(cls, value: str) -> str:
        return str(redact(value))

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(exclude={"confirmation"}, mode="json")
        return sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()

    def verify_confirmation(self) -> None:
        if self.confirmation != CONFIRMATIONS[self.action]:
            raise ValueError("explicit confirmation phrase does not match the requested action")


class ControlRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: Annotated[int, Field(ge=1)]
    record_id: UUID
    occurred_at_utc: datetime
    actor_ref: str = Field(pattern=r"^[a-f0-9]{16}$")
    action: ControlAction
    target: str
    reason: str
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ControlStatus
    result_code: str = Field(min_length=1, max_length=80)
    effect_verified: bool
    network_used: bool = False
    previous_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("occurred_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("control timestamp must be UTC-aware")
        return value


class ControlExecution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ControlStatus
    result_code: str
    effect_verified: bool
    network_used: bool = False


class ControlExecutor(Protocol):
    def execute(
        self, request: ControlRequest, *, actor_ref: str, occurred_at_utc: datetime
    ) -> ControlExecution: ...


class LocalSafetyControlExecutor:
    """Applies only local safety state or records a proposal; it cannot reach an exchange."""

    network_capability = False

    def __init__(self, kill_switch: KillSwitch, incidents: IncidentStore) -> None:
        self.kill_switch = kill_switch
        self.incidents = incidents

    def execute(
        self, request: ControlRequest, *, actor_ref: str, occurred_at_utc: datetime
    ) -> ControlExecution:
        if request.action is ControlAction.ACTIVATE_CANCEL_ONLY:
            if self.kill_switch.active:
                return ControlExecution(
                    status=ControlStatus.VERIFIED,
                    result_code="KILL_SWITCH_ALREADY_ACTIVE",
                    effect_verified=True,
                )
            self.kill_switch.activate(
                KillSwitchMode.CANCEL_ONLY,
                reason=request.reason,
                occurred_at_utc=occurred_at_utc,
            )
            return ControlExecution(
                status=ControlStatus.VERIFIED,
                result_code="LOCAL_CANCEL_ONLY_ACTIVE",
                effect_verified=self.kill_switch.active,
            )
        if request.action is ControlAction.ACKNOWLEDGE_INCIDENT:
            event = self.incidents.acknowledge(
                request.target, actor_ref=actor_ref, occurred_at_utc=occurred_at_utc
            )
            return ControlExecution(
                status=ControlStatus.VERIFIED,
                result_code="INCIDENT_ACKNOWLEDGED",
                effect_verified=event.incident.status.value == "ACKNOWLEDGED",
            )
        if request.action is ControlAction.PAUSE_STRATEGY_REQUEST:
            return ControlExecution(
                status=ControlStatus.VERIFIED,
                result_code="STRATEGY_PAUSE_REQUEST_RECORDED",
                effect_verified=False,
            )
        return ControlExecution(
            status=ControlStatus.BLOCKED,
            result_code="ORDER_CANCELLATION_TRANSPORT_UNAVAILABLE",
            effect_verified=False,
        )


class ControlJournal:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._records: list[ControlRecord] = []
        if path is not None and path.exists():
            self._load()

    @property
    def records(self) -> tuple[ControlRecord, ...]:
        return tuple(self._records)

    def find_by_key_hash(self, key_hash: str) -> tuple[ControlRecord, ...]:
        return tuple(record for record in self._records if record.idempotency_key_hash == key_hash)

    def append(
        self,
        *,
        request: ControlRequest,
        actor_ref: str,
        idempotency_key: str,
        status: ControlStatus,
        result_code: str,
        effect_verified: bool,
        network_used: bool,
        occurred_at_utc: datetime,
    ) -> ControlRecord:
        sequence = len(self._records) + 1
        previous_hash = self._records[-1].record_hash if self._records else ZERO_HASH
        values = {
            "sequence": sequence,
            "record_id": deterministic_execution_id(
                "control", sequence, request.fingerprint, status, previous_hash
            ),
            "occurred_at_utc": occurred_at_utc,
            "actor_ref": actor_ref,
            "action": request.action,
            "target": request.target,
            "reason": request.reason,
            "request_fingerprint": request.fingerprint,
            "idempotency_key_hash": sha256(idempotency_key.encode()).hexdigest(),
            "status": status,
            "result_code": result_code,
            "effect_verified": effect_verified,
            "network_used": network_used,
            "previous_hash": previous_hash,
        }
        record = ControlRecord(**values, record_hash=self._hash_values(values))
        if self.path is not None:
            self._persist(record)
        self._records.append(record)
        return record

    def verify(self) -> None:
        previous_hash = ZERO_HASH
        fingerprints: dict[str, str] = {}
        for sequence, record in enumerate(self._records, start=1):
            if record.sequence != sequence or record.previous_hash != previous_hash:
                raise ValueError("control journal sequence/hash link is invalid")
            if record.record_hash != self._hash_record(record):
                raise ValueError("control journal record hash is invalid")
            prior = fingerprints.setdefault(record.idempotency_key_hash, record.request_fingerprint)
            if prior != record.request_fingerprint:
                raise ValueError("idempotency key is bound to conflicting requests")
            if record.network_used:
                raise ValueError("Phase 7 control journal cannot record network use")
            previous_hash = record.record_hash

    def _persist(self, record: ControlRecord) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as handle:
            handle.write(
                orjson.dumps(record.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS) + b"\n"
            )
            handle.flush()
            os.fsync(handle.fileno())

    def _load(self) -> None:
        assert self.path is not None
        try:
            self._records = [
                ControlRecord.model_validate(orjson.loads(line))
                for line in self.path.read_bytes().splitlines()
            ]
            self.verify()
        except (OSError, orjson.JSONDecodeError, ValueError) as exc:
            raise ValueError("control journal could not be safely loaded") from exc

    @staticmethod
    def _hash_values(values: dict[str, object]) -> str:
        return sha256(orjson.dumps(values, option=orjson.OPT_SORT_KEYS, default=str)).hexdigest()

    @classmethod
    def _hash_record(cls, record: ControlRecord) -> str:
        return cls._hash_values(record.model_dump(exclude={"record_hash"}))


class EmergencyControlService:
    def __init__(
        self,
        journal: ControlJournal,
        audit_log: AuditLog,
        executor: ControlExecutor,
    ) -> None:
        self.journal = journal
        self.audit_log = audit_log
        self.executor = executor

    def submit(
        self,
        request: ControlRequest,
        *,
        actor_ref: str,
        idempotency_key: str,
        occurred_at_utc: datetime,
    ) -> ControlRecord:
        request.verify_confirmation()
        if not idempotency_key or len(idempotency_key) > 160:
            raise ValueError("a bounded idempotency key is required")
        key_hash = sha256(idempotency_key.encode()).hexdigest()
        existing = self.journal.find_by_key_hash(key_hash)
        if existing:
            if existing[0].request_fingerprint != request.fingerprint:
                raise ValueError("idempotency key is already bound to a different request")
            final = existing[-1]
            if final.status is ControlStatus.REQUESTED:
                recovered = self.journal.append(
                    request=request,
                    actor_ref=actor_ref,
                    idempotency_key=idempotency_key,
                    status=ControlStatus.UNKNOWN,
                    result_code="INTERRUPTED_REQUEST_REQUIRES_RECONCILIATION",
                    effect_verified=False,
                    network_used=False,
                    occurred_at_utc=occurred_at_utc,
                )
                self._audit(
                    request,
                    actor_ref,
                    idempotency_key,
                    ControlStatus.UNKNOWN,
                    occurred_at_utc,
                )
                return recovered
            return final

        self.journal.append(
            request=request,
            actor_ref=actor_ref,
            idempotency_key=idempotency_key,
            status=ControlStatus.REQUESTED,
            result_code="REQUEST_ACCEPTED",
            effect_verified=False,
            network_used=False,
            occurred_at_utc=occurred_at_utc,
        )
        self._audit(request, actor_ref, idempotency_key, "REQUESTED", occurred_at_utc)
        try:
            execution = self.executor.execute(
                request, actor_ref=actor_ref, occurred_at_utc=occurred_at_utc
            )
            if execution.network_used:
                raise RuntimeError("Phase 7 control executor attempted network use")
        except Exception:
            execution = ControlExecution(
                status=ControlStatus.UNKNOWN,
                result_code="CONTROL_RESULT_UNKNOWN",
                effect_verified=False,
            )
        final = self.journal.append(
            request=request,
            actor_ref=actor_ref,
            idempotency_key=idempotency_key,
            status=execution.status,
            result_code=execution.result_code,
            effect_verified=execution.effect_verified,
            network_used=False,
            occurred_at_utc=occurred_at_utc,
        )
        self._audit(request, actor_ref, idempotency_key, execution.status, occurred_at_utc)
        return final

    def _audit(
        self,
        request: ControlRequest,
        actor_ref: str,
        idempotency_key: str,
        outcome: str,
        occurred_at_utc: datetime,
    ) -> None:
        self.audit_log.append(
            occurred_at_utc=occurred_at_utc,
            actor_ref=actor_ref,
            action=request.action,
            target=request.target,
            outcome=outcome,
            request_fingerprint=request.fingerprint,
            idempotency_key=idempotency_key,
        )

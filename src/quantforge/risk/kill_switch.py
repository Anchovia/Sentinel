"""Manually released, hash-chained emergency stop state."""

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Annotated
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.domain import deterministic_execution_id

ZERO_HASH = "0" * 64


class KillSwitchMode(StrEnum):
    CANCEL_ONLY = "cancel_only"
    CANCEL_AND_FLATTEN = "cancel_and_flatten"


class KillSwitchState(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    RELEASE_PENDING = "release_pending"


class KillSwitchAction(StrEnum):
    ACTIVATE = "activate"
    RELEASE_REQUESTED = "release_requested"
    RELEASE_BLOCKED = "release_blocked"
    RELEASED = "released"


class KillSwitchEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: Annotated[int, Field(ge=1)]
    event_id: UUID
    occurred_at_utc: datetime
    action: KillSwitchAction
    state: KillSwitchState
    mode: KillSwitchMode
    reason: str = Field(min_length=1)
    operator_approval_id: str | None = None
    liquidity_safe: bool
    reconciliation_ok: bool | None = None
    previous_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("occurred_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("kill-switch timestamps must be UTC-aware")
        return value


class KillSwitch:
    """Emergency stop with no automatic release or unapproved flatten path."""

    def __init__(self) -> None:
        self._state = KillSwitchState.INACTIVE
        self._mode: KillSwitchMode | None = None
        self._events: list[KillSwitchEvent] = []

    @property
    def state(self) -> KillSwitchState:
        return self._state

    @property
    def active(self) -> bool:
        return self._state is not KillSwitchState.INACTIVE

    @property
    def events(self) -> tuple[KillSwitchEvent, ...]:
        return tuple(self._events)

    def activate(
        self,
        mode: KillSwitchMode,
        *,
        reason: str,
        occurred_at_utc: datetime,
        operator_approval_id: str | None = None,
        liquidity_safe: bool = False,
    ) -> KillSwitchEvent:
        if self.active:
            raise ValueError("kill switch is already active")
        if mode is KillSwitchMode.CANCEL_AND_FLATTEN and (
            not operator_approval_id or not liquidity_safe
        ):
            raise ValueError("flatten requires operator approval and a liquidity-safe assessment")
        self._state = KillSwitchState.ACTIVE
        self._mode = mode
        return self._append(
            action=KillSwitchAction.ACTIVATE,
            state=self._state,
            mode=mode,
            reason=reason,
            occurred_at_utc=occurred_at_utc,
            operator_approval_id=operator_approval_id,
            liquidity_safe=liquidity_safe,
        )

    def request_release(
        self, *, operator_approval_id: str, occurred_at_utc: datetime
    ) -> KillSwitchEvent:
        if self._state is not KillSwitchState.ACTIVE or self._mode is None:
            raise ValueError("only an active kill switch can request release")
        if not operator_approval_id:
            raise ValueError("manual operator approval is required")
        self._state = KillSwitchState.RELEASE_PENDING
        return self._append(
            action=KillSwitchAction.RELEASE_REQUESTED,
            state=self._state,
            mode=self._mode,
            reason="MANUAL_RELEASE_REQUESTED",
            occurred_at_utc=occurred_at_utc,
            operator_approval_id=operator_approval_id,
            liquidity_safe=False,
        )

    def complete_release(
        self, *, reconciliation_ok: bool, occurred_at_utc: datetime
    ) -> KillSwitchEvent:
        if self._state is not KillSwitchState.RELEASE_PENDING or self._mode is None:
            raise ValueError("release must be manually requested first")
        if not reconciliation_ok:
            return self._append(
                action=KillSwitchAction.RELEASE_BLOCKED,
                state=self._state,
                mode=self._mode,
                reason="RELEASE_BLOCKED_RECONCILIATION",
                occurred_at_utc=occurred_at_utc,
                operator_approval_id=None,
                liquidity_safe=False,
                reconciliation_ok=False,
            )
        mode = self._mode
        event = self._append(
            action=KillSwitchAction.RELEASED,
            state=KillSwitchState.INACTIVE,
            mode=mode,
            reason="MANUAL_RELEASE_RECONCILED",
            occurred_at_utc=occurred_at_utc,
            operator_approval_id=None,
            liquidity_safe=False,
            reconciliation_ok=True,
        )
        self._state = KillSwitchState.INACTIVE
        self._mode = None
        return event

    def verify_chain(self) -> bool:
        previous_hash = ZERO_HASH
        for sequence, event in enumerate(self._events, start=1):
            if event.sequence != sequence or event.previous_hash != previous_hash:
                return False
            if event.event_hash != self._hash_event(event):
                return False
            previous_hash = event.event_hash
        return True

    def _append(
        self,
        *,
        action: KillSwitchAction,
        state: KillSwitchState,
        mode: KillSwitchMode,
        reason: str,
        occurred_at_utc: datetime,
        operator_approval_id: str | None,
        liquidity_safe: bool,
        reconciliation_ok: bool | None = None,
    ) -> KillSwitchEvent:
        sequence = len(self._events) + 1
        previous_hash = self._events[-1].event_hash if self._events else ZERO_HASH
        values = {
            "sequence": sequence,
            "event_id": deterministic_execution_id(
                "kill-switch", sequence, occurred_at_utc, action, reason, previous_hash
            ),
            "occurred_at_utc": occurred_at_utc,
            "action": action,
            "state": state,
            "mode": mode,
            "reason": reason,
            "operator_approval_id": operator_approval_id,
            "liquidity_safe": liquidity_safe,
            "reconciliation_ok": reconciliation_ok,
            "previous_hash": previous_hash,
        }
        event_hash = self._hash_values(values)
        event = KillSwitchEvent(**values, event_hash=event_hash)
        self._events.append(event)
        return event

    @staticmethod
    def _hash_values(values: dict[str, object]) -> str:
        payload = orjson.dumps(values, option=orjson.OPT_SORT_KEYS, default=str)
        return sha256(payload).hexdigest()

    @classmethod
    def _hash_event(cls, event: KillSwitchEvent) -> str:
        return cls._hash_values(event.model_dump(exclude={"event_hash"}))

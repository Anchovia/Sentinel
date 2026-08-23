"""Durable append-only order-state journal with identifier burn semantics."""

import os
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Annotated
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import (
    ExchangeOrderRequest,
    OrderStateMachine,
    OrderStatus,
    deterministic_execution_id,
)

ZERO_HASH = "0" * 64


class OrderJournalIntegrityError(ValueError):
    """Raised when persistence, identity, or state evidence is unsafe."""


class JournalSource(StrEnum):
    LOCAL = "local"
    RISK = "risk"
    PREFLIGHT = "preflight"
    REST = "rest"
    PRIVATE_STREAM = "private_stream"
    RECONCILIATION = "reconciliation"
    RECOVERY = "recovery"


class ExecutionJournalEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: Annotated[int, Field(ge=1)]
    event_id: UUID
    intent_id: UUID
    risk_decision_id: UUID
    identifier: str = Field(min_length=1, max_length=64)
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    status: OrderStatus
    occurred_at_utc: datetime
    source: JournalSource
    exchange_order_id: UUID | None = None
    details: tuple[tuple[str, str], ...] = ()
    previous_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("occurred_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("order journal timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_details(self) -> "ExecutionJournalEvent":
        names = tuple(name for name, _ in self.details)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("order journal details must have sorted unique names")
        return self


class OrderJournal:
    """One durable source of local order identity and state."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._events: list[ExecutionJournalEvent] = []
        self._current: dict[str, ExecutionJournalEvent] = {}
        self._intent_identifiers: dict[UUID, str] = {}
        if path is not None and path.exists():
            self._load(path)

    @property
    def events(self) -> tuple[ExecutionJournalEvent, ...]:
        return tuple(self._events)

    @property
    def identifiers(self) -> tuple[str, ...]:
        return tuple(sorted(self._current))

    def current(self, identifier: str) -> ExecutionJournalEvent | None:
        return self._current.get(identifier)

    def by_intent(self, intent_id: UUID) -> ExecutionJournalEvent | None:
        identifier = self._intent_identifiers.get(intent_id)
        return self._current.get(identifier) if identifier is not None else None

    def register(
        self, request: ExchangeOrderRequest, *, occurred_at_utc: datetime
    ) -> ExecutionJournalEvent:
        existing_for_intent = self.by_intent(request.intent_id)
        if existing_for_intent is not None:
            if (
                existing_for_intent.identifier != request.identifier
                or existing_for_intent.risk_decision_id != request.risk_decision_id
                or existing_for_intent.market != request.market
            ):
                raise OrderJournalIntegrityError("intent cannot change its burned identity")
            return existing_for_intent
        existing_identifier = self.current(request.identifier)
        if existing_identifier is not None:
            raise OrderJournalIntegrityError("order identifier has already been used")
        if occurred_at_utc < request.requested_at_utc:
            raise OrderJournalIntegrityError("intent cannot be journaled before request time")
        return self._append(
            intent_id=request.intent_id,
            risk_decision_id=request.risk_decision_id,
            identifier=request.identifier,
            market=request.market,
            status=OrderStatus.INTENT_CREATED,
            occurred_at_utc=occurred_at_utc,
            source=JournalSource.LOCAL,
            exchange_order_id=None,
            details=(),
        )

    def transition(
        self,
        identifier: str,
        status: OrderStatus,
        *,
        occurred_at_utc: datetime,
        source: JournalSource,
        exchange_order_id: UUID | None = None,
        details: tuple[tuple[str, str], ...] = (),
    ) -> ExecutionJournalEvent:
        current = self.current(identifier)
        if current is None:
            raise OrderJournalIntegrityError("cannot transition an unregistered identifier")
        if occurred_at_utc < current.occurred_at_utc:
            raise OrderJournalIntegrityError("order journal time cannot move backwards")
        try:
            OrderStateMachine.transition(current.status, status)
        except ValueError as exc:
            raise OrderJournalIntegrityError(str(exc)) from exc
        return self._append(
            intent_id=current.intent_id,
            risk_decision_id=current.risk_decision_id,
            identifier=current.identifier,
            market=current.market,
            status=status,
            occurred_at_utc=occurred_at_utc,
            source=source,
            exchange_order_id=exchange_order_id or current.exchange_order_id,
            details=details,
        )

    def verify(self) -> None:
        previous_hash = ZERO_HASH
        current: dict[str, ExecutionJournalEvent] = {}
        intents: dict[UUID, str] = {}
        for sequence, event in enumerate(self._events, start=1):
            if event.sequence != sequence or event.previous_hash != previous_hash:
                raise OrderJournalIntegrityError("order journal sequence/hash link is invalid")
            if event.event_hash != self._hash_event(event):
                raise OrderJournalIntegrityError("order journal event hash is invalid")
            prior = current.get(event.identifier)
            if prior is None:
                if event.status is not OrderStatus.INTENT_CREATED:
                    raise OrderJournalIntegrityError("order journal identity has no intent event")
                if event.intent_id in intents:
                    raise OrderJournalIntegrityError("intent is linked to multiple identifiers")
                intents[event.intent_id] = event.identifier
            else:
                if (
                    prior.intent_id != event.intent_id
                    or prior.risk_decision_id != event.risk_decision_id
                    or prior.market != event.market
                ):
                    raise OrderJournalIntegrityError("order journal identity changed")
                if event.occurred_at_utc < prior.occurred_at_utc:
                    raise OrderJournalIntegrityError("order journal time moved backwards")
                try:
                    OrderStateMachine.transition(prior.status, event.status)
                except ValueError as exc:
                    raise OrderJournalIntegrityError(str(exc)) from exc
            current[event.identifier] = event
            previous_hash = event.event_hash

    def _append(
        self,
        *,
        intent_id: UUID,
        risk_decision_id: UUID,
        identifier: str,
        market: str,
        status: OrderStatus,
        occurred_at_utc: datetime,
        source: JournalSource,
        exchange_order_id: UUID | None,
        details: tuple[tuple[str, str], ...],
    ) -> ExecutionJournalEvent:
        sequence = len(self._events) + 1
        previous_hash = self._events[-1].event_hash if self._events else ZERO_HASH
        values = {
            "sequence": sequence,
            "event_id": deterministic_execution_id(
                "order-journal", sequence, identifier, status, previous_hash
            ),
            "intent_id": intent_id,
            "risk_decision_id": risk_decision_id,
            "identifier": identifier,
            "market": market,
            "status": status,
            "occurred_at_utc": occurred_at_utc,
            "source": source,
            "exchange_order_id": exchange_order_id,
            "details": tuple(sorted(details)),
            "previous_hash": previous_hash,
        }
        event = ExecutionJournalEvent(**values, event_hash=self._hash_values(values))
        if self.path is not None:
            self._persist(event)
        self._events.append(event)
        self._current[event.identifier] = event
        self._intent_identifiers[event.intent_id] = event.identifier
        return event

    def _persist(self, event: ExecutionJournalEvent) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = orjson.dumps(event.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        with self.path.open("ab") as handle:
            handle.write(serialized + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _load(self, path: Path) -> None:
        try:
            lines = path.read_bytes().splitlines()
            if not lines and path.stat().st_size:
                raise OrderJournalIntegrityError("order journal contains a partial record")
            self._events = [
                ExecutionJournalEvent.model_validate(orjson.loads(line)) for line in lines
            ]
            self.verify()
        except (OSError, orjson.JSONDecodeError, ValueError) as exc:
            if isinstance(exc, OrderJournalIntegrityError):
                raise
            raise OrderJournalIntegrityError("order journal could not be safely loaded") from exc
        self._current.clear()
        self._intent_identifiers.clear()
        for event in self._events:
            self._current[event.identifier] = event
            self._intent_identifiers[event.intent_id] = event.identifier

    @staticmethod
    def _hash_values(values: dict[str, object]) -> str:
        payload = orjson.dumps(values, option=orjson.OPT_SORT_KEYS, default=str)
        return sha256(payload).hexdigest()

    @classmethod
    def _hash_event(cls, event: ExecutionJournalEvent) -> str:
        return cls._hash_values(event.model_dump(exclude={"event_hash"}))

"""No-retry submission coordinator with identifier-based uncertainty reconciliation."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from quantforge.domain import (
    ExchangeOrderRequest,
    OrderChance,
    OrderStatus,
    RemoteOrderSnapshot,
    RemoteOrderState,
    RiskDecision,
    RiskDecisionType,
)
from quantforge.exchange.private import (
    PrivateExchangeDisabled,
    PrivateOrderPort,
    PrivateTransportError,
    PrivateTransportTimeout,
)
from quantforge.execution.journal import JournalSource, OrderJournal
from quantforge.execution.order_policy import ExchangeOrderPolicy, OrderPreflightResult


class SubmissionOutcome(StrEnum):
    ACKNOWLEDGED = "acknowledged"
    FILLED = "filled"
    CANCELED = "canceled"
    PREVENTED = "prevented"
    REJECTED = "rejected"
    UNKNOWN = "unknown"
    IDEMPOTENT = "idempotent"


class SubmissionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    outcome: SubmissionOutcome
    status: OrderStatus
    occurred_at_utc: datetime
    exchange_order_id: UUID | None = None
    reason_codes: tuple[str, ...]
    create_attempted: bool
    reconciled: bool

    @field_validator("occurred_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("submission result timestamp must be UTC-aware")
        return value


class SubmissionCoordinator:
    def __init__(
        self,
        *,
        port: PrivateOrderPort,
        journal: OrderJournal,
        policy: ExchangeOrderPolicy | None = None,
    ) -> None:
        self.port = port
        self.journal = journal
        self.policy = policy or ExchangeOrderPolicy()

    def prepare(
        self,
        request: ExchangeOrderRequest,
        risk: RiskDecision,
        chance: OrderChance,
        *,
        at_utc: datetime,
    ) -> OrderPreflightResult:
        current = self.journal.register(request, occurred_at_utc=at_utc)
        if current.status is not OrderStatus.INTENT_CREATED:
            raise ValueError("order identifier has already passed preparation")
        if (
            risk.intent_id != request.intent_id
            or risk.decision_id != request.risk_decision_id
            or risk.decision not in {RiskDecisionType.ALLOW, RiskDecisionType.RESIZE}
        ):
            self.journal.transition(
                request.identifier,
                OrderStatus.RISK_REJECTED,
                occurred_at_utc=at_utc,
                source=JournalSource.RISK,
                details=(("reason", "risk_not_approved"),),
            )
            return self.policy.evaluate(request, risk, chance, checked_at_utc=at_utc)
        self.journal.transition(
            request.identifier,
            OrderStatus.RISK_APPROVED,
            occurred_at_utc=at_utc,
            source=JournalSource.RISK,
        )
        self.journal.transition(
            request.identifier,
            OrderStatus.PREFLIGHT_PENDING,
            occurred_at_utc=at_utc,
            source=JournalSource.PREFLIGHT,
        )
        preflight = self.policy.evaluate(request, risk, chance, checked_at_utc=at_utc)
        self.journal.transition(
            request.identifier,
            OrderStatus.PREFLIGHT_OK if preflight.allowed else OrderStatus.PREFLIGHT_FAILED,
            occurred_at_utc=at_utc,
            source=JournalSource.PREFLIGHT,
            details=(("reasons", "|".join(preflight.reason_codes)),),
        )
        return preflight

    async def submit(
        self,
        request: ExchangeOrderRequest,
        risk: RiskDecision,
        chance: OrderChance,
        *,
        at_utc: datetime,
    ) -> SubmissionResult:
        current = self.journal.by_intent(request.intent_id)
        if current is None:
            preflight = self.prepare(request, risk, chance, at_utc=at_utc)
            if not preflight.allowed:
                return self._result(
                    request,
                    SubmissionOutcome.REJECTED,
                    OrderStatus.PREFLIGHT_FAILED,
                    at_utc,
                    preflight.reason_codes,
                    create_attempted=False,
                )
            current = self.journal.current(request.identifier)
            assert current is not None

        if current.status in {
            OrderStatus.SUBMISSION_PENDING,
            OrderStatus.UNKNOWN,
            OrderStatus.RECONCILING,
        }:
            return await self._reconcile(request, at_utc=at_utc, create_attempted=False)
        if current.status is not OrderStatus.PREFLIGHT_OK:
            return self._result(
                request,
                SubmissionOutcome.IDEMPOTENT,
                current.status,
                at_utc,
                ("NO_DUPLICATE_CREATE",),
                create_attempted=False,
                exchange_order_id=current.exchange_order_id,
            )

        self.journal.transition(
            request.identifier,
            OrderStatus.SUBMISSION_PENDING,
            occurred_at_utc=at_utc,
            source=JournalSource.REST,
        )
        try:
            remote = await self.port.create_order(request)
        except PrivateTransportTimeout:
            self.journal.transition(
                request.identifier,
                OrderStatus.UNKNOWN,
                occurred_at_utc=at_utc,
                source=JournalSource.REST,
                details=(("reason", "create_timeout"),),
            )
            return await self._reconcile(request, at_utc=at_utc, create_attempted=True)
        except (PrivateTransportError, PrivateExchangeDisabled) as exc:
            self.journal.transition(
                request.identifier,
                OrderStatus.REJECTED,
                occurred_at_utc=at_utc,
                source=JournalSource.REST,
                details=(("error_type", type(exc).__name__),),
            )
            return self._result(
                request,
                SubmissionOutcome.REJECTED,
                OrderStatus.REJECTED,
                at_utc,
                ("DEFINITE_CREATE_FAILURE",),
                create_attempted=True,
            )
        try:
            self._validate_remote_identity(request, remote)
        except ValueError:
            self.journal.transition(
                request.identifier,
                OrderStatus.UNKNOWN,
                occurred_at_utc=at_utc,
                source=JournalSource.REST,
                details=(("reason", "create_identity_mismatch"),),
            )
            return await self._reconcile(request, at_utc=at_utc, create_attempted=True)
        self.journal.transition(
            request.identifier,
            OrderStatus.SUBMITTED,
            occurred_at_utc=at_utc,
            source=JournalSource.REST,
            exchange_order_id=remote.exchange_order_id,
        )
        return self._apply_remote(
            request, remote, at_utc=at_utc, source=JournalSource.REST, create_attempted=True
        )

    async def _reconcile(
        self,
        request: ExchangeOrderRequest,
        *,
        at_utc: datetime,
        create_attempted: bool,
    ) -> SubmissionResult:
        current = self.journal.current(request.identifier)
        assert current is not None
        if current.status is OrderStatus.SUBMISSION_PENDING:
            current = self.journal.transition(
                request.identifier,
                OrderStatus.UNKNOWN,
                occurred_at_utc=at_utc,
                source=JournalSource.RECOVERY,
                details=(("reason", "submission_pending_after_recovery"),),
            )
        elif current.status is OrderStatus.RECONCILING:
            current = self.journal.transition(
                request.identifier,
                OrderStatus.UNKNOWN,
                occurred_at_utc=at_utc,
                source=JournalSource.RECOVERY,
                details=(("reason", "reconciliation_interrupted"),),
            )
        if current.status is not OrderStatus.UNKNOWN:
            raise ValueError("only uncertain submissions can be reconciled")
        self.journal.transition(
            request.identifier,
            OrderStatus.RECONCILING,
            occurred_at_utc=at_utc,
            source=JournalSource.RECONCILIATION,
        )
        try:
            remote = await self.port.find_order(request.identifier)
        except (PrivateTransportTimeout, PrivateTransportError, PrivateExchangeDisabled):
            remote = None
            reason = "IDENTIFIER_LOOKUP_FAILED_NO_RETRY"
        else:
            reason = "IDENTIFIER_NOT_FOUND_NO_RETRY"
        if remote is None:
            self.journal.transition(
                request.identifier,
                OrderStatus.UNKNOWN,
                occurred_at_utc=at_utc,
                source=JournalSource.RECONCILIATION,
                details=(("reason", reason),),
            )
            return self._result(
                request,
                SubmissionOutcome.UNKNOWN,
                OrderStatus.UNKNOWN,
                at_utc,
                (reason,),
                create_attempted=create_attempted,
                reconciled=True,
            )
        try:
            self._validate_remote_identity(request, remote)
        except ValueError:
            self.journal.transition(
                request.identifier,
                OrderStatus.UNKNOWN,
                occurred_at_utc=at_utc,
                source=JournalSource.RECONCILIATION,
                details=(("reason", "REMOTE_IDENTITY_MISMATCH_NO_RETRY"),),
            )
            return self._result(
                request,
                SubmissionOutcome.UNKNOWN,
                OrderStatus.UNKNOWN,
                at_utc,
                ("REMOTE_IDENTITY_MISMATCH_NO_RETRY",),
                create_attempted=create_attempted,
                reconciled=True,
            )
        return self._apply_remote(
            request,
            remote,
            at_utc=at_utc,
            source=JournalSource.RECONCILIATION,
            create_attempted=create_attempted,
            reconciled=True,
        )

    def _apply_remote(
        self,
        request: ExchangeOrderRequest,
        remote: RemoteOrderSnapshot,
        *,
        at_utc: datetime,
        source: JournalSource,
        create_attempted: bool,
        reconciled: bool = False,
    ) -> SubmissionResult:
        current = self.journal.current(request.identifier)
        assert current is not None
        if current.status is OrderStatus.SUBMITTED:
            self.journal.transition(
                request.identifier,
                OrderStatus.ACKNOWLEDGED,
                occurred_at_utc=at_utc,
                source=source,
                exchange_order_id=remote.exchange_order_id,
            )
        target, outcome = {
            RemoteOrderState.WAIT: (OrderStatus.ACKNOWLEDGED, SubmissionOutcome.ACKNOWLEDGED),
            RemoteOrderState.WATCH: (OrderStatus.ACKNOWLEDGED, SubmissionOutcome.ACKNOWLEDGED),
            RemoteOrderState.DONE: (OrderStatus.FILLED, SubmissionOutcome.FILLED),
            RemoteOrderState.CANCEL: (OrderStatus.CANCELED, SubmissionOutcome.CANCELED),
            RemoteOrderState.PREVENTED: (OrderStatus.PREVENTED, SubmissionOutcome.PREVENTED),
        }[remote.state]
        current = self.journal.current(request.identifier)
        assert current is not None
        if current.status != target:
            self.journal.transition(
                request.identifier,
                target,
                occurred_at_utc=at_utc,
                source=source,
                exchange_order_id=remote.exchange_order_id,
            )
        return self._result(
            request,
            outcome,
            target,
            at_utc,
            ("REMOTE_IDENTITY_RECONCILED",),
            create_attempted=create_attempted,
            reconciled=reconciled,
            exchange_order_id=remote.exchange_order_id,
        )

    @staticmethod
    def _validate_remote_identity(
        request: ExchangeOrderRequest, remote: RemoteOrderSnapshot
    ) -> None:
        if remote.identifier != request.identifier or remote.market != request.market:
            raise ValueError("remote order identity does not match request")

    @staticmethod
    def _result(
        request: ExchangeOrderRequest,
        outcome: SubmissionOutcome,
        status: OrderStatus,
        at_utc: datetime,
        reasons: tuple[str, ...],
        *,
        create_attempted: bool,
        reconciled: bool = False,
        exchange_order_id: UUID | None = None,
    ) -> SubmissionResult:
        return SubmissionResult(
            identifier=request.identifier,
            outcome=outcome,
            status=status,
            occurred_at_utc=at_utc,
            exchange_order_id=exchange_order_id,
            reason_codes=reasons,
            create_attempted=create_attempted,
            reconciled=reconciled,
        )

"""Read-only order and balance reconciliation used before execution resumes."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.domain import MonetaryDecimal, OrderStatus, RemoteOrderSnapshot, RemoteOrderState
from quantforge.execution.journal import OrderJournal


class ReconciliationIssueType(StrEnum):
    UNCERTAIN_SUBMISSION = "uncertain_submission"
    UNKNOWN_REMOTE_ORDER = "unknown_remote_order"
    MISSING_REMOTE_ORDER = "missing_remote_order"
    ORDER_STATE_MISMATCH = "order_state_mismatch"
    BALANCE_MISMATCH = "balance_mismatch"


class BalanceObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: str = Field(pattern=r"^[A-Z0-9]+$")
    available: MonetaryDecimal = Field(ge=0)
    locked: MonetaryDecimal = Field(ge=0)


class ReconciliationIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_type: ReconciliationIssueType
    key: str
    local_value: str | None = None
    remote_value: str | None = None


class ReconciliationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reconciled_at_utc: datetime
    safe_to_resume: bool
    issues: tuple[ReconciliationIssue, ...]
    journal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    report_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("reconciled_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("reconciliation timestamp must be UTC-aware")
        return value


class ExecutionReconciler:
    def reconcile(
        self,
        *,
        journal: OrderJournal,
        remote_orders: tuple[RemoteOrderSnapshot, ...],
        local_balances: tuple[BalanceObservation, ...],
        remote_balances: tuple[BalanceObservation, ...],
        reconciled_at_utc: datetime,
    ) -> ReconciliationReport:
        journal.verify()
        issues: list[ReconciliationIssue] = []
        remote_by_identifier = {order.identifier: order for order in remote_orders}
        if len(remote_by_identifier) != len(remote_orders):
            raise ValueError("remote reconciliation contains duplicate identifiers")
        local_by_identifier = {
            identifier: journal.current(identifier) for identifier in journal.identifiers
        }
        for identifier, remote_order in sorted(remote_by_identifier.items()):
            if local_by_identifier.get(identifier) is None:
                issues.append(
                    ReconciliationIssue(
                        issue_type=ReconciliationIssueType.UNKNOWN_REMOTE_ORDER,
                        key=identifier,
                        remote_value=remote_order.state.value,
                    )
                )
        for identifier, local_event in sorted(local_by_identifier.items()):
            assert local_event is not None
            matching_remote = remote_by_identifier.get(identifier)
            if local_event.status in {OrderStatus.UNKNOWN, OrderStatus.RECONCILING}:
                issues.append(
                    ReconciliationIssue(
                        issue_type=ReconciliationIssueType.UNCERTAIN_SUBMISSION,
                        key=identifier,
                        local_value=local_event.status.value,
                    )
                )
            if (
                local_event.status
                in {
                    OrderStatus.SUBMITTED,
                    OrderStatus.ACKNOWLEDGED,
                    OrderStatus.PARTIALLY_FILLED,
                    OrderStatus.CANCEL_PENDING,
                    OrderStatus.CANCEL_REQUESTED,
                }
                and matching_remote is None
            ):
                issues.append(
                    ReconciliationIssue(
                        issue_type=ReconciliationIssueType.MISSING_REMOTE_ORDER,
                        key=identifier,
                        local_value=local_event.status.value,
                    )
                )
            elif matching_remote is not None and not self._states_compatible(
                local_event.status, matching_remote.state
            ):
                issues.append(
                    ReconciliationIssue(
                        issue_type=ReconciliationIssueType.ORDER_STATE_MISMATCH,
                        key=identifier,
                        local_value=local_event.status.value,
                        remote_value=matching_remote.state.value,
                    )
                )

        local_balance_map = self._balance_map(local_balances)
        remote_balance_map = self._balance_map(remote_balances)
        for currency in sorted(set(local_balance_map) | set(remote_balance_map)):
            local_amounts = local_balance_map.get(currency, (Decimal(0), Decimal(0)))
            remote_amounts = remote_balance_map.get(currency, (Decimal(0), Decimal(0)))
            if local_amounts != remote_amounts:
                issues.append(
                    ReconciliationIssue(
                        issue_type=ReconciliationIssueType.BALANCE_MISMATCH,
                        key=currency,
                        local_value=f"{local_amounts[0]}|{local_amounts[1]}",
                        remote_value=f"{remote_amounts[0]}|{remote_amounts[1]}",
                    )
                )
        issues_tuple = tuple(sorted(issues, key=lambda item: (item.issue_type.value, item.key)))
        journal_hash = journal.events[-1].event_hash if journal.events else "0" * 64
        values = {
            "reconciled_at_utc": reconciled_at_utc,
            "safe_to_resume": not issues_tuple,
            "issues": tuple(issue.model_dump(mode="json") for issue in issues_tuple),
            "journal_hash": journal_hash,
        }
        report_hash = sha256(
            orjson.dumps(values, option=orjson.OPT_SORT_KEYS, default=str)
        ).hexdigest()
        return ReconciliationReport(**values, report_hash=report_hash)

    @staticmethod
    def _balance_map(values: tuple[BalanceObservation, ...]) -> dict[str, tuple[Decimal, Decimal]]:
        result = {value.currency: (value.available, value.locked) for value in values}
        if len(result) != len(values):
            raise ValueError("balance observations contain duplicate currencies")
        return result

    @staticmethod
    def _states_compatible(local: OrderStatus, remote: RemoteOrderState) -> bool:
        compatibility = {
            RemoteOrderState.WAIT: {
                OrderStatus.SUBMITTED,
                OrderStatus.ACKNOWLEDGED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.CANCEL_PENDING,
                OrderStatus.CANCEL_REQUESTED,
            },
            RemoteOrderState.WATCH: {OrderStatus.ACKNOWLEDGED},
            RemoteOrderState.DONE: {OrderStatus.FILLED},
            RemoteOrderState.CANCEL: {OrderStatus.CANCELED},
            RemoteOrderState.PREVENTED: {OrderStatus.PREVENTED},
        }
        return local in compatibility[remote]

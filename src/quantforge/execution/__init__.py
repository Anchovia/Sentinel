"""Paper engines and transport-free authenticated execution safety contracts."""

from quantforge.execution.coordinator import (
    SubmissionCoordinator,
    SubmissionOutcome,
    SubmissionResult,
)
from quantforge.execution.identifiers import OrderIdentifierFactory
from quantforge.execution.journal import (
    ExecutionJournalEvent,
    JournalSource,
    OrderJournal,
    OrderJournalIntegrityError,
)
from quantforge.execution.live import DisabledLiveOrderAdapter, LiveExecutionUnavailable
from quantforge.execution.order_policy import ExchangeOrderPolicy, OrderPreflightResult
from quantforge.execution.paper import (
    PaperBroker,
    PaperBrokerState,
    PaperExecutionRejected,
    PaperWorkingOrderState,
)
from quantforge.execution.reconciliation import (
    BalanceObservation,
    ExecutionReconciler,
    ReconciliationIssue,
    ReconciliationIssueType,
    ReconciliationReport,
)

__all__ = [
    "BalanceObservation",
    "DisabledLiveOrderAdapter",
    "ExchangeOrderPolicy",
    "ExecutionJournalEvent",
    "ExecutionReconciler",
    "JournalSource",
    "LiveExecutionUnavailable",
    "OrderIdentifierFactory",
    "OrderJournal",
    "OrderJournalIntegrityError",
    "OrderPreflightResult",
    "PaperBroker",
    "PaperBrokerState",
    "PaperExecutionRejected",
    "PaperWorkingOrderState",
    "ReconciliationIssue",
    "ReconciliationIssueType",
    "ReconciliationReport",
    "SubmissionCoordinator",
    "SubmissionOutcome",
    "SubmissionResult",
]

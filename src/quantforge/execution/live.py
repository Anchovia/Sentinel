"""Phase 6 live boundary: permanently disabled even if all configuration gates pass."""

from quantforge.config import QuantForgeSettings
from quantforge.domain import ExchangeOrderRequest, RiskDecision
from quantforge.runtime import LiveSubmissionGuard


class LiveExecutionUnavailable(RuntimeError):
    """There is deliberately no Phase 6 real-order implementation."""


class DisabledLiveOrderAdapter:
    network_capability = False

    async def submit(
        self,
        request: ExchangeOrderRequest,
        risk: RiskDecision,
        settings: QuantForgeSettings,
    ) -> None:
        del request, risk
        LiveSubmissionGuard.require_allowed(settings)
        raise LiveExecutionUnavailable(
            "Phase 6 live adapter remains disabled after all gates; manual canary review is absent"
        )

    async def cancel(self, identifier: str, settings: QuantForgeSettings) -> None:
        del identifier
        LiveSubmissionGuard.require_allowed(settings)
        raise LiveExecutionUnavailable("Phase 6 live cancellation transport is not implemented")

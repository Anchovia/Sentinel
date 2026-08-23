"""Fail-closed live order submission gate."""

from dataclasses import dataclass

from quantforge.config import QuantForgeSettings, TradingMode


class LiveSubmissionBlocked(RuntimeError):
    """Raised whenever any independent live gate is unsatisfied."""


@dataclass(frozen=True, slots=True)
class LiveGateResult:
    allowed: bool
    failures: tuple[str, ...]


class LiveSubmissionGuard:
    """Evaluate the six mandatory live gates without side effects."""

    @staticmethod
    def evaluate(settings: QuantForgeSettings) -> LiveGateResult:
        checks = {
            "TRADING_MODE_LIVE": settings.trading_mode is TradingMode.LIVE,
            "ALLOW_ORDER_SUBMISSION": settings.allow_order_submission,
            "LIVE_RELEASE_MANIFEST_VALID": settings.live_release_manifest_valid,
            "RISK_POLICY_APPROVED": settings.risk_policy_approved,
            "MODEL_RELEASE_APPROVED": settings.model_release_approved,
            "OPERATOR_UNLOCK_PRESENT": settings.operator_unlock_present,
        }
        failures = tuple(name for name, passed in checks.items() if not passed)
        return LiveGateResult(allowed=not failures, failures=failures)

    @classmethod
    def require_allowed(cls, settings: QuantForgeSettings) -> None:
        result = cls.evaluate(settings)
        if not result.allowed:
            failure_list = ", ".join(result.failures)
            raise LiveSubmissionBlocked(f"live order submission blocked: {failure_list}")

import pytest

from quantforge.config import QuantForgeSettings, TradingMode
from quantforge.runtime import LiveSubmissionBlocked, LiveSubmissionGuard


def _live_settings(**overrides: object) -> QuantForgeSettings:
    values: dict[str, object] = {
        "_env_file": None,
        "trading_mode": TradingMode.LIVE,
        "allow_order_submission": True,
        "live_release_manifest_valid": True,
        "risk_policy_approved": True,
        "model_release_approved": True,
        "operator_unlock_present": True,
    }
    values.update(overrides)
    return QuantForgeSettings(**values)


def test_default_settings_fail_all_six_live_gates() -> None:
    result = LiveSubmissionGuard.evaluate(QuantForgeSettings(_env_file=None))

    assert result.allowed is False
    assert result.failures == (
        "TRADING_MODE_LIVE",
        "ALLOW_ORDER_SUBMISSION",
        "LIVE_RELEASE_MANIFEST_VALID",
        "RISK_POLICY_APPROVED",
        "MODEL_RELEASE_APPROVED",
        "OPERATOR_UNLOCK_PRESENT",
    )


def test_all_six_live_gates_are_required() -> None:
    settings = _live_settings()

    assert LiveSubmissionGuard.evaluate(settings).allowed is True
    LiveSubmissionGuard.require_allowed(settings)


@pytest.mark.parametrize(
    ("field", "value", "expected_failure"),
    [
        ("trading_mode", TradingMode.PAPER, "TRADING_MODE_LIVE"),
        ("allow_order_submission", False, "ALLOW_ORDER_SUBMISSION"),
        ("live_release_manifest_valid", False, "LIVE_RELEASE_MANIFEST_VALID"),
        ("risk_policy_approved", False, "RISK_POLICY_APPROVED"),
        ("model_release_approved", False, "MODEL_RELEASE_APPROVED"),
        ("operator_unlock_present", False, "OPERATOR_UNLOCK_PRESENT"),
    ],
)
def test_each_missing_live_gate_blocks_submission(
    field: str, value: object, expected_failure: str
) -> None:
    settings = _live_settings(**{field: value})
    result = LiveSubmissionGuard.evaluate(settings)

    assert result.allowed is False
    assert result.failures == (expected_failure,)


def test_require_allowed_raises_with_evidence() -> None:
    with pytest.raises(LiveSubmissionBlocked, match="TRADING_MODE_LIVE"):
        LiveSubmissionGuard.require_allowed(QuantForgeSettings(_env_file=None))

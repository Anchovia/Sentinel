from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from quantforge.domain.risk import RiskDecision, RiskDecisionType


def _decision(**overrides: object) -> RiskDecision:
    values: dict[str, object] = {
        "intent_id": uuid4(),
        "decision": RiskDecisionType.REJECT,
        "reason_codes": ("FOUNDATION_BLOCK",),
        "risk_snapshot_id": uuid4(),
        "policy_version": "foundation-0.1",
        "decided_at": datetime.now(tz=UTC),
    }
    values.update(overrides)
    return RiskDecision(**values)


def test_reject_decision_has_no_approved_amount() -> None:
    decision = _decision()

    assert decision.decision is RiskDecisionType.REJECT
    assert decision.approved_notional is None


def test_allow_requires_exactly_one_positive_amount() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        _decision(decision=RiskDecisionType.ALLOW)

    decision = _decision(decision=RiskDecisionType.ALLOW, approved_notional="10000")
    assert str(decision.approved_notional) == "10000"

    with pytest.raises(ValidationError, match="positive"):
        _decision(decision=RiskDecisionType.RESIZE, approved_quantity="0")


def test_reject_cannot_carry_approval_and_time_must_be_aware() -> None:
    with pytest.raises(ValidationError, match="cannot approve"):
        _decision(approved_notional="10000")

    with pytest.raises(ValidationError, match="timezone-aware"):
        _decision(decided_at=datetime.now())

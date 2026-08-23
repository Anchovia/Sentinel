"""Risk decision contracts independent from strategy code."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantforge.domain.money import MonetaryDecimal


class RiskDecisionType(StrEnum):
    ALLOW = "allow"
    REJECT = "reject"
    RESIZE = "resize"
    HOLD = "hold"


class RiskDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: UUID = Field(default_factory=uuid4)
    intent_id: UUID
    decision: RiskDecisionType
    approved_notional: MonetaryDecimal | None = None
    approved_quantity: MonetaryDecimal | None = None
    reason_codes: tuple[str, ...] = Field(min_length=1)
    risk_snapshot_id: UUID
    policy_version: str = Field(min_length=1)
    decided_at: datetime

    @model_validator(mode="after")
    def validate_approval_amount(self) -> "RiskDecision":
        amounts = (self.approved_notional, self.approved_quantity)
        present = sum(value is not None for value in amounts)
        if self.decision in {RiskDecisionType.ALLOW, RiskDecisionType.RESIZE} and present != 1:
            raise ValueError("allow/resize decisions require exactly one approved amount")
        if self.decision in {RiskDecisionType.REJECT, RiskDecisionType.HOLD} and present != 0:
            raise ValueError("reject/hold decisions cannot approve an amount")
        if any(value is not None and value <= 0 for value in amounts):
            raise ValueError("approved amounts must be positive")
        if self.decided_at.tzinfo is None:
            raise ValueError("decided_at must be timezone-aware")
        return self

"""Hard-limit risk engine positioned between strategy routing and any broker."""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.domain import (
    OrderIntent,
    RiskDecision,
    RiskDecisionType,
    deterministic_execution_id,
)
from quantforge.domain.money import MonetaryDecimal
from quantforge.strategies import StrategyAction, StrategyDecision


class RiskLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str
    min_order_notional_krw: MonetaryDecimal = Field(ge=0)
    max_order_notional_krw: MonetaryDecimal = Field(ge=0)
    max_position_notional_per_market: MonetaryDecimal = Field(ge=0)
    max_total_exposure_krw: MonetaryDecimal = Field(ge=0)
    max_total_exposure_pct: MonetaryDecimal = Field(ge=0, le=1)
    max_concurrent_positions: int = Field(ge=0)
    max_daily_loss_krw: MonetaryDecimal = Field(ge=0)
    max_daily_loss_pct: MonetaryDecimal = Field(ge=0, le=1)
    max_drawdown_pct: MonetaryDecimal = Field(ge=0, le=1)
    max_strategy_loss_krw: MonetaryDecimal = Field(ge=0)
    max_consecutive_losses: int = Field(ge=0)
    max_orders_per_minute: int = Field(ge=0)
    max_orders_per_market_per_minute: int = Field(ge=0)
    max_turnover_per_day: MonetaryDecimal = Field(ge=0)
    max_relative_spread_bps: MonetaryDecimal = Field(ge=0)
    max_expected_slippage_bps: MonetaryDecimal = Field(ge=0)
    max_data_age_ms: int = Field(ge=0)
    max_clock_skew_ms: int = Field(ge=0)
    max_unknown_orders: int = Field(ge=0)
    max_balance_age_seconds: int = Field(ge=0)
    max_balance_reconciliation_age_seconds: int = Field(ge=0)
    max_model_age_seconds: int = Field(ge=0)
    max_prediction_age_seconds: int = Field(ge=0)
    max_prediction_uncertainty: float = Field(ge=0, le=1)
    min_expected_net_edge_bps: MonetaryDecimal = Field(ge=0)

    @property
    def digest(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()


class RiskSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: UUID
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    captured_at_utc: datetime
    trading_mode: str
    kill_switch_active: bool
    market_active: bool
    warning_active: bool
    public_websocket_healthy: bool
    private_websocket_healthy: bool
    rest_healthy: bool
    data_age_ms: int = Field(ge=0)
    clock_skew_ms: int = Field(ge=0)
    balance_age_seconds: int = Field(ge=0)
    reconciliation_age_seconds: int = Field(ge=0)
    model_available: bool
    model_release_approved: bool
    model_age_seconds: int = Field(ge=0)
    features_complete: bool
    prediction_age_seconds: int = Field(ge=0)
    prediction_uncertainty: float = Field(ge=0, le=1)
    expected_net_edge_bps: MonetaryDecimal
    relative_spread_bps: MonetaryDecimal = Field(ge=0)
    expected_slippage_bps: MonetaryDecimal = Field(ge=0)
    opposing_depth_notional: MonetaryDecimal = Field(ge=0)
    reference_price: MonetaryDecimal = Field(gt=0)
    position_notional: MonetaryDecimal = Field(ge=0)
    total_exposure_krw: MonetaryDecimal = Field(ge=0)
    total_equity_krw: MonetaryDecimal = Field(gt=0)
    concurrent_positions: int = Field(ge=0)
    available_cash_krw: MonetaryDecimal = Field(ge=0)
    locked_cash_krw: MonetaryDecimal = Field(ge=0)
    daily_loss_krw: MonetaryDecimal = Field(ge=0)
    daily_loss_pct: MonetaryDecimal = Field(ge=0, le=1)
    drawdown_pct: MonetaryDecimal = Field(ge=0, le=1)
    strategy_loss_krw: MonetaryDecimal = Field(ge=0)
    consecutive_losses: int = Field(ge=0)
    orders_last_minute: int = Field(ge=0)
    market_orders_last_minute: int = Field(ge=0)
    turnover_today_krw: MonetaryDecimal = Field(ge=0)
    existing_open_order: bool
    identifier_unique: bool
    unknown_orders: int = Field(ge=0)
    volatility_scale: float = Field(ge=0, le=1)
    liquidity_scale: float = Field(ge=0, le=1)
    correlation_penalty: float = Field(ge=0, le=1)

    @field_validator("captured_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("risk snapshot timestamp must be UTC-aware")
        return value


class GatewayResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_decision_id: UUID
    intent: OrderIntent | None
    risk_decision: RiskDecision | None
    outcome: str


class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits

    def evaluate(self, intent: OrderIntent, snapshot: RiskSnapshot) -> RiskDecision:
        reasons = self._rejection_reasons(intent, snapshot)
        if reasons:
            return self._decision(intent, snapshot, RiskDecisionType.REJECT, tuple(reasons))
        if intent.requested_notional is not None:
            requested_notional = intent.requested_notional
        else:
            assert intent.requested_quantity is not None
            requested_notional = intent.requested_quantity * snapshot.reference_price
        common_capacity = min(
            self.limits.max_order_notional_krw,
            self.limits.max_turnover_per_day - snapshot.turnover_today_krw,
            snapshot.opposing_depth_notional,
        )
        if intent.side == "bid":
            hard_capacity = min(
                common_capacity,
                self.limits.max_position_notional_per_market - snapshot.position_notional,
                self.limits.max_total_exposure_krw - snapshot.total_exposure_krw,
                snapshot.total_equity_krw * self.limits.max_total_exposure_pct
                - snapshot.total_exposure_krw,
                snapshot.available_cash_krw,
            )
        else:
            hard_capacity = min(common_capacity, snapshot.position_notional)
        scale = (
            Decimal(str(snapshot.volatility_scale))
            * Decimal(str(snapshot.liquidity_scale))
            * Decimal(str(intent.confidence))
            * (Decimal(1) - Decimal(str(intent.uncertainty)))
            * (Decimal(1) - Decimal(str(snapshot.correlation_penalty)))
            * (Decimal(1) - snapshot.drawdown_pct)
        )
        approved_notional = min(requested_notional, hard_capacity) * max(scale, Decimal(0))
        if approved_notional < self.limits.min_order_notional_krw:
            return self._decision(
                intent,
                snapshot,
                RiskDecisionType.REJECT,
                ("SIZED_BELOW_MINIMUM",),
            )
        if intent.requested_notional is not None:
            amount: dict[str, Decimal] = {"approved_notional": approved_notional}
        else:
            ratio = approved_notional / requested_notional
            assert intent.requested_quantity is not None
            amount = {"approved_quantity": intent.requested_quantity * ratio}
        decision_type = (
            RiskDecisionType.ALLOW
            if approved_notional == requested_notional
            else RiskDecisionType.RESIZE
        )
        return self._decision(
            intent,
            snapshot,
            decision_type,
            ("ALL_HARD_LIMITS_PASS",),
            **amount,
        )

    def _rejection_reasons(self, intent: OrderIntent, state: RiskSnapshot) -> list[str]:
        checks = (
            (state.market != intent.market, "RISK_MARKET_MISMATCH"),
            (
                state.captured_at_utc < intent.signal_timestamp,
                "RISK_SNAPSHOT_PRECEDES_SIGNAL",
            ),
            (
                state.expected_net_edge_bps != Decimal(str(intent.expected_net_edge_bps)),
                "EDGE_SNAPSHOT_MISMATCH",
            ),
            (
                state.prediction_uncertainty != intent.uncertainty,
                "UNCERTAINTY_SNAPSHOT_MISMATCH",
            ),
            (state.kill_switch_active, "KILL_SWITCH_ACTIVE"),
            (state.trading_mode not in {"paper", "backtest", "shadow"}, "MODE_NOT_ALLOWED"),
            (not state.market_active, "MARKET_INACTIVE"),
            (state.warning_active, "MARKET_WARNING"),
            (not state.public_websocket_healthy, "PUBLIC_WEBSOCKET_UNHEALTHY"),
            (state.data_age_ms > self.limits.max_data_age_ms, "STALE_DATA"),
            (state.clock_skew_ms > self.limits.max_clock_skew_ms, "CLOCK_SKEW"),
            (
                state.balance_age_seconds > self.limits.max_balance_age_seconds,
                "STALE_BALANCE",
            ),
            (
                state.reconciliation_age_seconds
                > self.limits.max_balance_reconciliation_age_seconds,
                "STALE_RECONCILIATION",
            ),
            (not state.model_available, "MODEL_UNAVAILABLE"),
            (not state.model_release_approved, "MODEL_RELEASE_NOT_APPROVED"),
            (state.model_age_seconds > self.limits.max_model_age_seconds, "STALE_MODEL"),
            (not state.features_complete, "INCOMPLETE_FEATURES"),
            (
                state.prediction_age_seconds > self.limits.max_prediction_age_seconds,
                "STALE_PREDICTION",
            ),
            (
                state.prediction_uncertainty > self.limits.max_prediction_uncertainty,
                "PREDICTION_UNCERTAIN",
            ),
            (
                state.expected_net_edge_bps < self.limits.min_expected_net_edge_bps,
                "INSUFFICIENT_NET_EDGE",
            ),
            (
                state.relative_spread_bps > self.limits.max_relative_spread_bps,
                "SPREAD_LIMIT",
            ),
            (
                state.expected_slippage_bps > self.limits.max_expected_slippage_bps,
                "SLIPPAGE_LIMIT",
            ),
            (state.opposing_depth_notional <= 0, "INSUFFICIENT_DEPTH"),
            (state.daily_loss_krw >= self.limits.max_daily_loss_krw, "DAILY_LOSS_KRW"),
            (state.daily_loss_pct >= self.limits.max_daily_loss_pct, "DAILY_LOSS_PCT"),
            (state.drawdown_pct >= self.limits.max_drawdown_pct, "DRAWDOWN_LIMIT"),
            (state.strategy_loss_krw >= self.limits.max_strategy_loss_krw, "STRATEGY_LOSS"),
            (
                state.consecutive_losses >= self.limits.max_consecutive_losses,
                "CONSECUTIVE_LOSSES",
            ),
            (state.orders_last_minute >= self.limits.max_orders_per_minute, "ORDER_RATE"),
            (
                state.market_orders_last_minute >= self.limits.max_orders_per_market_per_minute,
                "MARKET_ORDER_RATE",
            ),
            (state.existing_open_order, "EXISTING_OPEN_ORDER"),
            (not state.identifier_unique, "IDENTIFIER_NOT_UNIQUE"),
            (state.unknown_orders > self.limits.max_unknown_orders, "UNKNOWN_ORDERS"),
            (intent.expires_at <= state.captured_at_utc, "INTENT_EXPIRED"),
        )
        reasons = [reason for failed, reason in checks if failed]
        if (
            state.concurrent_positions >= self.limits.max_concurrent_positions
            and state.position_notional == 0
        ):
            reasons.append("CONCURRENT_POSITION_LIMIT")
        return reasons

    def _decision(
        self,
        intent: OrderIntent,
        snapshot: RiskSnapshot,
        decision: RiskDecisionType,
        reasons: tuple[str, ...],
        **amount: Decimal,
    ) -> RiskDecision:
        return RiskDecision(
            decision_id=deterministic_execution_id(
                "risk-decision", intent.intent_id, snapshot.snapshot_id, self.limits.digest
            ),
            intent_id=intent.intent_id,
            decision=decision,
            approved_notional=amount.get("approved_notional"),
            approved_quantity=amount.get("approved_quantity"),
            reason_codes=reasons,
            risk_snapshot_id=snapshot.snapshot_id,
            policy_version=self.limits.policy_version,
            decided_at=snapshot.captured_at_utc,
        )


class StrategyRiskGateway:
    """The only Phase 5 adapter from a strategy decision to an order intent."""

    def __init__(self, engine: RiskEngine) -> None:
        self.engine = engine

    def process(self, decision: StrategyDecision, snapshot: RiskSnapshot) -> GatewayResult:
        if decision.action is not StrategyAction.TRADE:
            return GatewayResult(
                strategy_decision_id=decision.decision_id,
                intent=None,
                risk_decision=None,
                outcome=decision.action.value,
            )
        intent = OrderIntent(
            intent_id=deterministic_execution_id(
                "order-intent", decision.decision_id, snapshot.snapshot_id
            ),
            strategy_id=decision.strategy_id,
            strategy_version=decision.strategy_version,
            market=decision.market,
            side=decision.side,
            requested_notional=decision.target_notional,
            requested_quantity=decision.target_quantity,
            order_type=decision.order_preference.value,
            limit_price=decision.limit_price,
            signal_timestamp=decision.decided_at_utc,
            expires_at=decision.valid_until_utc,
            expected_gross_edge_bps=float(decision.expected_gross_edge_bps),
            expected_cost_bps=float(decision.expected_cost_bps),
            expected_net_edge_bps=float(decision.expected_net_edge_bps),
            confidence=decision.confidence,
            uncertainty=decision.uncertainty,
            reason="|".join(decision.reason_codes),
        )
        risk_decision = self.engine.evaluate(intent, snapshot)
        return GatewayResult(
            strategy_decision_id=decision.decision_id,
            intent=intent,
            risk_decision=risk_decision,
            outcome=risk_decision.decision.value,
        )

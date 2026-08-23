"""Initial transparent strategies that only emit proposals."""

from datetime import timedelta
from decimal import Decimal
from typing import cast

from quantforge.domain import deterministic_execution_id
from quantforge.models import DecisionAction, Regime
from quantforge.strategies.contracts import (
    OrderPreference,
    StrategyAction,
    StrategyDecision,
    StrategyInput,
)


def _non_trade(
    inputs: StrategyInput,
    *,
    action: StrategyAction,
    strategy_id: str,
    strategy_version: str,
    reason: str,
) -> StrategyDecision:
    return StrategyDecision(
        decision_id=deterministic_execution_id(
            "strategy-decision", strategy_id, inputs.market.snapshot_id, reason
        ),
        action=action,
        market=inputs.market.market,
        order_preference=OrderPreference.NO_ORDER,
        expected_horizon_seconds=inputs.alpha.horizon_seconds,
        expected_gross_edge_bps=inputs.alpha.expected_gross_return_bps,
        expected_cost_bps=inputs.alpha.estimated_round_trip_cost_bps,
        expected_net_edge_bps=inputs.alpha.expected_net_return_bps,
        confidence=inputs.alpha.confidence,
        uncertainty=inputs.alpha.uncertainty,
        decided_at_utc=inputs.decision_at_utc,
        valid_until_utc=inputs.alpha.valid_until_utc,
        invalidation_conditions=("NEWER_MARKET_SNAPSHOT",),
        exit_plan="no position change",
        reason_codes=(reason,),
        strategy_id=strategy_id,
        strategy_version=strategy_version,
    )


class OfiMicropriceMomentum:
    strategy_id = "ofi-microprice-momentum"
    strategy_version = "1.0.0"

    def __init__(
        self,
        *,
        target_notional: Decimal = Decimal("10000"),
        min_ofi: float = 0.1,
        min_trade_imbalance: float = 0.05,
        max_spread_bps: Decimal = Decimal("20"),
        min_net_edge_bps: Decimal = Decimal("3"),
    ) -> None:
        self.target_notional = target_notional
        self.min_ofi = min_ofi
        self.min_trade_imbalance = min_trade_imbalance
        self.max_spread_bps = max_spread_bps
        self.min_net_edge_bps = min_net_edge_bps

    def evaluate(self, inputs: StrategyInput) -> StrategyDecision:
        if inputs.alpha.action is not DecisionAction.TRADE:
            return _non_trade(
                inputs,
                action=(
                    StrategyAction.ABSTAIN
                    if inputs.alpha.action is DecisionAction.ABSTAIN
                    else StrategyAction.HOLD
                ),
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                reason=f"ALPHA_{inputs.alpha.action.value}",
            )
        if (
            not inputs.market.market_active
            or inputs.market.warning_active
            or inputs.market.data_gap
            or inputs.market.relative_spread_bps > self.max_spread_bps
        ):
            return _non_trade(
                inputs,
                action=StrategyAction.HOLD,
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                reason="MARKET_QUALITY_BLOCK",
            )
        features = inputs.features.values
        required = (
            features.get("snapshot_derived_ofi_5"),
            features.get("trade_imbalance"),
            features.get("microprice"),
            features.get("mid_price"),
        )
        if any(value is None for value in required):
            return _non_trade(
                inputs,
                action=StrategyAction.ABSTAIN,
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                reason="MISSING_FEATURES",
            )
        ofi, imbalance, microprice, mid = (float(cast(float, value)) for value in required)
        aligned = ofi >= self.min_ofi and imbalance >= self.min_trade_imbalance and microprice > mid
        regime_ok = inputs.regime.selected_regime in {
            Regime.UPTREND_LOW_VOL,
            Regime.UPTREND_HIGH_VOL,
            Regime.RANGE_LOW_VOL,
        }
        if (
            not aligned
            or not regime_ok
            or inputs.alpha.p_up <= inputs.alpha.p_down
            or inputs.alpha.expected_net_return_bps < self.min_net_edge_bps
        ):
            return _non_trade(
                inputs,
                action=StrategyAction.HOLD,
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                reason="MOMENTUM_NOT_ALIGNED",
            )
        return StrategyDecision(
            decision_id=deterministic_execution_id(
                "strategy-decision", self.strategy_id, inputs.market.snapshot_id
            ),
            action=StrategyAction.TRADE,
            market=inputs.market.market,
            side="bid",
            target_notional=self.target_notional,
            order_preference=OrderPreference.BEST,
            expected_horizon_seconds=inputs.alpha.horizon_seconds,
            expected_gross_edge_bps=inputs.alpha.expected_gross_return_bps,
            expected_cost_bps=inputs.alpha.estimated_round_trip_cost_bps,
            expected_net_edge_bps=inputs.alpha.expected_net_return_bps,
            confidence=inputs.alpha.confidence,
            uncertainty=inputs.alpha.uncertainty,
            decided_at_utc=inputs.decision_at_utc,
            valid_until_utc=inputs.alpha.valid_until_utc,
            invalidation_conditions=("OFI_REVERSAL", "REGIME_CHANGE", "EDGE_DECAY"),
            exit_plan="time stop or OFI/microprice reversal",
            reason_codes=("OFI_MICROPRICE_ALIGNED",),
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
        )


class LiquidityShockMeanReversion:
    strategy_id = "liquidity-shock-mean-reversion"
    strategy_version = "1.0.0"

    def __init__(self, *, target_notional: Decimal = Decimal("7500")) -> None:
        self.target_notional = target_notional

    def evaluate(self, inputs: StrategyInput) -> StrategyDecision:
        if inputs.alpha.action is not DecisionAction.TRADE:
            return _non_trade(
                inputs,
                action=(
                    StrategyAction.ABSTAIN
                    if inputs.alpha.action is DecisionAction.ABSTAIN
                    else StrategyAction.HOLD
                ),
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                reason=f"ALPHA_{inputs.alpha.action.value}",
            )
        values = inputs.features.values
        shock = values.get("return_1")
        resilience = values.get("book_resilience_proxy")
        intensity = values.get("trade_arrival_rate")
        blocked_regime = inputs.regime.selected_regime in {
            Regime.DOWNTREND_HIGH_VOL,
            Regime.MARKET_DISLOCATION,
            Regime.LIQUIDITY_STRESS,
        }
        ready = (
            shock is not None
            and shock < -0.002
            and resilience is not None
            and resilience > 0
            and intensity is not None
            and intensity < 10
            and not blocked_regime
            and inputs.alpha.expected_net_return_bps > 0
        )
        if not ready:
            return _non_trade(
                inputs,
                action=StrategyAction.HOLD,
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                reason="REVERSAL_NOT_CONFIRMED",
            )
        valid_until = min(
            inputs.alpha.valid_until_utc,
            inputs.decision_at_utc + timedelta(seconds=15),
        )
        return StrategyDecision(
            decision_id=deterministic_execution_id(
                "strategy-decision", self.strategy_id, inputs.market.snapshot_id
            ),
            action=StrategyAction.TRADE,
            market=inputs.market.market,
            side="bid",
            target_notional=self.target_notional,
            order_preference=OrderPreference.LIMIT,
            limit_price=inputs.market.mid_price,
            expected_horizon_seconds=15,
            expected_gross_edge_bps=inputs.alpha.expected_gross_return_bps,
            expected_cost_bps=inputs.alpha.estimated_round_trip_cost_bps,
            expected_net_edge_bps=inputs.alpha.expected_net_return_bps,
            confidence=inputs.alpha.confidence,
            uncertainty=inputs.alpha.uncertainty,
            decided_at_utc=inputs.decision_at_utc,
            valid_until_utc=valid_until,
            invalidation_conditions=("SHOCK_CONTINUATION", "DEPTH_DROPS", "REGIME_CHANGE"),
            exit_plan="mean-reversion target or 15-second time stop",
            reason_codes=("LIQUIDITY_RECOVERY_AFTER_SHOCK",),
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
        )

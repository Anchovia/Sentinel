from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from factories import BASE_TIME
from quantforge.domain import RiskDecisionType, deterministic_execution_id
from quantforge.features import FeatureSnapshot
from quantforge.models import (
    AlphaPrediction,
    DecisionAction,
    ExecutionPrediction,
    Regime,
    RegimePrediction,
)
from quantforge.portfolio import PortfolioSnapshot
from quantforge.risk import RiskEngine, RiskLimits, RiskSnapshot, StrategyRiskGateway
from quantforge.strategies import (
    LiquidityShockMeanReversion,
    MarketSnapshot,
    OfiMicropriceMomentum,
    OrderPreference,
    RiskContext,
    StrategyAction,
    StrategyDecision,
    StrategyInput,
    StrategyRouteConfig,
    StrategyRouter,
    StrategyStatus,
    UniverseCandidate,
    UniversePolicy,
    UniverseSelector,
)


def _strategy_input(*, values: dict[str, float | None] | None = None) -> StrategyInput:
    decision_at = BASE_TIME + timedelta(seconds=1)
    feature_values = values or {
        "snapshot_derived_ofi_5": 0.5,
        "trade_imbalance": 0.3,
        "microprice": 101.0,
        "mid_price": 100.0,
        "return_1": -0.003,
        "book_resilience_proxy": 1.0,
        "trade_arrival_rate": 5.0,
    }
    features = FeatureSnapshot(
        feature_set="phase5-test",
        feature_version="1",
        market="KRW-BTC",
        event_time_utc=BASE_TIME,
        available_at_utc=BASE_TIME,
        computed_at_utc=BASE_TIME,
        values=feature_values,
        input_hash="a" * 64,
    )
    regime = RegimePrediction(
        prediction_id=UUID(int=2),
        market="KRW-BTC",
        predicted_at_utc=BASE_TIME,
        valid_until_utc=BASE_TIME + timedelta(minutes=1),
        probabilities=((Regime.RANGE_LOW_VOL.value, 0.1), (Regime.UPTREND_LOW_VOL.value, 0.9)),
        selected_regime=Regime.UPTREND_LOW_VOL,
        confidence=0.9,
        uncertainty=0.1,
        change_point_score=0.1,
        expected_duration_seconds=60,
        feature_snapshot_hash=features.snapshot_hash,
        model_version="regime-test-1",
        artifact_hash="b" * 64,
    )
    alpha = AlphaPrediction(
        prediction_id=UUID(int=3),
        market="KRW-BTC",
        predicted_at_utc=BASE_TIME,
        valid_until_utc=BASE_TIME + timedelta(seconds=30),
        horizon_seconds=15,
        p_down=0.1,
        p_neutral=0.1,
        p_up=0.8,
        expected_gross_return_bps="10",
        estimated_round_trip_cost_bps="2",
        expected_net_return_bps="8",
        prediction_interval_bps=("-2", "15"),
        uncertainty=0.2,
        confidence=0.8,
        action=DecisionAction.TRADE,
        feature_snapshot_hash=features.snapshot_hash,
        model_version="alpha-test-1",
        artifact_hash="c" * 64,
    )
    execution = ExecutionPrediction(
        prediction_id=UUID(int=4),
        market="KRW-BTC",
        predicted_at_utc=BASE_TIME,
        limit_fill_probability=0.8,
        partial_fill_probability=0.3,
        full_fill_probability=0.5,
        expected_time_to_first_fill_ms=100,
        expected_time_to_full_fill_ms=250,
        market_slippage_bps="2",
        best_slippage_bps="1",
        post_only_cancel_probability=0.1,
        adverse_selection_bps="1",
        maker_expected_cost_bps="2",
        taker_expected_cost_bps="4",
        uncertainty=0.2,
        model_version="execution-test-1",
        artifact_hash="d" * 64,
    )
    portfolio = PortfolioSnapshot(
        market="KRW-BTC",
        as_of=BASE_TIME,
        initial_cash="100000",
        cash_balance="100000",
        locked_cash="0",
        available_cash="100000",
        position_quantity="0",
        locked_quantity="0",
        average_entry_price=None,
        mark_price="100",
        market_value="0",
        realized_pnl="0",
        unrealized_pnl="0",
        gross_pnl="0",
        fees="0",
        spread_cost="0",
        slippage_cost="0",
        adverse_selection_cost="0",
        net_pnl="0",
        equity="100000",
        ledger_hash="0" * 64,
    )
    return StrategyInput(
        decision_at_utc=decision_at,
        market=MarketSnapshot(
            snapshot_id=UUID(int=1),
            market="KRW-BTC",
            event_time_utc=BASE_TIME,
            available_at_utc=BASE_TIME,
            mid_price="100",
            relative_spread_bps="2",
            bid_depth="50000",
            ask_depth="50000",
            market_active=True,
            warning_active=False,
        ),
        features=features,
        regime=regime,
        alpha=alpha,
        execution=execution,
        portfolio=portfolio,
        risk=RiskContext(
            context_id=UUID(int=5),
            market="KRW-BTC",
            as_of_utc=BASE_TIME,
            trading_mode="paper",
            kill_switch_active=False,
            strategy_paused=False,
            daily_loss_capacity_remaining_krw="10000",
            position_capacity_remaining_krw="50000",
            turnover_capacity_remaining_krw="500000",
            drawdown_pct="0",
        ),
    )


class _FixedStrategy:
    strategy_version = "1.0.0"

    def __init__(self, strategy_id: str, edge: Decimal) -> None:
        self.strategy_id = strategy_id
        self.edge = edge

    def evaluate(self, inputs: StrategyInput) -> StrategyDecision:
        cost = Decimal(2)
        return StrategyDecision(
            decision_id=deterministic_execution_id(self.strategy_id, inputs.market.snapshot_id),
            action=StrategyAction.TRADE,
            market=inputs.market.market,
            side="bid",
            target_notional="10000",
            order_preference=OrderPreference.BEST,
            expected_horizon_seconds=15,
            expected_gross_edge_bps=self.edge + cost,
            expected_cost_bps=cost,
            expected_net_edge_bps=self.edge,
            confidence=0.8,
            uncertainty=0.2,
            decided_at_utc=inputs.decision_at_utc,
            valid_until_utc=inputs.decision_at_utc + timedelta(seconds=10),
            invalidation_conditions=("NEW_DATA",),
            exit_plan="time stop",
            reason_codes=("FIXED_TEST_EDGE",),
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
        )


def _limits() -> RiskLimits:
    return RiskLimits(
        policy_version="phase5-test-1",
        min_order_notional_krw="1000",
        max_order_notional_krw="20000",
        max_position_notional_per_market="50000",
        max_total_exposure_krw="80000",
        max_total_exposure_pct="0.8",
        max_concurrent_positions=3,
        max_daily_loss_krw="10000",
        max_daily_loss_pct="0.1",
        max_drawdown_pct="0.2",
        max_strategy_loss_krw="5000",
        max_consecutive_losses=5,
        max_orders_per_minute=10,
        max_orders_per_market_per_minute=5,
        max_turnover_per_day="500000",
        max_relative_spread_bps="20",
        max_expected_slippage_bps="10",
        max_data_age_ms=1000,
        max_clock_skew_ms=500,
        max_unknown_orders=0,
        max_balance_age_seconds=30,
        max_balance_reconciliation_age_seconds=30,
        max_model_age_seconds=3600,
        max_prediction_age_seconds=10,
        max_prediction_uncertainty=0.5,
        min_expected_net_edge_bps="3",
    )


def _risk_snapshot(**updates: object) -> RiskSnapshot:
    values: dict[str, object] = {
        "snapshot_id": UUID(int=50),
        "market": "KRW-BTC",
        "captured_at_utc": BASE_TIME + timedelta(seconds=1),
        "trading_mode": "paper",
        "kill_switch_active": False,
        "market_active": True,
        "warning_active": False,
        "public_websocket_healthy": True,
        "private_websocket_healthy": False,
        "rest_healthy": False,
        "data_age_ms": 100,
        "clock_skew_ms": 10,
        "balance_age_seconds": 1,
        "reconciliation_age_seconds": 1,
        "model_available": True,
        "model_release_approved": True,
        "model_age_seconds": 60,
        "features_complete": True,
        "prediction_age_seconds": 1,
        "prediction_uncertainty": 0.2,
        "expected_net_edge_bps": "8",
        "relative_spread_bps": "2",
        "expected_slippage_bps": "2",
        "opposing_depth_notional": "50000",
        "reference_price": "100",
        "position_notional": "0",
        "total_exposure_krw": "0",
        "total_equity_krw": "100000",
        "concurrent_positions": 0,
        "available_cash_krw": "100000",
        "locked_cash_krw": "0",
        "daily_loss_krw": "0",
        "daily_loss_pct": "0",
        "drawdown_pct": "0",
        "strategy_loss_krw": "0",
        "consecutive_losses": 0,
        "orders_last_minute": 0,
        "market_orders_last_minute": 0,
        "turnover_today_krw": "0",
        "existing_open_order": False,
        "identifier_unique": True,
        "unknown_orders": 0,
        "volatility_scale": 1.0,
        "liquidity_scale": 1.0,
        "correlation_penalty": 0.0,
    }
    values.update(updates)
    return RiskSnapshot(**values)


def test_strategy_contract_is_causal_and_momentum_only_proposes() -> None:
    inputs = _strategy_input()
    decision = OfiMicropriceMomentum().evaluate(inputs)
    assert decision.action is StrategyAction.TRADE
    assert decision.side == "bid"

    payload = inputs.model_dump()
    payload["decision_at_utc"] = BASE_TIME - timedelta(seconds=1)
    with pytest.raises(ValidationError, match="future information"):
        StrategyInput(**payload)

    missing = _strategy_input(values={"mid_price": 100.0})
    assert OfiMicropriceMomentum().evaluate(missing).action is StrategyAction.ABSTAIN
    assert LiquidityShockMeanReversion().evaluate(inputs).action is StrategyAction.TRADE


def test_router_deduplicates_correlated_signals_by_edge_not_iteration_order() -> None:
    inputs = _strategy_input()
    low = _FixedStrategy("a-low-edge", Decimal(4))
    high = _FixedStrategy("z-high-edge", Decimal(9))
    router = StrategyRouter(
        (
            StrategyRouteConfig(
                strategy_id=low.strategy_id,
                status=StrategyStatus.ACTIVE,
                priority=10,
                correlation_group="order-flow",
                capacity_notional="20000",
                cooldown_seconds=30,
                max_strategy_loss="1000",
            ),
            StrategyRouteConfig(
                strategy_id=high.strategy_id,
                status=StrategyStatus.ACTIVE,
                priority=0,
                correlation_group="order-flow",
                capacity_notional="20000",
                cooldown_seconds=30,
                max_strategy_loss="1000",
            ),
        )
    )
    route = router.route(inputs, (low, high))
    assert route.selected.strategy_id == high.strategy_id
    assert (low.strategy_id, "CORRELATED_SIGNAL_DEDUPLICATED") in route.rejected_reasons

    cooldown_route = router.route(inputs, (low, high))
    assert cooldown_route.selected.strategy_id == low.strategy_id
    assert (high.strategy_id, "COOLDOWN") in cooldown_route.rejected_reasons


def test_universe_selector_rejects_warning_stale_and_illiquid_markets() -> None:
    policy = UniversePolicy(
        max_markets=1,
        max_data_age_ms=1000,
        min_coverage_ratio=0.99,
        min_quote_volume_24h="1000000",
        max_relative_spread_bps="20",
        min_depth_notional="100000",
    )
    healthy = UniverseCandidate(
        market="KRW-BTC",
        market_active=True,
        warning_active=False,
        data_age_ms=10,
        coverage_ratio=1,
        quote_volume_24h="5000000",
        relative_spread_bps="3",
        depth_notional="500000",
    )
    unsafe = healthy.model_copy(
        update={"market": "KRW-ALT", "warning_active": True, "data_age_ms": 2000}
    )
    selection = UniverseSelector(policy).select((unsafe, healthy), selected_at_utc=BASE_TIME)
    assert selection.selected_markets == ("KRW-BTC",)
    assert selection.rejected == (("KRW-ALT", ("WARNING", "STALE")),)


def test_gateway_always_runs_independent_risk_and_sizes_conservatively() -> None:
    decision = OfiMicropriceMomentum().evaluate(_strategy_input())
    result = StrategyRiskGateway(RiskEngine(_limits())).process(decision, _risk_snapshot())
    assert result.intent is not None
    assert result.risk_decision is not None
    assert result.risk_decision.decision is RiskDecisionType.RESIZE
    assert result.risk_decision.approved_notional == Decimal("6400.00")


def test_non_trade_decision_cannot_create_an_intent() -> None:
    hold = OfiMicropriceMomentum().evaluate(_strategy_input(values={"mid_price": 100.0}))
    result = StrategyRiskGateway(RiskEngine(_limits())).process(hold, _risk_snapshot())
    assert result.outcome == StrategyAction.ABSTAIN.value
    assert result.intent is None
    assert result.risk_decision is None


@pytest.mark.parametrize("strategy", (OfiMicropriceMomentum(), LiquidityShockMeanReversion()))
def test_alpha_hold_or_abstain_cannot_create_a_strategy_trade(strategy: object) -> None:
    inputs = _strategy_input()
    for action in (DecisionAction.HOLD, DecisionAction.ABSTAIN):
        alpha = inputs.alpha.model_copy(
            update={
                "action": action,
                "abstention_reasons": ("TEST_ABSTAIN",) if action is DecisionAction.ABSTAIN else (),
            }
        )
        guarded = inputs.model_copy(update={"alpha": alpha})

        decision = strategy.evaluate(guarded)  # type: ignore[attr-defined]

        assert decision.action is not StrategyAction.TRADE
        assert decision.order_preference is OrderPreference.NO_ORDER


@pytest.mark.parametrize(
    ("updates", "reason"),
    (
        ({"kill_switch_active": True}, "KILL_SWITCH_ACTIVE"),
        ({"data_age_ms": 1001}, "STALE_DATA"),
        ({"daily_loss_krw": "10000"}, "DAILY_LOSS_KRW"),
        ({"prediction_age_seconds": 11}, "STALE_PREDICTION"),
        ({"model_release_approved": False}, "MODEL_RELEASE_NOT_APPROVED"),
        ({"market": "KRW-ETH"}, "RISK_MARKET_MISMATCH"),
        ({"captured_at_utc": BASE_TIME}, "RISK_SNAPSHOT_PRECEDES_SIGNAL"),
        ({"expected_net_edge_bps": "7"}, "EDGE_SNAPSHOT_MISMATCH"),
    ),
)
def test_hard_risk_failures_reject_before_broker(updates: dict[str, object], reason: str) -> None:
    decision = OfiMicropriceMomentum().evaluate(_strategy_input())
    result = StrategyRiskGateway(RiskEngine(_limits())).process(decision, _risk_snapshot(**updates))
    assert result.risk_decision is not None
    assert result.risk_decision.decision is RiskDecisionType.REJECT
    assert reason in result.risk_decision.reason_codes


def test_strategy_package_has_no_order_or_exchange_capability() -> None:
    root = Path(__file__).parents[2] / "src" / "quantforge" / "strategies"
    source = "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.glob("*.py")))
    assert "quantforge.exchange" not in source
    assert "quantforge.execution" not in source
    assert "OrderIntent" not in source

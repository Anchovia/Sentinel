from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import orjson
import pytest

from factories import make_orderbook_event
from quantforge.backtest import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    compare_backtests,
    write_backtest_report,
)
from quantforge.domain import (
    EventEnvelope,
    OrderIntent,
    PaperExecutionPolicy,
    PaperFillModel,
    RiskDecision,
    RiskDecisionType,
    deterministic_execution_id,
)
from quantforge.replay.engine import ReplayItem

GOLDEN = Path(__file__).parents[1] / "fixtures" / "backtest" / "phase3_golden_expected.json"


class OneShotMarketBuy:
    def __init__(self, *, quantity: str = "5", future_dated: bool = False) -> None:
        self.quantity = quantity
        self.future_dated = future_dated
        self.emitted = False

    def on_item(
        self, item: ReplayItem, *, now: datetime, random_seed: int
    ) -> Sequence[OrderIntent]:
        if self.emitted or not isinstance(item, EventEnvelope) or item.event_type != "orderbook":
            return ()
        self.emitted = True
        signal_time = now + timedelta(seconds=1) if self.future_dated else now
        return (
            OrderIntent(
                intent_id=deterministic_execution_id("test-intent", item.event_id, random_seed),
                strategy_id="one-shot-buy",
                strategy_version="1",
                market=item.market,
                side="bid",
                requested_quantity=self.quantity,
                order_type="market",
                signal_timestamp=signal_time,
                expires_at=signal_time + timedelta(seconds=5),
                expected_gross_edge_bps=10,
                expected_cost_bps=5,
                expected_net_edge_bps=5,
                confidence=0.5,
                uncertainty=0.2,
                reason="deterministic backtest fixture",
            ),
        )


class AllowRisk:
    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow

    def evaluate(
        self,
        intent: OrderIntent,
        *,
        available_cash: Decimal,
        position_quantity: Decimal,
        now: datetime,
        random_seed: int,
    ) -> RiskDecision:
        del available_cash, position_quantity
        allowed = self.allow
        return RiskDecision(
            decision_id=deterministic_execution_id(
                "test-risk", intent.intent_id, now.isoformat(), random_seed, allowed
            ),
            intent_id=intent.intent_id,
            decision=RiskDecisionType.ALLOW if allowed else RiskDecisionType.REJECT,
            approved_quantity=intent.requested_quantity if allowed else None,
            reason_codes=("TEST_ALLOW" if allowed else "TEST_REJECT",),
            risk_snapshot_id=deterministic_execution_id(
                "test-risk-snapshot", now.isoformat(), random_seed
            ),
            policy_version="test-risk-1",
            decided_at=now,
        )


def _items() -> list[EventEnvelope]:
    return [
        make_orderbook_event(
            sequence=1,
            received_offset_ms=0,
            asks=((101, 1),),
            bids=((99, 1),),
        ),
        make_orderbook_event(
            sequence=2,
            received_offset_ms=100,
            asks=((101, 1),),
            bids=((99, 1),),
        ),
    ]


def _run(model: PaperFillModel, *, initial_cash: str = "10000") -> BacktestResult:
    config = BacktestConfig(
        market="KRW-BTC",
        initial_cash=initial_cash,
        code_version="phase3-test",
        random_seed=7,
        execution=PaperExecutionPolicy(
            model=model,
            order_latency_ms=100,
            depth_haircut="0.5",
            slippage_buffer_bps="1",
            adverse_selection_bps="2",
        ),
    )
    return BacktestEngine(config).run(_items(), strategy=OneShotMarketBuy(), risk=AllowRisk())


def test_same_inputs_config_code_and_seed_produce_identical_run() -> None:
    first = _run(PaperFillModel.CONSERVATIVE_L2)
    second = _run(PaperFillModel.CONSERVATIVE_L2)

    assert first.run_id == second.run_id
    assert first.output_hash == second.output_hash
    assert first.replay_output_hash == second.replay_output_hash
    assert first.portfolio.ledger_hash == second.portfolio.ledger_hash


def test_phase3_golden_backtest_hashes_are_frozen() -> None:
    naive = _run(PaperFillModel.NAIVE)
    conservative = _run(PaperFillModel.CONSERVATIVE_L2)
    actual = {
        "dataset_hash": naive.dataset_hash,
        "replay_config_hash": naive.replay_config_hash,
        "naive_run_id": naive.run_id,
        "naive_output_hash": naive.output_hash,
        "naive_replay_output_hash": naive.replay_output_hash,
        "naive_ledger_hash": naive.portfolio.ledger_hash,
        "naive_filled_quantity": str(naive.filled_quantity),
        "naive_net_pnl": str(naive.portfolio.net_pnl),
        "conservative_run_id": conservative.run_id,
        "conservative_output_hash": conservative.output_hash,
        "conservative_replay_output_hash": conservative.replay_output_hash,
        "conservative_ledger_hash": conservative.portfolio.ledger_hash,
        "conservative_filled_quantity": str(conservative.filled_quantity),
        "conservative_net_pnl": str(conservative.portfolio.net_pnl),
    }

    assert actual == orjson.loads(GOLDEN.read_bytes())


def test_naive_vs_conservative_comparison_exposes_optimistic_fill() -> None:
    naive = _run(PaperFillModel.NAIVE)
    conservative = _run(PaperFillModel.CONSERVATIVE_L2)
    comparison = compare_backtests(naive, conservative)

    assert naive.filled_quantity == Decimal(5)
    assert conservative.filled_quantity == Decimal("0.5")
    assert comparison.naive_minus_conservative_filled_quantity == Decimal("4.5")
    assert comparison.optimism_detected
    assert conservative.portfolio.spread_cost > 0
    assert conservative.portfolio.slippage_cost > 0
    assert conservative.portfolio.adverse_selection_cost > 0


def test_report_is_atomic_json_with_full_provenance(tmp_path: Path) -> None:
    report = compare_backtests(_run(PaperFillModel.NAIVE), _run(PaperFillModel.CONSERVATIVE_L2))
    destination = write_backtest_report(report, tmp_path / "comparison.json")
    parsed = orjson.loads(destination.read_bytes())

    assert parsed["naive"]["dataset_hash"] == parsed["conservative"]["dataset_hash"]
    assert parsed["conservative"]["execution_policy_hash"]
    assert not list(tmp_path.glob("*.tmp"))


def test_future_strategy_intent_is_a_lookahead_violation() -> None:
    config = BacktestConfig(market="KRW-BTC", initial_cash="1000", code_version="phase3-test")
    with pytest.raises(ValueError, match="future-dated"):
        BacktestEngine(config).run(
            _items(), strategy=OneShotMarketBuy(future_dated=True), risk=AllowRisk()
        )


def test_risk_rejection_and_accounting_preflight_are_fail_closed() -> None:
    config = BacktestConfig(market="KRW-BTC", initial_cash="1000", code_version="phase3-test")
    rejected = BacktestEngine(config).run(
        _items(), strategy=OneShotMarketBuy(), risk=AllowRisk(allow=False)
    )
    assert rejected.risk_rejection_count == 1
    assert rejected.order_count == 0
    assert rejected.fill_count == 0

    prevented = _run(PaperFillModel.CONSERVATIVE_L2, initial_cash="10")
    assert prevented.submission_rejection_count == 1
    assert prevented.fill_count == 0
    assert prevented.orders[0].reject_reason == "insufficient available cash for reservation"


def test_comparison_rejects_different_dataset_provenance() -> None:
    naive = _run(PaperFillModel.NAIVE)
    conservative = _run(PaperFillModel.CONSERVATIVE_L2).model_copy(
        update={"dataset_hash": "f" * 64}
    )
    with pytest.raises(ValueError, match="comparable provenance"):
        compare_backtests(naive, conservative)

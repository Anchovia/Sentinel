from datetime import timedelta
from decimal import Decimal

import pytest

from factories import BASE_TIME
from quantforge.portfolio import AttributionLedger
from quantforge.risk import KillSwitch, KillSwitchAction, KillSwitchMode, KillSwitchState


def test_kill_switch_requires_manual_reconciled_release() -> None:
    switch = KillSwitch()
    switch.activate(
        KillSwitchMode.CANCEL_ONLY,
        reason="DAILY_LOSS_LIMIT",
        occurred_at_utc=BASE_TIME,
    )
    assert switch.active
    switch.request_release(
        operator_approval_id="operator-review-1",
        occurred_at_utc=BASE_TIME + timedelta(seconds=1),
    )
    blocked = switch.complete_release(
        reconciliation_ok=False,
        occurred_at_utc=BASE_TIME + timedelta(seconds=2),
    )
    assert blocked.action is KillSwitchAction.RELEASE_BLOCKED
    assert switch.state is KillSwitchState.RELEASE_PENDING
    released = switch.complete_release(
        reconciliation_ok=True,
        occurred_at_utc=BASE_TIME + timedelta(seconds=3),
    )
    assert released.action is KillSwitchAction.RELEASED
    assert switch.state is KillSwitchState.INACTIVE
    assert switch.verify_chain()


def test_flatten_mode_requires_approval_and_safe_liquidity() -> None:
    switch = KillSwitch()
    with pytest.raises(ValueError, match="operator approval"):
        switch.activate(
            KillSwitchMode.CANCEL_AND_FLATTEN,
            reason="EMERGENCY",
            occurred_at_utc=BASE_TIME,
        )
    switch.activate(
        KillSwitchMode.CANCEL_AND_FLATTEN,
        reason="EMERGENCY",
        occurred_at_utc=BASE_TIME,
        operator_approval_id="operator-review-2",
        liquidity_safe=True,
    )
    assert switch.events[0].mode is KillSwitchMode.CANCEL_AND_FLATTEN


def test_attribution_reconciles_costs_and_aggregates_exactly() -> None:
    ledger = AttributionLedger()
    first = ledger.append(
        attributed_at_utc=BASE_TIME,
        strategy_id="strategy-a",
        strategy_version="1",
        model_version="model-a",
        market="KRW-BTC",
        regime="UPTREND_LOW_VOL",
        gross_edge_pnl="100",
        fees="10",
        spread_cost="5",
        slippage_cost="3",
        adverse_selection_cost="2",
    )
    ledger.append(
        attributed_at_utc=BASE_TIME + timedelta(seconds=1),
        strategy_id="strategy-a",
        strategy_version="1",
        model_version="model-a",
        market="KRW-BTC",
        regime="RANGE_LOW_VOL",
        gross_edge_pnl="50",
        fees="5",
        spread_cost="2",
        slippage_cost="1",
        adverse_selection_cost="2",
    )
    assert first.net_pnl == Decimal(80)
    assert ledger.totals_by("strategy_id") == {"strategy-a": Decimal(120)}
    assert ledger.totals_by("regime") == {
        "UPTREND_LOW_VOL": Decimal(80),
        "RANGE_LOW_VOL": Decimal(40),
    }
    assert ledger.verify_chain()


def test_attribution_rejects_unknown_dimension() -> None:
    with pytest.raises(ValueError, match="unsupported attribution dimension"):
        AttributionLedger().totals_by("account")

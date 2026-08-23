from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from quantforge.domain.orders import (
    InvalidOrderTransition,
    OrderIntent,
    OrderStateMachine,
    OrderStatus,
)


def _intent(**overrides: object) -> OrderIntent:
    now = datetime.now(tz=UTC)
    values: dict[str, object] = {
        "strategy_id": "test-strategy",
        "strategy_version": "1.0.0",
        "market": "KRW-BTC",
        "side": "bid",
        "requested_notional": "10000",
        "order_type": "limit",
        "limit_price": "100000000",
        "signal_timestamp": now,
        "expires_at": now + timedelta(seconds=5),
        "expected_gross_edge_bps": 5.0,
        "expected_cost_bps": 3.0,
        "expected_net_edge_bps": 2.0,
        "confidence": 0.6,
        "uncertainty": 0.2,
        "reason": "unit test",
    }
    values.update(overrides)
    return OrderIntent(**values)


def test_order_intent_accepts_decimal_strings() -> None:
    intent = _intent()

    assert str(intent.requested_notional) == "10000"
    assert str(intent.limit_price) == "100000000"


def test_order_intent_rejects_binary_float_at_money_boundary() -> None:
    with pytest.raises(ValidationError, match="monetary"):
        _intent(requested_notional=10000.0)


def test_order_intent_requires_exactly_one_requested_amount() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        _intent(requested_quantity="0.001")


def test_order_intent_requires_positive_amount_and_price() -> None:
    with pytest.raises(ValidationError, match="requested amount"):
        _intent(requested_notional="0")
    with pytest.raises(ValidationError, match="limit price"):
        _intent(limit_price="0")


def test_order_intent_requires_aware_ordered_timestamps() -> None:
    naive = datetime.now()
    with pytest.raises(ValidationError, match="timezone-aware"):
        _intent(signal_timestamp=naive, expires_at=naive + timedelta(seconds=1))

    now = datetime.now(tz=UTC)
    with pytest.raises(ValidationError, match="later"):
        _intent(signal_timestamp=now, expires_at=now)


def test_valid_state_transition() -> None:
    assert (
        OrderStateMachine.transition(OrderStatus.INTENT_CREATED, OrderStatus.RISK_APPROVED)
        is OrderStatus.RISK_APPROVED
    )


def test_invalid_state_transition_is_rejected() -> None:
    with pytest.raises(InvalidOrderTransition):
        OrderStateMachine.transition(OrderStatus.INTENT_CREATED, OrderStatus.FILLED)


def test_unknown_order_can_only_enter_reconciliation() -> None:
    assert OrderStateMachine.can_transition(OrderStatus.UNKNOWN, OrderStatus.RECONCILING)
    assert not OrderStateMachine.can_transition(OrderStatus.UNKNOWN, OrderStatus.SUBMITTED)


def test_paper_example_is_valid_and_short_lived() -> None:
    intent = OrderIntent.paper_example()

    assert intent.market == "KRW-BTC"
    assert intent.expires_at > intent.signal_timestamp

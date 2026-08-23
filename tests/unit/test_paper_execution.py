from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from factories import BASE_TIME, make_orderbook_event, make_trade_event
from quantforge.domain import (
    DataGap,
    DataGapReason,
    OrderIntent,
    OrderStatus,
    PaperExecutionPolicy,
    PaperFillModel,
    RiskDecision,
    RiskDecisionType,
)
from quantforge.execution import PaperBroker, PaperExecutionRejected


def _intent(**overrides: object) -> OrderIntent:
    values: dict[str, object] = {
        "intent_id": UUID(int=101),
        "strategy_id": "paper-test",
        "strategy_version": "1",
        "market": "KRW-BTC",
        "side": "bid",
        "requested_notional": "101",
        "order_type": "market",
        "signal_timestamp": BASE_TIME,
        "expires_at": BASE_TIME + timedelta(seconds=5),
        "expected_gross_edge_bps": 10,
        "expected_cost_bps": 5,
        "expected_net_edge_bps": 5,
        "confidence": 0.5,
        "uncertainty": 0.2,
        "reason": "deterministic paper test",
    }
    values.update(overrides)
    return OrderIntent(**values)


def _decision(intent: OrderIntent, **overrides: object) -> RiskDecision:
    values: dict[str, object] = {
        "decision_id": UUID(int=201),
        "intent_id": intent.intent_id,
        "decision": RiskDecisionType.ALLOW,
        "approved_notional": intent.requested_notional,
        "reason_codes": ("TEST_ALLOW",),
        "risk_snapshot_id": UUID(int=301),
        "policy_version": "test-1",
        "decided_at": BASE_TIME,
    }
    values.update(overrides)
    return RiskDecision(**values)


def test_policy_forbids_zero_fees_except_explicit_research_comparison() -> None:
    with pytest.raises(ValidationError, match="zero fees"):
        PaperExecutionPolicy(maker_fee_rate="0")

    policy = PaperExecutionPolicy(
        maker_fee_rate="0", taker_fee_rate="0", research_allow_zero_fees=True
    )
    assert policy.research_allow_zero_fees


def test_calibrated_model_requires_lineage() -> None:
    with pytest.raises(ValidationError, match="calibration_id"):
        PaperExecutionPolicy(model=PaperFillModel.CALIBRATED_L2)


def test_conservative_market_order_waits_for_latency_and_partially_fills() -> None:
    policy = PaperExecutionPolicy(
        order_latency_ms=100,
        depth_haircut="0.5",
        slippage_buffer_bps="1",
        adverse_selection_bps="2",
    )
    broker = PaperBroker(policy)
    first = make_orderbook_event(
        sequence=1, received_offset_ms=0, asks=((101, 1),), bids=((99, 1),)
    )
    broker.on_item(first, now=first.received_at_utc)
    intent = _intent(requested_notional=None, requested_quantity="1")
    submitted = broker.submit(
        intent,
        _decision(intent, approved_notional=None, approved_quantity="1"),
        submitted_at=BASE_TIME,
    )

    assert submitted.order.status is OrderStatus.SUBMITTED
    assert broker.on_item(first.model_copy(update={"event_id": UUID(int=2)}), now=BASE_TIME) == ()

    arrival_book = make_orderbook_event(
        sequence=3, received_offset_ms=100, asks=((101, 1),), bids=((99, 1),)
    )
    updates = broker.on_item(arrival_book, now=arrival_book.received_at_utc)

    assert updates[-1].order.status is OrderStatus.CANCELED
    assert updates[-1].order.remaining_quantity == Decimal("0.5")
    assert updates[-1].fills[0].quantity == Decimal("0.5")
    assert updates[-1].fills[0].price > Decimal(101)
    assert updates[-1].fills[0].fee > 0


def test_naive_model_fills_full_quantity_at_midpoint() -> None:
    broker = PaperBroker(PaperExecutionPolicy(model=PaperFillModel.NAIVE, order_latency_ms=0))
    book = make_orderbook_event(sequence=1, received_offset_ms=0, asks=((101, 1),), bids=((99, 1),))
    broker.on_item(book, now=BASE_TIME)
    intent = _intent(requested_notional=None, requested_quantity="5")
    broker.submit(
        intent,
        _decision(intent, approved_notional=None, approved_quantity="5"),
        submitted_at=BASE_TIME,
    )
    updates = broker.on_item(book.model_copy(update={"event_id": UUID(int=2)}), now=BASE_TIME)

    assert updates[-1].order.status is OrderStatus.FILLED
    assert updates[-1].fills[0].quantity == Decimal(5)
    assert updates[-1].fills[0].price == Decimal(100)


def test_passive_limit_queue_requires_aggressive_volume_beyond_queue_ahead() -> None:
    broker = PaperBroker(
        PaperExecutionPolicy(
            order_latency_ms=0,
            queue_factor="1",
            snapshot_decrease_fill_fraction="0",
        )
    )
    book = make_orderbook_event(sequence=1, received_offset_ms=0, asks=((101, 1),), bids=((99, 2),))
    broker.on_item(book, now=BASE_TIME)
    intent = _intent(
        requested_notional=None,
        requested_quantity="1",
        order_type="limit",
        limit_price="99",
    )
    broker.submit(
        intent,
        _decision(intent, approved_notional=None, approved_quantity="1"),
        submitted_at=BASE_TIME,
    )
    broker.on_item(book.model_copy(update={"event_id": UUID(int=2)}), now=BASE_TIME)

    first_trade = make_trade_event(
        sequence=3,
        exchange_offset_ms=100,
        received_offset_ms=100,
        price=99,
        volume=2,
        ask_bid="ASK",
    )
    first_updates = broker.on_item(first_trade, now=first_trade.received_at_utc)
    assert first_updates[-1].fills == ()

    second_trade = make_trade_event(
        sequence=4,
        exchange_offset_ms=200,
        received_offset_ms=200,
        price=99,
        volume=1,
        ask_bid="ASK",
    )
    second_updates = broker.on_item(second_trade, now=second_trade.received_at_utc)
    assert second_updates[-1].order.status is OrderStatus.FILLED
    assert second_updates[-1].fills[0].quantity == Decimal(1)


def test_post_only_cross_is_rejected_and_gap_invalidates_market() -> None:
    broker = PaperBroker(PaperExecutionPolicy(order_latency_ms=0))
    book = make_orderbook_event(sequence=1, received_offset_ms=0)
    broker.on_item(book, now=BASE_TIME)
    intent = _intent(order_type="post_only", limit_price="101")
    broker.submit(intent, _decision(intent), submitted_at=BASE_TIME)
    updates = broker.on_item(book.model_copy(update={"event_id": UUID(int=2)}), now=BASE_TIME)
    assert updates[-1].order.status is OrderStatus.REJECTED


def test_rejects_non_approved_future_or_mismatched_submission() -> None:
    broker = PaperBroker()
    book = make_orderbook_event(sequence=1, received_offset_ms=0)
    broker.on_item(book, now=BASE_TIME)
    intent = _intent()

    with pytest.raises(PaperExecutionRejected, match="risk did not approve"):
        broker.submit(
            intent,
            _decision(
                intent,
                decision=RiskDecisionType.REJECT,
                approved_notional=None,
            ),
            submitted_at=BASE_TIME,
        )
    with pytest.raises(PaperExecutionRejected, match="does not belong"):
        broker.submit(
            intent,
            _decision(intent, intent_id=UUID(int=999)),
            submitted_at=BASE_TIME,
        )


def test_fok_does_not_leak_a_partial_fill() -> None:
    broker = PaperBroker(PaperExecutionPolicy(order_latency_ms=0, depth_haircut="0.5"))
    book = make_orderbook_event(sequence=1, received_offset_ms=0, asks=((101, 1),), bids=((99, 1),))
    broker.on_item(book, now=BASE_TIME)
    intent = _intent(
        requested_notional=None,
        requested_quantity="1",
        order_type="fok",
        limit_price="102",
    )
    broker.submit(
        intent,
        _decision(intent, approved_notional=None, approved_quantity="1"),
        submitted_at=BASE_TIME,
    )
    updates = broker.on_item(book.model_copy(update={"event_id": UUID(int=2)}), now=BASE_TIME)

    assert updates[-1].order.status is OrderStatus.CANCELED
    assert updates[-1].fills == ()
    assert broker.fills == ()


def test_trade_can_fill_during_cancel_latency_window() -> None:
    broker = PaperBroker(
        PaperExecutionPolicy(
            order_latency_ms=0,
            cancel_latency_ms=100,
            queue_factor="0",
            snapshot_decrease_fill_fraction="0",
        )
    )
    book = make_orderbook_event(sequence=1, received_offset_ms=0, asks=((101, 1),), bids=((99, 1),))
    broker.on_item(book, now=BASE_TIME)
    intent = _intent(
        requested_notional=None,
        requested_quantity="1",
        order_type="limit",
        limit_price="99",
    )
    submitted = broker.submit(
        intent,
        _decision(intent, approved_notional=None, approved_quantity="1"),
        submitted_at=BASE_TIME,
    )
    broker.on_item(book.model_copy(update={"event_id": UUID(int=2)}), now=BASE_TIME)
    pending = broker.request_cancel(submitted.order.order_id, requested_at=BASE_TIME)
    assert pending.order.status is OrderStatus.CANCEL_PENDING

    trade = make_trade_event(
        sequence=3,
        exchange_offset_ms=50,
        received_offset_ms=50,
        price=99,
        volume=1,
        ask_bid="ASK",
    )
    updates = broker.on_item(trade, now=trade.received_at_utc)
    assert updates[-1].order.status is OrderStatus.FILLED
    assert updates[-1].fills[0].quantity == Decimal(1)


def test_data_gap_cancels_orders_and_stale_books_are_rejected() -> None:
    broker = PaperBroker(PaperExecutionPolicy(order_latency_ms=500, max_book_age_ms=50))
    book = make_orderbook_event(sequence=1, received_offset_ms=0)
    broker.on_item(book, now=BASE_TIME)
    intent = _intent()
    broker.submit(intent, _decision(intent), submitted_at=BASE_TIME)
    gap = DataGap(
        market="KRW-BTC",
        start_utc=BASE_TIME,
        end_utc=BASE_TIME + timedelta(milliseconds=50),
        known_at_utc=BASE_TIME + timedelta(milliseconds=100),
        reason=DataGapReason.CONNECTION_LOST,
        details="paper broker gap test",
    )
    updates = broker.on_item(gap, now=gap.known_at_utc)
    assert updates[-1].order.status is OrderStatus.CANCELED

    with pytest.raises(PaperExecutionRejected, match="unsafe"):
        broker.submit(
            _intent(intent_id=UUID(int=102)),
            _decision(_intent(intent_id=UUID(int=102)), decision_id=UUID(int=202)),
            submitted_at=gap.known_at_utc,
        )

    stale_broker = PaperBroker(PaperExecutionPolicy(max_book_age_ms=50))
    stale_broker.on_item(book, now=BASE_TIME)
    with pytest.raises(PaperExecutionRejected, match="stale"):
        stale_broker.submit(
            _intent(intent_id=UUID(int=103)),
            _decision(_intent(intent_id=UUID(int=103)), decision_id=UUID(int=203)),
            submitted_at=BASE_TIME + timedelta(milliseconds=100),
        )

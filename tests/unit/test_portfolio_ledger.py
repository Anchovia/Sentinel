from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from factories import BASE_TIME
from quantforge.domain import (
    LiquidityRole,
    OrderStatus,
    PaperFill,
    PaperFillModel,
    PaperOrder,
    PaperOrderType,
    TimeInForce,
)
from quantforge.portfolio import AccountingInvariantError, PortfolioLedger


def _fill(*, sequence: int, side: str, price: str, quantity: str) -> PaperFill:
    decimal_price = Decimal(price)
    decimal_quantity = Decimal(quantity)
    notional = decimal_price * decimal_quantity
    fee_rate = Decimal("0.001")
    return PaperFill(
        fill_id=UUID(int=1_000 + sequence),
        order_id=UUID(int=2_000 + sequence),
        sequence=1,
        market="KRW-BTC",
        side=side,
        quantity=decimal_quantity,
        price=decimal_price,
        notional=notional,
        fee=notional * fee_rate,
        fee_rate=fee_rate,
        liquidity_role=LiquidityRole.TAKER,
        filled_at=BASE_TIME + timedelta(seconds=sequence),
        source_event_id=UUID(int=3_000 + sequence),
        reference_mid=decimal_price,
        spread_cost="1",
        slippage_cost="2",
        adverse_selection_cost="3",
        model=PaperFillModel.CONSERVATIVE_L2,
    )


def _order(*, side: str = "bid", quantity: str = "1") -> PaperOrder:
    return PaperOrder(
        order_id=UUID(int=9_001 if side == "bid" else 9_002),
        intent_id=UUID(int=8_001),
        decision_id=UUID(int=8_002),
        market="KRW-BTC",
        side=side,
        order_type=PaperOrderType.MARKET,
        time_in_force=TimeInForce.IOC,
        original_quantity=quantity,
        remaining_quantity=quantity,
        reference_mid="100",
        submitted_at=BASE_TIME,
        arrival_at=BASE_TIME,
        status=OrderStatus.SUBMITTED,
        policy_hash="a" * 64,
    )


def test_buy_sell_fifo_and_pnl_reconcile_exactly() -> None:
    ledger = PortfolioLedger(market="KRW-BTC", initial_cash="1000")
    buy = _fill(sequence=1, side="bid", price="100", quantity="2")
    sell = _fill(sequence=2, side="ask", price="110", quantity="1")

    ledger.apply_fill(buy)
    ledger.apply_fill(sell)
    snapshot = ledger.snapshot(mark_price=Decimal(110), as_of=BASE_TIME + timedelta(seconds=3))
    ledger.verify()

    assert snapshot.cash_balance == Decimal("909.69")
    assert snapshot.position_quantity == Decimal(1)
    assert snapshot.realized_pnl == Decimal(10)
    assert snapshot.unrealized_pnl == Decimal(10)
    assert snapshot.gross_pnl == Decimal(20)
    assert snapshot.fees == Decimal("0.31")
    assert snapshot.net_pnl == Decimal("19.69")
    assert snapshot.equity == Decimal("1019.69")
    assert snapshot.spread_cost == Decimal(2)
    assert snapshot.slippage_cost == Decimal(4)
    assert snapshot.adverse_selection_cost == Decimal(6)


def test_fifo_consumes_oldest_lot_first() -> None:
    ledger = PortfolioLedger(market="KRW-BTC", initial_cash="1000")
    ledger.apply_fill(_fill(sequence=1, side="bid", price="100", quantity="1"))
    ledger.apply_fill(_fill(sequence=2, side="bid", price="120", quantity="1"))
    ledger.apply_fill(_fill(sequence=3, side="ask", price="130", quantity="1.5"))

    assert ledger.realized_gross_pnl == Decimal(35)
    assert len(ledger.lots) == 1
    assert ledger.lots[0].entry_price == Decimal(120)
    assert ledger.lots[0].remaining_quantity == Decimal("0.5")


def test_duplicate_and_short_sell_are_rejected_before_mutation() -> None:
    ledger = PortfolioLedger(market="KRW-BTC", initial_cash="1000")
    buy = _fill(sequence=1, side="bid", price="100", quantity="1")
    ledger.apply_fill(buy)
    record_count = len(ledger.records)

    with pytest.raises(AccountingInvariantError, match="already applied"):
        ledger.apply_fill(buy)
    assert len(ledger.records) == record_count

    with pytest.raises(AccountingInvariantError, match="position negative"):
        ledger.apply_fill(_fill(sequence=2, side="ask", price="100", quantity="2"))
    assert ledger.position_quantity == Decimal(1)


def test_cash_and_position_reservations_are_released() -> None:
    ledger = PortfolioLedger(market="KRW-BTC", initial_cash="1000")
    bid = _order()
    ledger.reserve_order(bid, at=BASE_TIME, cash_amount=Decimal(200))
    assert ledger.available_cash == Decimal(800)
    ledger.release_order(bid.order_id, at=BASE_TIME + timedelta(seconds=1))
    assert ledger.available_cash == Decimal(1000)

    ledger.apply_fill(_fill(sequence=1, side="bid", price="100", quantity="2"))
    ask = _order(side="ask", quantity="1")
    ledger.reserve_order(ask, at=BASE_TIME, cash_amount=None)
    assert ledger.locked_quantity == Decimal(1)
    ledger.release_order(ask.order_id, at=BASE_TIME + timedelta(seconds=1))
    assert ledger.locked_quantity == 0


def test_reservations_and_initial_cash_fail_closed() -> None:
    with pytest.raises(AccountingInvariantError, match="exact"):
        PortfolioLedger(market="KRW-BTC", initial_cash=1000.0)

    ledger = PortfolioLedger(market="KRW-BTC", initial_cash="10")
    with pytest.raises(AccountingInvariantError, match="insufficient"):
        ledger.reserve_order(_order(), at=BASE_TIME, cash_amount=Decimal(11))


def test_hash_chain_detects_tampering() -> None:
    ledger = PortfolioLedger(market="KRW-BTC", initial_cash="1000")
    ledger.apply_fill(_fill(sequence=1, side="bid", price="100", quantity="1"))
    ledger._records[0] = ledger._records[0].model_copy(update={"amount": Decimal(999)})

    with pytest.raises(AccountingInvariantError, match="hash"):
        ledger.verify()

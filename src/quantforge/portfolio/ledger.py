"""Append-only Decimal portfolio ledger with FIFO lots and a verified hash chain."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Annotated
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import (
    OrderIntent,
    PaperExecutionUpdate,
    PaperFill,
    PaperOrder,
    RiskDecision,
    deterministic_execution_id,
)
from quantforge.domain.money import MonetaryDecimal

ZERO_HASH = "0" * 64


class AccountingInvariantError(ValueError):
    """Raised before an operation could make the accounting state inconsistent."""


class LedgerRecordType(StrEnum):
    INTENT = "intent"
    RISK_DECISION = "risk_decision"
    ORDER_STATE = "order_state"
    CASH_LOCK = "cash_lock"
    POSITION_LOCK = "position_lock"
    CASH_RELEASE = "cash_release"
    POSITION_RELEASE = "position_release"
    FILL = "fill"
    FEE = "fee"
    BALANCE = "balance"
    LOT_OPENED = "lot_opened"
    LOT_REDUCED = "lot_reduced"
    VALUATION = "valuation"
    ATTRIBUTION = "attribution"


class PositionLot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lot_id: UUID
    source_fill_id: UUID
    opened_at: datetime
    entry_price: MonetaryDecimal = Field(gt=0)
    original_quantity: MonetaryDecimal = Field(gt=0)
    remaining_quantity: MonetaryDecimal = Field(ge=0)

    @field_validator("opened_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("lot timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_quantity(self) -> "PositionLot":
        if self.remaining_quantity > self.original_quantity:
            raise ValueError("remaining lot quantity cannot exceed original quantity")
        return self


class LedgerRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: Annotated[int, Field(ge=1)]
    record_id: UUID
    recorded_at: datetime
    record_type: LedgerRecordType
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    order_id: UUID | None = None
    fill_id: UUID | None = None
    amount: MonetaryDecimal = Decimal(0)
    quantity: MonetaryDecimal = Decimal(0)
    cash_balance: MonetaryDecimal
    locked_cash: MonetaryDecimal = Field(ge=0)
    position_quantity: MonetaryDecimal = Field(ge=0)
    locked_quantity: MonetaryDecimal = Field(ge=0)
    realized_gross_pnl: MonetaryDecimal
    cumulative_fees: MonetaryDecimal = Field(ge=0)
    details: tuple[tuple[str, str], ...] = ()
    previous_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("recorded_at")
    @classmethod
    def require_record_time_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("ledger timestamp must be UTC-aware")
        return value


class PortfolioSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str
    as_of: datetime
    initial_cash: MonetaryDecimal = Field(ge=0)
    cash_balance: MonetaryDecimal
    locked_cash: MonetaryDecimal = Field(ge=0)
    available_cash: MonetaryDecimal
    position_quantity: MonetaryDecimal = Field(ge=0)
    locked_quantity: MonetaryDecimal = Field(ge=0)
    average_entry_price: MonetaryDecimal | None
    mark_price: MonetaryDecimal = Field(gt=0)
    market_value: MonetaryDecimal = Field(ge=0)
    realized_pnl: MonetaryDecimal
    unrealized_pnl: MonetaryDecimal
    gross_pnl: MonetaryDecimal
    fees: MonetaryDecimal = Field(ge=0)
    spread_cost: MonetaryDecimal = Field(ge=0)
    slippage_cost: MonetaryDecimal = Field(ge=0)
    adverse_selection_cost: MonetaryDecimal = Field(ge=0)
    net_pnl: MonetaryDecimal
    equity: MonetaryDecimal
    ledger_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("as_of")
    @classmethod
    def require_snapshot_time_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("portfolio snapshot timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_snapshot_arithmetic(self) -> "PortfolioSnapshot":
        if self.available_cash != self.cash_balance - self.locked_cash:
            raise ValueError("available cash does not reconcile")
        if self.market_value != self.position_quantity * self.mark_price:
            raise ValueError("market value does not reconcile")
        if self.gross_pnl != self.realized_pnl + self.unrealized_pnl:
            raise ValueError("gross PnL does not reconcile")
        if self.net_pnl != self.gross_pnl - self.fees:
            raise ValueError("net PnL does not reconcile")
        if self.equity != self.cash_balance + self.market_value:
            raise ValueError("equity does not reconcile")
        if self.net_pnl != self.equity - self.initial_cash:
            raise ValueError("net PnL and equity do not reconcile")
        return self


@dataclass
class _Reservation:
    side: str
    cash: Decimal = Decimal(0)
    quantity: Decimal = Decimal(0)


class PortfolioLedger:
    """Single-market spot ledger; every mutation emits immutable audit records."""

    def __init__(self, *, market: str, initial_cash: Decimal | int | str) -> None:
        if isinstance(initial_cash, (bool, float)):
            raise AccountingInvariantError("initial cash must be exact")
        value = Decimal(str(initial_cash))
        if not value.is_finite() or value < 0:
            raise AccountingInvariantError("initial cash must be finite and non-negative")
        self.market = market
        self.initial_cash = value
        self.cash_balance = value
        self.locked_cash = Decimal(0)
        self.realized_gross_pnl = Decimal(0)
        self.cumulative_fees = Decimal(0)
        self.spread_cost = Decimal(0)
        self.slippage_cost = Decimal(0)
        self.adverse_selection_cost = Decimal(0)
        self._lots: list[PositionLot] = []
        self._records: list[LedgerRecord] = []
        self._reservations: dict[UUID, _Reservation] = {}
        self._applied_fills: set[UUID] = set()

    @property
    def lots(self) -> tuple[PositionLot, ...]:
        return tuple(self._lots)

    @property
    def records(self) -> tuple[LedgerRecord, ...]:
        return tuple(self._records)

    @property
    def position_quantity(self) -> Decimal:
        return sum((lot.remaining_quantity for lot in self._lots), start=Decimal(0))

    @property
    def locked_quantity(self) -> Decimal:
        return sum((item.quantity for item in self._reservations.values()), start=Decimal(0))

    @property
    def available_cash(self) -> Decimal:
        return self.cash_balance - self.locked_cash

    def record_intent(self, intent: OrderIntent) -> LedgerRecord:
        self._require_market(intent.market)
        return self._append(
            LedgerRecordType.INTENT,
            intent.signal_timestamp,
            details=(("intent_id", str(intent.intent_id)), ("side", intent.side)),
        )

    def record_risk_decision(self, decision: RiskDecision) -> LedgerRecord:
        return self._append(
            LedgerRecordType.RISK_DECISION,
            decision.decided_at,
            details=(
                ("decision_id", str(decision.decision_id)),
                ("decision", decision.decision.value),
                ("intent_id", str(decision.intent_id)),
            ),
        )

    def record_order_update(self, update: PaperExecutionUpdate) -> LedgerRecord:
        self._require_market(update.order.market)
        return self._append(
            LedgerRecordType.ORDER_STATE,
            update.occurred_at,
            order_id=update.order.order_id,
            quantity=update.order.remaining_quantity,
            details=(("reason", update.reason), ("status", update.order.status.value)),
        )

    def reserve_order(
        self,
        order: PaperOrder,
        *,
        at: datetime,
        cash_amount: Decimal | None = None,
    ) -> LedgerRecord:
        self._require_market(order.market)
        if order.order_id in self._reservations:
            raise AccountingInvariantError("order already has a reservation")
        if order.side == "bid":
            if cash_amount is None or cash_amount <= 0:
                raise AccountingInvariantError("bid reservation requires positive cash")
            if cash_amount > self.available_cash:
                raise AccountingInvariantError("insufficient available cash for reservation")
            reservation = _Reservation(side=order.side, cash=cash_amount)
            self.locked_cash += cash_amount
            record_type = LedgerRecordType.CASH_LOCK
            amount = cash_amount
            quantity = Decimal(0)
        else:
            quantity = order.original_quantity
            if quantity > self.position_quantity - self.locked_quantity:
                raise AccountingInvariantError("insufficient available position for reservation")
            reservation = _Reservation(side=order.side, quantity=quantity)
            record_type = LedgerRecordType.POSITION_LOCK
            amount = Decimal(0)
        self._reservations[order.order_id] = reservation
        return self._append(
            record_type,
            at,
            order_id=order.order_id,
            amount=amount,
            quantity=quantity,
        )

    def release_order(self, order_id: UUID, *, at: datetime) -> LedgerRecord | None:
        reservation = self._reservations.pop(order_id, None)
        if reservation is None:
            return None
        if reservation.side == "bid":
            self.locked_cash -= reservation.cash
            return self._append(
                LedgerRecordType.CASH_RELEASE,
                at,
                order_id=order_id,
                amount=reservation.cash,
            )
        return self._append(
            LedgerRecordType.POSITION_RELEASE,
            at,
            order_id=order_id,
            quantity=reservation.quantity,
        )

    def apply_fill(self, fill: PaperFill) -> tuple[LedgerRecord, ...]:
        self._require_market(fill.market)
        if fill.fill_id in self._applied_fills:
            raise AccountingInvariantError("fill was already applied")
        before_cash = self.cash_balance
        before_quantity = self.position_quantity
        reservation = self._reservations.get(fill.order_id)
        realized_delta = Decimal(0)

        if fill.side == "bid":
            cash_delta, quantity_delta, lot_record_type = self._apply_bid(fill, reservation)
        else:
            (
                cash_delta,
                quantity_delta,
                realized_delta,
                lot_record_type,
            ) = self._apply_ask(fill, reservation)

        self.cumulative_fees += fill.fee
        self.spread_cost += fill.spread_cost
        self.slippage_cost += fill.slippage_cost
        self.adverse_selection_cost += fill.adverse_selection_cost
        self._applied_fills.add(fill.fill_id)
        if self.cash_balance - before_cash != cash_delta:
            raise AccountingInvariantError("cash delta failed to reconcile")
        if self.position_quantity - before_quantity != quantity_delta:
            raise AccountingInvariantError("position delta failed to reconcile")

        records = [
            self._append(
                LedgerRecordType.FILL,
                fill.filled_at,
                order_id=fill.order_id,
                fill_id=fill.fill_id,
                amount=cash_delta,
                quantity=quantity_delta,
                details=(
                    ("notional", str(fill.notional)),
                    ("price", str(fill.price)),
                    ("realized_gross_delta", str(realized_delta)),
                    ("side", fill.side),
                ),
            ),
            self._append(
                LedgerRecordType.FEE,
                fill.filled_at,
                order_id=fill.order_id,
                fill_id=fill.fill_id,
                amount=fill.fee,
                details=(("fee_rate", str(fill.fee_rate)),),
            ),
            self._append(
                lot_record_type,
                fill.filled_at,
                order_id=fill.order_id,
                fill_id=fill.fill_id,
                quantity=fill.quantity,
            ),
            self._append(
                LedgerRecordType.ATTRIBUTION,
                fill.filled_at,
                order_id=fill.order_id,
                fill_id=fill.fill_id,
                amount=fill.spread_cost + fill.slippage_cost + fill.adverse_selection_cost,
                details=(
                    ("adverse_selection_cost", str(fill.adverse_selection_cost)),
                    ("slippage_cost", str(fill.slippage_cost)),
                    ("spread_cost", str(fill.spread_cost)),
                ),
            ),
        ]
        return tuple(records)

    def snapshot(self, *, mark_price: Decimal, as_of: datetime) -> PortfolioSnapshot:
        if mark_price <= 0:
            raise AccountingInvariantError("mark price must be positive")
        position = self.position_quantity
        cost_basis = sum(
            (lot.remaining_quantity * lot.entry_price for lot in self._lots),
            start=Decimal(0),
        )
        market_value = position * mark_price
        unrealized = market_value - cost_basis
        gross = self.realized_gross_pnl + unrealized
        equity = self.cash_balance + market_value
        average = cost_basis / position if position else None
        snapshot = PortfolioSnapshot(
            market=self.market,
            as_of=as_of,
            initial_cash=self.initial_cash,
            cash_balance=self.cash_balance,
            locked_cash=self.locked_cash,
            available_cash=self.available_cash,
            position_quantity=position,
            locked_quantity=self.locked_quantity,
            average_entry_price=average,
            mark_price=mark_price,
            market_value=market_value,
            realized_pnl=self.realized_gross_pnl,
            unrealized_pnl=unrealized,
            gross_pnl=gross,
            fees=self.cumulative_fees,
            spread_cost=self.spread_cost,
            slippage_cost=self.slippage_cost,
            adverse_selection_cost=self.adverse_selection_cost,
            net_pnl=gross - self.cumulative_fees,
            equity=equity,
            ledger_hash=self._records[-1].record_hash if self._records else ZERO_HASH,
        )
        valuation = self._append(
            LedgerRecordType.VALUATION,
            as_of,
            amount=snapshot.equity,
            quantity=position,
            details=(
                ("mark_price", str(mark_price)),
                ("net_pnl", str(snapshot.net_pnl)),
            ),
        )
        return snapshot.model_copy(update={"ledger_hash": valuation.record_hash})

    def verify(self) -> None:
        previous = ZERO_HASH
        for expected_sequence, record in enumerate(self._records, start=1):
            if record.sequence != expected_sequence or record.previous_hash != previous:
                raise AccountingInvariantError("ledger sequence or previous hash is invalid")
            expected_hash = self._calculate_hash(record.model_dump(exclude={"record_hash"}))
            if record.record_hash != expected_hash:
                raise AccountingInvariantError("ledger record hash is invalid")
            previous = record.record_hash
        if self.locked_cash < 0 or self.locked_quantity > self.position_quantity:
            raise AccountingInvariantError("ledger locks are invalid")

    def _apply_bid(
        self, fill: PaperFill, reservation: _Reservation | None
    ) -> tuple[Decimal, Decimal, LedgerRecordType]:
        total_cost = fill.notional + fill.fee
        if total_cost > self.cash_balance:
            raise AccountingInvariantError("paper fill would make cash negative")
        if reservation is not None and total_cost > reservation.cash:
            raise AccountingInvariantError("paper fill exceeds locked cash")
        self.cash_balance -= total_cost
        if reservation is not None:
            reservation.cash -= total_cost
            self.locked_cash -= total_cost
        self._lots.append(
            PositionLot(
                lot_id=deterministic_execution_id("lot", fill.fill_id),
                source_fill_id=fill.fill_id,
                opened_at=fill.filled_at,
                entry_price=fill.price,
                original_quantity=fill.quantity,
                remaining_quantity=fill.quantity,
            )
        )
        return -total_cost, fill.quantity, LedgerRecordType.LOT_OPENED

    def _apply_ask(
        self, fill: PaperFill, reservation: _Reservation | None
    ) -> tuple[Decimal, Decimal, Decimal, LedgerRecordType]:
        if fill.quantity > self.position_quantity:
            raise AccountingInvariantError("paper fill would make position negative")
        if reservation is not None and fill.quantity > reservation.quantity:
            raise AccountingInvariantError("paper fill exceeds locked position")
        cost_basis = self._consume_fifo(fill.quantity)
        realized_delta = fill.notional - cost_basis
        self.realized_gross_pnl += realized_delta
        cash_delta = fill.notional - fill.fee
        self.cash_balance += cash_delta
        if reservation is not None:
            reservation.quantity -= fill.quantity
        return cash_delta, -fill.quantity, realized_delta, LedgerRecordType.LOT_REDUCED

    def _consume_fifo(self, quantity: Decimal) -> Decimal:
        remaining = quantity
        cost_basis = Decimal(0)
        updated: list[PositionLot] = []
        for index, lot in enumerate(self._lots):
            consumed = min(lot.remaining_quantity, remaining)
            cost_basis += consumed * lot.entry_price
            remaining -= consumed
            lot_remaining = lot.remaining_quantity - consumed
            if lot_remaining > 0:
                updated.append(lot.model_copy(update={"remaining_quantity": lot_remaining}))
            if remaining == 0:
                updated.extend(self._lots[index + 1 :])
                break
        if remaining != 0:
            raise AccountingInvariantError("FIFO lots could not satisfy sell fill")
        self._lots = updated
        return cost_basis

    def _append(
        self,
        record_type: LedgerRecordType,
        recorded_at: datetime,
        *,
        order_id: UUID | None = None,
        fill_id: UUID | None = None,
        amount: Decimal = Decimal(0),
        quantity: Decimal = Decimal(0),
        details: tuple[tuple[str, str], ...] = (),
    ) -> LedgerRecord:
        sequence = len(self._records) + 1
        previous_hash = self._records[-1].record_hash if self._records else ZERO_HASH
        record_id = deterministic_execution_id(
            "ledger", self.market, sequence, record_type, order_id, fill_id
        )
        values: dict[str, object] = {
            "sequence": sequence,
            "record_id": record_id,
            "recorded_at": recorded_at,
            "record_type": record_type,
            "market": self.market,
            "order_id": order_id,
            "fill_id": fill_id,
            "amount": amount,
            "quantity": quantity,
            "cash_balance": self.cash_balance,
            "locked_cash": self.locked_cash,
            "position_quantity": self.position_quantity,
            "locked_quantity": self.locked_quantity,
            "realized_gross_pnl": self.realized_gross_pnl,
            "cumulative_fees": self.cumulative_fees,
            "details": tuple(sorted(details)),
            "previous_hash": previous_hash,
        }
        record_hash = self._calculate_hash(values)
        record = LedgerRecord(**values, record_hash=record_hash)
        self._records.append(record)
        return record

    @staticmethod
    def _calculate_hash(values: dict[str, object]) -> str:
        payload = orjson.dumps(
            values,
            default=str,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
        )
        return sha256(payload).hexdigest()

    def _require_market(self, market: str) -> None:
        if market != self.market:
            raise AccountingInvariantError("ledger does not accept another market")

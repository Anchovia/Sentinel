"""Deterministic, latency-aware paper broker driven only by replayed public data."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import (
    DataGap,
    EventEnvelope,
    LiquidityRole,
    OrderIntent,
    OrderStatus,
    PaperExecutionPolicy,
    PaperExecutionUpdate,
    PaperFill,
    PaperFillModel,
    PaperOrder,
    PaperOrderType,
    RiskDecision,
    RiskDecisionType,
    TimeInForce,
    deterministic_execution_id,
)
from quantforge.exchange.upbit.schemas import AskBid, UpbitOrderbook, UpbitTrade

BPS = Decimal(10_000)


class PaperExecutionRejected(ValueError):
    """Raised when an intent cannot safely enter the paper broker."""


class PaperWorkingOrderState(BaseModel):
    """Versioned state required to audit or cancel one recovered paper order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order: PaperOrder
    expires_at: datetime
    queue_ahead: Decimal = Field(ge=0)
    fill_sequence: Annotated[int, Field(ge=0)] = 0

    @field_validator("expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("paper order expiry must be UTC-aware")
        return value


class PaperBrokerState(BaseModel):
    """Secret-free broker checkpoint; stale books are deliberately never restored."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    orders: tuple[PaperWorkingOrderState, ...] = ()
    fills: tuple[PaperFill, ...] = ()

    @model_validator(mode="after")
    def validate_identity_and_arithmetic(self) -> "PaperBrokerState":
        order_ids = tuple(item.order.order_id for item in self.orders)
        fill_ids = tuple(fill.fill_id for fill in self.fills)
        if order_ids != tuple(sorted(order_ids, key=str)) or len(order_ids) != len(set(order_ids)):
            raise ValueError("paper broker orders must have sorted unique identities")
        if fill_ids != tuple(sorted(fill_ids, key=str)) or len(fill_ids) != len(set(fill_ids)):
            raise ValueError("paper broker fills must have sorted unique identities")
        orders = {item.order.order_id: item for item in self.orders}
        for item in self.orders:
            if item.order.policy_hash != self.policy_hash:
                raise ValueError("paper order policy does not match broker state")
            sequences = sorted(
                fill.sequence for fill in self.fills if fill.order_id == item.order.order_id
            )
            if sequences and sequences != list(range(1, max(sequences) + 1)):
                raise ValueError("paper fill sequences must be contiguous")
            if sequences and item.fill_sequence != max(sequences):
                raise ValueError("working order fill sequence does not reconcile")
            if not sequences and item.fill_sequence != 0:
                raise ValueError("working order has an unexplained fill sequence")
            filled = sum(
                (fill.quantity for fill in self.fills if fill.order_id == item.order.order_id),
                start=Decimal(0),
            )
            if item.order.remaining_quantity != item.order.original_quantity - filled:
                raise ValueError("paper order remaining quantity does not reconcile")
        if any(fill.order_id not in orders for fill in self.fills):
            raise ValueError("paper fill has no checkpointed order")
        return self


@dataclass(frozen=True)
class _BookView:
    event_id: UUID
    market: str
    available_at: datetime
    asks: tuple[tuple[Decimal, Decimal], ...]
    bids: tuple[tuple[Decimal, Decimal], ...]

    @property
    def mid(self) -> Decimal:
        return (self.asks[0][0] + self.bids[0][0]) / Decimal(2)

    def same_side_size(self, side: str, price: Decimal) -> Decimal:
        levels = self.bids if side == "bid" else self.asks
        return next((size for level_price, size in levels if level_price == price), Decimal(0))


@dataclass
class _WorkingOrder:
    order: PaperOrder
    expires_at: datetime
    queue_ahead: Decimal = Decimal(0)
    fill_sequence: int = 0


def _order_terms(order_type: str) -> tuple[PaperOrderType, TimeInForce]:
    mapping = {
        "market": (PaperOrderType.MARKET, TimeInForce.IOC),
        "best": (PaperOrderType.BEST, TimeInForce.IOC),
        "limit": (PaperOrderType.LIMIT, TimeInForce.GTC),
        "post_only": (PaperOrderType.LIMIT, TimeInForce.POST_ONLY),
        "ioc": (PaperOrderType.LIMIT, TimeInForce.IOC),
        "fok": (PaperOrderType.LIMIT, TimeInForce.FOK),
    }
    try:
        return mapping[order_type.lower()]
    except KeyError as exc:
        raise PaperExecutionRejected(f"unsupported paper order type: {order_type}") from exc


class PaperBroker:
    """Stateful paper broker with a conservative L2 model as the default."""

    def __init__(self, policy: PaperExecutionPolicy | None = None) -> None:
        self.policy = policy or PaperExecutionPolicy()
        self._books: dict[str, _BookView] = {}
        self._orders: dict[UUID, _WorkingOrder] = {}
        self._fills: list[PaperFill] = []
        self._unsafe_markets: set[str] = set()

    @property
    def orders(self) -> tuple[PaperOrder, ...]:
        return tuple(item.order for item in self._ordered_working_orders())

    @property
    def fills(self) -> tuple[PaperFill, ...]:
        return tuple(self._fills)

    def export_state(self) -> PaperBrokerState:
        """Return exact economic/order state without carrying a potentially stale public book."""

        return PaperBrokerState(
            policy_hash=self.policy.digest,
            orders=tuple(
                PaperWorkingOrderState(
                    order=working.order,
                    expires_at=working.expires_at,
                    queue_ahead=working.queue_ahead,
                    fill_sequence=working.fill_sequence,
                )
                for working in self._ordered_working_orders()
            ),
            fills=tuple(sorted(self._fills, key=lambda fill: str(fill.fill_id))),
        )

    @classmethod
    def from_state(
        cls,
        state: PaperBrokerState,
        *,
        policy: PaperExecutionPolicy,
        markets: tuple[str, ...],
    ) -> "PaperBroker":
        """Restore verified paper state while requiring a fresh book before any new execution."""

        if state.policy_hash != policy.digest:
            raise PaperExecutionRejected("paper broker checkpoint policy mismatch")
        market_set = set(markets)
        if any(item.order.market not in market_set for item in state.orders):
            raise PaperExecutionRejected("paper broker checkpoint market mismatch")
        broker = cls(policy)
        broker._orders = {
            item.order.order_id: _WorkingOrder(
                order=item.order,
                expires_at=item.expires_at,
                queue_ahead=item.queue_ahead,
                fill_sequence=item.fill_sequence,
            )
            for item in state.orders
        }
        broker._fills = list(state.fills)
        broker._unsafe_markets = market_set
        return broker

    def submit(
        self,
        intent: OrderIntent,
        decision: RiskDecision,
        *,
        submitted_at: datetime,
    ) -> PaperExecutionUpdate:
        self._validate_submission(intent, decision, submitted_at)
        book = self._fresh_book(intent.market, submitted_at)
        order_type, tif = _order_terms(intent.order_type)
        if order_type is PaperOrderType.LIMIT and intent.limit_price is None:
            raise PaperExecutionRejected("limit, post_only, IOC, and FOK require a limit price")
        if order_type is not PaperOrderType.LIMIT and intent.limit_price is not None:
            raise PaperExecutionRejected("market and best paper orders cannot carry a limit price")

        approved_quantity = decision.approved_quantity
        if approved_quantity is None:
            if decision.approved_notional is None:  # protected by RiskDecision validation
                raise PaperExecutionRejected("approved paper order has no amount")
            reference_price = book.asks[0][0] if intent.side == "bid" else book.bids[0][0]
            approved_quantity = decision.approved_notional / reference_price
        order_id = deterministic_execution_id(
            "order", intent.intent_id, decision.decision_id, self.policy.digest
        )
        if order_id in self._orders:
            raise PaperExecutionRejected("duplicate paper order identity")
        order = PaperOrder(
            order_id=order_id,
            intent_id=intent.intent_id,
            decision_id=decision.decision_id,
            market=intent.market,
            side=intent.side,
            order_type=order_type,
            time_in_force=tif,
            limit_price=intent.limit_price if order_type is PaperOrderType.LIMIT else None,
            original_quantity=approved_quantity,
            remaining_quantity=approved_quantity,
            reference_mid=book.mid,
            submitted_at=submitted_at,
            arrival_at=self.policy.arrival_time(submitted_at),
            status=OrderStatus.SUBMITTED,
            policy_hash=self.policy.digest,
        )
        self._orders[order_id] = _WorkingOrder(order=order, expires_at=intent.expires_at)
        return PaperExecutionUpdate(
            order=order,
            occurred_at=submitted_at,
            reason="paper order scheduled for latency-adjusted arrival",
        )

    def request_cancel(self, order_id: UUID, *, requested_at: datetime) -> PaperExecutionUpdate:
        working = self._orders.get(order_id)
        if working is None:
            raise PaperExecutionRejected("unknown paper order")
        if working.order.status not in {
            OrderStatus.ACKNOWLEDGED,
            OrderStatus.PARTIALLY_FILLED,
        }:
            raise PaperExecutionRejected("only resting paper orders can be canceled")
        updated = working.order.model_copy(
            update={
                "status": OrderStatus.CANCEL_PENDING,
                "cancel_requested_at": requested_at,
                "cancel_effective_at": self.policy.cancel_effective_time(requested_at),
            }
        )
        working.order = updated
        return PaperExecutionUpdate(
            order=updated,
            occurred_at=requested_at,
            reason="paper cancel entered latency window",
        )

    def reservation_cash(self, order: PaperOrder) -> Decimal:
        """Estimate a fail-closed cash lock for a bid before its paper arrival."""

        if order.side != "bid":
            return Decimal(0)
        if order.limit_price is not None:
            reserve_price = order.limit_price
        else:
            reserve_price = order.reference_mid * (
                Decimal(1) + self.policy.market_reserve_buffer_bps / BPS
            )
        return order.original_quantity * reserve_price * (Decimal(1) + self.policy.taker_fee_rate)

    def reject_preflight(
        self, order_id: UUID, *, rejected_at: datetime, reason: str
    ) -> PaperExecutionUpdate:
        working = self._orders.get(order_id)
        if working is None or working.order.status is not OrderStatus.SUBMITTED:
            raise PaperExecutionRejected("only a submitted paper order can fail preflight")
        working.order = working.order.model_copy(
            update={"status": OrderStatus.REJECTED, "reject_reason": reason}
        )
        return PaperExecutionUpdate(
            order=working.order,
            occurred_at=rejected_at,
            reason=f"paper accounting preflight rejected: {reason}",
        )

    def close(self, *, closed_at: datetime) -> tuple[PaperExecutionUpdate, ...]:
        """Deterministically cancel all non-terminal orders at the replay boundary."""

        return self.cancel_all(
            canceled_at=closed_at,
            reason="paper order canceled at replay boundary",
        )

    def cancel_all(self, *, canceled_at: datetime, reason: str) -> tuple[PaperExecutionUpdate, ...]:
        """Cancel every non-terminal paper order for shutdown or fail-closed recovery."""

        updates: list[PaperExecutionUpdate] = []
        for working in self._ordered_working_orders():
            if working.order.status not in {
                OrderStatus.SUBMITTED,
                OrderStatus.ACKNOWLEDGED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.CANCEL_PENDING,
            }:
                continue
            working.order = working.order.model_copy(update={"status": OrderStatus.CANCELED})
            updates.append(
                PaperExecutionUpdate(
                    order=working.order,
                    occurred_at=canceled_at,
                    reason=reason,
                )
            )
        return tuple(updates)

    def on_item(
        self, item: EventEnvelope | DataGap, *, now: datetime
    ) -> tuple[PaperExecutionUpdate, ...]:
        if isinstance(item, DataGap):
            return self._on_gap(item, now)
        if item.received_at_utc > now:
            raise PaperExecutionRejected("future market data cannot be consumed")

        old_book = self._books.get(item.market)
        new_book: _BookView | None = None
        if item.event_type == "orderbook":
            new_book = self._book_from_event(item)
            self._books[item.market] = new_book
            self._unsafe_markets.discard(item.market)

        updates: list[PaperExecutionUpdate] = []
        # Resting orders see the public event before newly arriving orders join the queue.
        for working in self._ordered_working_orders():
            if working.order.market != item.market or not self._is_resting(working.order.status):
                continue
            update = self._apply_passive_evidence(working, item, old_book, new_book, now)
            if update is not None:
                updates.append(update)

        for working in self._ordered_working_orders():
            if working.order.market != item.market:
                continue
            if working.order.status is OrderStatus.SUBMITTED and working.order.arrival_at <= now:
                updates.append(self._arrive(working, item, now))

        updates.extend(self.advance_time(now))
        return tuple(updates)

    def advance_time(self, now: datetime) -> tuple[PaperExecutionUpdate, ...]:
        updates: list[PaperExecutionUpdate] = []
        for working in self._ordered_working_orders():
            order = working.order
            if (
                order.status
                in {
                    OrderStatus.SUBMITTED,
                    OrderStatus.ACKNOWLEDGED,
                    OrderStatus.PARTIALLY_FILLED,
                    OrderStatus.CANCEL_PENDING,
                }
                and now >= working.expires_at
            ):
                status = (
                    OrderStatus.CANCELED
                    if order.remaining_quantity < order.original_quantity
                    else OrderStatus.EXPIRED
                )
                working.order = order.model_copy(update={"status": status})
                updates.append(
                    PaperExecutionUpdate(
                        order=working.order,
                        occurred_at=now,
                        reason="paper order expired before complete fill",
                    )
                )
                continue
            if (
                order.status is OrderStatus.CANCEL_PENDING
                and order.cancel_effective_at is not None
                and now >= order.cancel_effective_at
            ):
                working.order = order.model_copy(update={"status": OrderStatus.CANCELED})
                updates.append(
                    PaperExecutionUpdate(
                        order=working.order,
                        occurred_at=now,
                        reason="paper cancel became effective",
                    )
                )
        return tuple(updates)

    def _validate_submission(
        self, intent: OrderIntent, decision: RiskDecision, submitted_at: datetime
    ) -> None:
        if submitted_at.tzinfo is None:
            raise PaperExecutionRejected("submission timestamp must be timezone-aware")
        if decision.intent_id != intent.intent_id:
            raise PaperExecutionRejected("risk decision does not belong to intent")
        if decision.decision not in {RiskDecisionType.ALLOW, RiskDecisionType.RESIZE}:
            raise PaperExecutionRejected("risk did not approve the intent")
        if intent.signal_timestamp > submitted_at or decision.decided_at > submitted_at:
            raise PaperExecutionRejected("future intent or risk decision would violate causality")
        if intent.expires_at <= submitted_at:
            raise PaperExecutionRejected("intent expired before paper submission")

    def _fresh_book(self, market: str, now: datetime) -> _BookView:
        if market in self._unsafe_markets:
            raise PaperExecutionRejected("market is unsafe after an unresolved data gap")
        book = self._books.get(market)
        if book is None:
            raise PaperExecutionRejected("paper execution requires a prior orderbook")
        age_ms = Decimal(str((now - book.available_at).total_seconds())) * Decimal(1000)
        if age_ms < 0:
            raise PaperExecutionRejected("future orderbook would violate causality")
        if age_ms > self.policy.max_book_age_ms:
            raise PaperExecutionRejected("paper execution refuses a stale orderbook")
        return book

    @staticmethod
    def _book_from_event(event: EventEnvelope) -> _BookView:
        message = UpbitOrderbook.model_validate(event.raw_payload)
        asks = tuple(sorted((unit.ask_price, unit.ask_size) for unit in message.orderbook_units))
        bids = tuple(
            sorted(
                ((unit.bid_price, unit.bid_size) for unit in message.orderbook_units),
                reverse=True,
            )
        )
        return _BookView(event.event_id, event.market, event.received_at_utc, asks, bids)

    def _arrive(
        self, working: _WorkingOrder, source: EventEnvelope, now: datetime
    ) -> PaperExecutionUpdate:
        order = working.order
        try:
            book = self._fresh_book(order.market, now)
        except PaperExecutionRejected as exc:
            working.order = order.model_copy(
                update={"status": OrderStatus.REJECTED, "reject_reason": str(exc)}
            )
            return PaperExecutionUpdate(order=working.order, occurred_at=now, reason=str(exc))

        if self._would_cross(order, book) and order.time_in_force is TimeInForce.POST_ONLY:
            working.order = order.model_copy(
                update={
                    "status": OrderStatus.REJECTED,
                    "reject_reason": "post_only would take liquidity",
                }
            )
            return PaperExecutionUpdate(
                order=working.order,
                occurred_at=now,
                reason="post_only rejected because it would cross",
            )

        fills = self._immediate_fills(working, book, source, now)
        filled_quantity = sum((fill.quantity for fill in fills), start=Decimal(0))
        if order.time_in_force is TimeInForce.FOK and filled_quantity < order.remaining_quantity:
            fills = ()
            filled_quantity = Decimal(0)

        remaining = order.remaining_quantity - filled_quantity
        if remaining == 0:
            status = OrderStatus.FILLED
            reason = "paper order fully filled"
        elif order.time_in_force in {TimeInForce.IOC, TimeInForce.FOK}:
            status = OrderStatus.CANCELED
            reason = "unfilled paper quantity canceled by time-in-force"
        elif filled_quantity > 0:
            status = OrderStatus.PARTIALLY_FILLED
            reason = "paper order partially filled and remainder joined queue"
        else:
            status = OrderStatus.ACKNOWLEDGED
            reason = "paper order joined conservative queue"

        working.order = order.model_copy(update={"status": status, "remaining_quantity": remaining})
        if status in {OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED}:
            limit = cast(Decimal, working.order.limit_price)
            working.queue_ahead = book.same_side_size(order.side, limit) * self.policy.queue_factor
        self._fills.extend(fills)
        return PaperExecutionUpdate(
            order=working.order,
            fills=fills,
            occurred_at=now,
            reason=reason,
        )

    def _immediate_fills(
        self,
        working: _WorkingOrder,
        book: _BookView,
        source: EventEnvelope,
        now: datetime,
    ) -> tuple[PaperFill, ...]:
        order = working.order
        if self.policy.model is PaperFillModel.NAIVE:
            if order.order_type is PaperOrderType.LIMIT and not self._would_cross(order, book):
                return ()
            working.fill_sequence += 1
            return (
                self._make_fill(
                    working,
                    quantity=order.remaining_quantity,
                    price=book.mid,
                    raw_book_price=book.mid,
                    source_event_id=source.event_id,
                    filled_at=now,
                    liquidity_role=LiquidityRole.TAKER,
                    spread_cost=Decimal(0),
                    slippage_cost=Decimal(0),
                    adverse_selection_cost=Decimal(0),
                ),
            )

        levels = book.asks if order.side == "bid" else book.bids
        if order.order_type is PaperOrderType.BEST:
            levels = levels[:1]
        remaining = order.remaining_quantity
        candidates: list[tuple[Decimal, Decimal, Decimal, Decimal, Decimal]] = []
        for raw_price, raw_size in levels:
            adjusted, slippage, adverse = self._adjusted_taker_price(order.side, raw_price)
            if not self._price_is_eligible(order, adjusted):
                continue
            available = raw_size * self.policy.depth_haircut
            quantity = min(remaining, available)
            if quantity <= 0:
                continue
            spread = quantity * abs(raw_price - book.mid)
            candidates.append((quantity, adjusted, spread, quantity * slippage, quantity * adverse))
            remaining -= quantity
            if remaining == 0:
                break
        if order.time_in_force is TimeInForce.FOK and remaining > 0:
            return ()

        fills: list[PaperFill] = []
        for quantity, price, spread, slippage, adverse in candidates:
            working.fill_sequence += 1
            fills.append(
                self._make_fill(
                    working,
                    quantity=quantity,
                    price=price,
                    raw_book_price=price,
                    source_event_id=source.event_id,
                    filled_at=now,
                    liquidity_role=LiquidityRole.TAKER,
                    spread_cost=spread,
                    slippage_cost=slippage,
                    adverse_selection_cost=adverse,
                )
            )
        return tuple(fills)

    def _adjusted_taker_price(
        self, side: str, raw_price: Decimal
    ) -> tuple[Decimal, Decimal, Decimal]:
        slippage = raw_price * self.policy.slippage_buffer_bps / BPS
        adverse = raw_price * self.policy.adverse_selection_bps / BPS
        direction = Decimal(1) if side == "bid" else Decimal(-1)
        return raw_price + direction * (slippage + adverse), slippage, adverse

    @staticmethod
    def _would_cross(order: PaperOrder, book: _BookView) -> bool:
        if order.order_type is not PaperOrderType.LIMIT:
            return True
        if order.side == "bid":
            return cast(Decimal, order.limit_price) >= book.asks[0][0]
        return cast(Decimal, order.limit_price) <= book.bids[0][0]

    @staticmethod
    def _price_is_eligible(order: PaperOrder, price: Decimal) -> bool:
        if order.order_type is not PaperOrderType.LIMIT:
            return True
        limit = cast(Decimal, order.limit_price)
        return price <= limit if order.side == "bid" else price >= limit

    def _apply_passive_evidence(
        self,
        working: _WorkingOrder,
        event: EventEnvelope,
        old_book: _BookView | None,
        new_book: _BookView | None,
        now: datetime,
    ) -> PaperExecutionUpdate | None:
        order = working.order
        limit = cast(Decimal, order.limit_price)
        executable = Decimal(0)
        reason = ""
        if event.event_type == "trade":
            trade = UpbitTrade.model_validate(event.raw_payload)
            correct_aggressor = (order.side == "bid" and trade.ask_bid is AskBid.ASK) or (
                order.side == "ask" and trade.ask_bid is AskBid.BID
            )
            if correct_aggressor and trade.trade_price == limit:
                executable = trade.trade_volume
                reason = "aggressive public trade consumed conservative queue"
        elif old_book is not None and new_book is not None:
            old_size = old_book.same_side_size(order.side, limit)
            new_size = new_book.same_side_size(order.side, limit)
            if new_size < old_size:
                executable = (old_size - new_size) * self.policy.snapshot_decrease_fill_fraction
                reason = "ambiguous L2 depth decrease partially consumed queue"
        if executable <= 0:
            return None

        queue_consumed = min(working.queue_ahead, executable)
        working.queue_ahead -= queue_consumed
        fillable = min(order.remaining_quantity, executable - queue_consumed)
        if fillable <= 0:
            return PaperExecutionUpdate(order=order, occurred_at=now, reason=reason)

        working.fill_sequence += 1
        adverse = limit * self.policy.adverse_selection_bps / BPS * fillable
        fill = self._make_fill(
            working,
            quantity=fillable,
            price=limit,
            raw_book_price=limit,
            source_event_id=event.event_id,
            filled_at=now,
            liquidity_role=LiquidityRole.MAKER,
            spread_cost=Decimal(0),
            slippage_cost=Decimal(0),
            adverse_selection_cost=adverse,
        )
        remaining = order.remaining_quantity - fillable
        if remaining == 0:
            status = OrderStatus.FILLED
        elif order.status is OrderStatus.CANCEL_PENDING:
            status = OrderStatus.CANCEL_PENDING
        else:
            status = OrderStatus.PARTIALLY_FILLED
        working.order = order.model_copy(update={"remaining_quantity": remaining, "status": status})
        self._fills.append(fill)
        return PaperExecutionUpdate(
            order=working.order, fills=(fill,), occurred_at=now, reason=reason
        )

    def _make_fill(
        self,
        working: _WorkingOrder,
        *,
        quantity: Decimal,
        price: Decimal,
        raw_book_price: Decimal,
        source_event_id: UUID,
        filled_at: datetime,
        liquidity_role: LiquidityRole,
        spread_cost: Decimal,
        slippage_cost: Decimal,
        adverse_selection_cost: Decimal,
    ) -> PaperFill:
        del raw_book_price  # retained in the call boundary to make cost attribution explicit
        order = working.order
        fee_rate = (
            self.policy.maker_fee_rate
            if liquidity_role is LiquidityRole.MAKER
            else self.policy.taker_fee_rate
        )
        notional = quantity * price
        return PaperFill(
            fill_id=deterministic_execution_id(
                "fill", order.order_id, working.fill_sequence, source_event_id
            ),
            order_id=order.order_id,
            sequence=working.fill_sequence,
            market=order.market,
            side=order.side,
            quantity=quantity,
            price=price,
            notional=notional,
            fee=notional * fee_rate,
            fee_rate=fee_rate,
            liquidity_role=liquidity_role,
            filled_at=filled_at,
            source_event_id=source_event_id,
            reference_mid=order.reference_mid,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            adverse_selection_cost=adverse_selection_cost,
            model=self.policy.model,
        )

    def _on_gap(self, gap: DataGap, now: datetime) -> tuple[PaperExecutionUpdate, ...]:
        self._unsafe_markets.add(gap.market)
        self._books.pop(gap.market, None)
        updates: list[PaperExecutionUpdate] = []
        for working in self._ordered_working_orders():
            order = working.order
            if order.market != gap.market or order.status not in {
                OrderStatus.SUBMITTED,
                OrderStatus.ACKNOWLEDGED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.CANCEL_PENDING,
            }:
                continue
            working.order = order.model_copy(update={"status": OrderStatus.CANCELED})
            updates.append(
                PaperExecutionUpdate(
                    order=working.order,
                    occurred_at=now,
                    reason="data gap canceled paper order and invalidated book",
                )
            )
        return tuple(updates)

    def _ordered_working_orders(self) -> list[_WorkingOrder]:
        return sorted(self._orders.values(), key=lambda item: str(item.order.order_id))

    @staticmethod
    def _is_resting(status: OrderStatus) -> bool:
        return status in {
            OrderStatus.ACKNOWLEDGED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCEL_PENDING,
        }

"""Causal backtest orchestration over the deterministic replay engine."""

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import (
    EventEnvelope,
    OrderIntent,
    OrderStatus,
    PaperExecutionPolicy,
    PaperExecutionUpdate,
    PaperFill,
    PaperFillModel,
    PaperOrder,
    RiskDecision,
    RiskDecisionType,
)
from quantforge.domain.money import MonetaryDecimal
from quantforge.exchange.upbit.schemas import UpbitOrderbook, UpbitTicker, UpbitTrade
from quantforge.execution import PaperBroker, PaperExecutionRejected
from quantforge.portfolio import (
    AccountingInvariantError,
    LedgerRecord,
    PortfolioLedger,
    PortfolioSnapshot,
)
from quantforge.replay import ReplayConfig, ReplayEngine, ReplayResult, VirtualClock
from quantforge.replay.engine import ReplayItem

TERMINAL_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
        OrderStatus.PREVENTED,
    }
)


class Strategy(Protocol):
    def on_item(
        self, item: ReplayItem, *, now: datetime, random_seed: int
    ) -> Sequence[OrderIntent]: ...


class RiskEvaluator(Protocol):
    def evaluate(
        self,
        intent: OrderIntent,
        *,
        available_cash: Decimal,
        position_quantity: Decimal,
        now: datetime,
        random_seed: int,
    ) -> RiskDecision: ...


class BacktestConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    initial_cash: MonetaryDecimal = Field(gt=0)
    code_version: str = Field(min_length=1, max_length=128)
    random_seed: int = 0
    replay: ReplayConfig = Field(default_factory=ReplayConfig)
    execution: PaperExecutionPolicy = Field(default_factory=PaperExecutionPolicy)

    @property
    def digest(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()


class BacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    run_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    market: str
    code_version: str
    random_seed: int
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    replay_config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    backtest_config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    replay_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    fill_model: PaperFillModel
    started_at_utc: datetime
    ended_at_utc: datetime
    intent_count: int = Field(ge=0)
    risk_rejection_count: int = Field(ge=0)
    submission_rejection_count: int = Field(ge=0)
    order_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    filled_quantity: MonetaryDecimal = Field(ge=0)
    ledger_record_count: int = Field(ge=0)
    orders: tuple[PaperOrder, ...]
    fills: tuple[PaperFill, ...]
    portfolio: PortfolioSnapshot

    @field_validator("started_at_utc", "ended_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("backtest timestamps must be UTC-aware")
        return value


class BacktestComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    naive: BacktestResult
    conservative: BacktestResult
    naive_minus_conservative_net_pnl: MonetaryDecimal
    naive_minus_conservative_filled_quantity: MonetaryDecimal
    optimism_detected: bool
    explanation: str

    @model_validator(mode="after")
    def require_same_experiment(self) -> "BacktestComparison":
        comparable = (
            self.naive.dataset_hash == self.conservative.dataset_hash
            and self.naive.replay_config_hash == self.conservative.replay_config_hash
            and self.naive.code_version == self.conservative.code_version
            and self.naive.random_seed == self.conservative.random_seed
            and self.naive.market == self.conservative.market
        )
        if not comparable:
            raise ValueError("backtests do not share comparable provenance")
        if self.naive.fill_model is not PaperFillModel.NAIVE:
            raise ValueError("naive result does not use the naive fill model")
        if self.conservative.fill_model is PaperFillModel.NAIVE:
            raise ValueError("conservative result cannot use the naive fill model")
        return self


class BacktestEngine:
    def __init__(self, config: BacktestConfig) -> None:
        self.config = config

    def run(
        self,
        items: Sequence[ReplayItem],
        *,
        strategy: Strategy,
        risk: RiskEvaluator,
    ) -> BacktestResult:
        broker = PaperBroker(self.config.execution)
        ledger = PortfolioLedger(market=self.config.market, initial_cash=self.config.initial_cash)
        intent_count = 0
        risk_rejections = 0
        submission_rejections = 0
        last_mark: Decimal | None = None

        def handle(item: ReplayItem, clock: VirtualClock) -> bytes:
            nonlocal intent_count, risk_rejections, submission_rejections, last_mark
            now = clock.now
            if isinstance(item, EventEnvelope) and item.market == self.config.market:
                last_mark = _mark_price(item)
            updates = broker.on_item(item, now=now)
            self._apply_updates(ledger, updates)
            emitted: list[dict[str, object]] = [
                {"execution": update.model_dump(mode="json")} for update in updates
            ]

            intents = tuple(strategy.on_item(item, now=now, random_seed=self.config.random_seed))
            for intent in intents:
                intent_count += 1
                if intent.market != self.config.market:
                    raise ValueError("strategy emitted an intent for another market")
                if intent.signal_timestamp > now:
                    raise ValueError("strategy emitted a future-dated intent")
                ledger.record_intent(intent)
                decision = risk.evaluate(
                    intent,
                    available_cash=ledger.available_cash,
                    position_quantity=ledger.position_quantity - ledger.locked_quantity,
                    now=now,
                    random_seed=self.config.random_seed,
                )
                ledger.record_risk_decision(decision)
                emitted.append(
                    {
                        "intent": intent.model_dump(mode="json"),
                        "risk": decision.model_dump(mode="json"),
                    }
                )
                if decision.decision not in {
                    RiskDecisionType.ALLOW,
                    RiskDecisionType.RESIZE,
                }:
                    risk_rejections += 1
                    continue
                try:
                    submitted = broker.submit(intent, decision, submitted_at=now)
                except PaperExecutionRejected as exc:
                    submission_rejections += 1
                    emitted.append({"submission_rejected": str(exc)})
                    continue
                ledger.record_order_update(submitted)
                try:
                    ledger.reserve_order(
                        submitted.order,
                        at=now,
                        cash_amount=broker.reservation_cash(submitted.order),
                    )
                except AccountingInvariantError as exc:
                    submission_rejections += 1
                    rejected = broker.reject_preflight(
                        submitted.order.order_id,
                        rejected_at=now,
                        reason=str(exc),
                    )
                    ledger.record_order_update(rejected)
                    emitted.append({"execution": rejected.model_dump(mode="json")})
                    continue
                emitted.append({"execution": submitted.model_dump(mode="json")})
            return orjson.dumps(emitted, option=orjson.OPT_SORT_KEYS)

        replay_result = ReplayEngine(self.config.replay).run(items, handle)
        boundary_updates = broker.close(closed_at=replay_result.ended_at_utc)
        self._apply_updates(ledger, boundary_updates)
        if last_mark is None:
            raise ValueError("backtest requires at least one price-bearing market event")
        portfolio = ledger.snapshot(mark_price=last_mark, as_of=replay_result.ended_at_utc)
        ledger.verify()
        return self._result(
            replay_result,
            broker.orders,
            broker.fills,
            portfolio,
            ledger.records,
            intent_count,
            risk_rejections,
            submission_rejections,
        )

    @staticmethod
    def _apply_updates(ledger: PortfolioLedger, updates: Sequence[PaperExecutionUpdate]) -> None:
        for update in updates:
            ledger.record_order_update(update)
            for fill in update.fills:
                ledger.apply_fill(fill)
            if update.order.status in TERMINAL_STATUSES:
                ledger.release_order(update.order.order_id, at=update.occurred_at)

    def _result(
        self,
        replay: ReplayResult,
        orders: tuple[PaperOrder, ...],
        fills: tuple[PaperFill, ...],
        portfolio: PortfolioSnapshot,
        records: tuple[LedgerRecord, ...],
        intent_count: int,
        risk_rejections: int,
        submission_rejections: int,
    ) -> BacktestResult:
        run_identity = "|".join(
            (
                replay.dataset_hash,
                self.config.digest,
                self.config.code_version,
                str(self.config.random_seed),
            )
        )
        run_id = sha256(run_identity.encode()).hexdigest()
        result_values: dict[str, object] = {
            "schema_version": 1,
            "run_id": run_id,
            "market": self.config.market,
            "code_version": self.config.code_version,
            "random_seed": self.config.random_seed,
            "dataset_hash": replay.dataset_hash,
            "replay_config_hash": replay.config_hash,
            "execution_policy_hash": self.config.execution.digest,
            "backtest_config_hash": self.config.digest,
            "replay_output_hash": replay.output_hash,
            "fill_model": self.config.execution.model,
            "started_at_utc": replay.started_at_utc,
            "ended_at_utc": replay.ended_at_utc,
            "intent_count": intent_count,
            "risk_rejection_count": risk_rejections,
            "submission_rejection_count": submission_rejections,
            "order_count": len(orders),
            "fill_count": len(fills),
            "filled_quantity": sum((fill.quantity for fill in fills), start=Decimal(0)),
            "ledger_record_count": len(records),
            "orders": orders,
            "fills": fills,
            "portfolio": portfolio,
        }
        output_hash = sha256(
            orjson.dumps(result_values, default=str, option=orjson.OPT_SORT_KEYS)
        ).hexdigest()
        return BacktestResult(**result_values, output_hash=output_hash)


def _mark_price(event: EventEnvelope) -> Decimal:
    if event.event_type == "orderbook":
        book = UpbitOrderbook.model_validate(event.raw_payload)
        best_ask = min(unit.ask_price for unit in book.orderbook_units)
        best_bid = max(unit.bid_price for unit in book.orderbook_units)
        return (best_ask + best_bid) / Decimal(2)
    if event.event_type == "trade":
        return UpbitTrade.model_validate(event.raw_payload).trade_price
    if event.event_type == "ticker":
        return UpbitTicker.model_validate(event.raw_payload).trade_price


def compare_backtests(naive: BacktestResult, conservative: BacktestResult) -> BacktestComparison:
    pnl_delta = naive.portfolio.net_pnl - conservative.portfolio.net_pnl
    quantity_delta = naive.filled_quantity - conservative.filled_quantity
    return BacktestComparison(
        naive=naive,
        conservative=conservative,
        naive_minus_conservative_net_pnl=pnl_delta,
        naive_minus_conservative_filled_quantity=quantity_delta,
        optimism_detected=pnl_delta > 0 or quantity_delta > 0,
        explanation=(
            "Naive execution assumes full midpoint fills. Conservative L2 applies latency, "
            "visible-depth haircuts, spread, slippage, adverse selection, partial/non-fill, "
            "queue uncertainty, cancellation timing, and non-zero fees. Positive deltas show "
            "the amount of fill or PnL optimism removed by those assumptions."
        ),
    )


def write_backtest_report(report: BacktestResult | BacktestComparison, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    payload = (
        orjson.dumps(
            report.model_dump(mode="json"),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination

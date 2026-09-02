"""Preregistered, cost-inclusive short-horizon paper research."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import (
    DataGap,
    EventEnvelope,
    OrderIntent,
    OrderStatus,
    PaperExecutionPolicy,
    PaperExecutionUpdate,
    RiskDecision,
    RiskDecisionType,
    deterministic_execution_id,
)
from quantforge.domain.money import MonetaryDecimal
from quantforge.exchange.upbit.schemas import UpbitOrderbook, UpbitTicker, UpbitTrade
from quantforge.execution import PaperBroker, PaperExecutionRejected
from quantforge.portfolio import AccountingInvariantError, PortfolioLedger, PortfolioSnapshot
from quantforge.replay import ReplayEngine, VirtualClock
from quantforge.research.experiments import (
    ExperimentDecision,
    ExperimentLedger,
    ExperimentLedgerSnapshot,
    ExperimentRegistration,
    ExperimentSummary,
    new_experiment_id,
)
from quantforge.research.splits import SplitRole
from quantforge.runtime.realtime_pipeline import RealtimeFeatureFrame, RealtimePaperPipeline
from quantforge.storage import RawEventResearchInventory

BPS = Decimal(10_000)
TERMINAL_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
        OrderStatus.PREVENTED,
    }
)


class ScalpingResearchError(ValueError):
    """Raised when a plan or trial would violate its preregistered boundary."""


class ScalpingTrialLimitError(RuntimeError):
    """Raised when one preregistered trial exceeds an operational work bound."""


class ScalpingRule(StrEnum):
    ALWAYS_NEUTRAL = "always_neutral"
    TRADE_CONTINUATION = "trade_continuation"
    SNAPSHOT_BOOK_PRESSURE = "snapshot_book_pressure"
    CONFIRMED_CONTINUATION = "confirmed_continuation"
    SELL_SHOCK_EXHAUSTION = "sell_shock_exhaustion"
    BID_REPLENISHMENT_REVERSAL = "bid_replenishment_reversal"
    CONFIRMED_REVERSAL = "confirmed_reversal"


class ScalpingExitReason(StrEnum):
    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    TIME_STOP = "time_stop"
    SPLIT_BOUNDARY = "split_boundary"


class ScalpingResearchDecision(StrEnum):
    BLOCKED = "BLOCKED"
    REJECT = "REJECT"
    MORE_DATA = "MORE_DATA"
    CONTINUE_RESEARCH = "CONTINUE_RESEARCH"
    PAPER_CANDIDATE = "PAPER_CANDIDATE"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DatasetSelectionPlan(_FrozenModel):
    source: str = Field(min_length=1)
    storage_label: str = Field(min_length=1)
    manifest_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    maximum_exchange_timestamp_utc: datetime
    minimum_received_at_utc: datetime | None = None
    maximum_received_at_utc: datetime | None = None
    fixed_markets: tuple[str, ...] | None = None
    exclude_marked_duplicates: bool = False
    exclude_quality_flagged_events: bool = False
    availability_order: str = Field(min_length=1)
    market_scope: str = Field(min_length=1)
    final_holdout_fraction: Decimal = Field(gt=0, lt=1)
    final_holdout_access: Literal[False]

    @field_validator(
        "maximum_exchange_timestamp_utc",
        "minimum_received_at_utc",
        "maximum_received_at_utc",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError("dataset cutoff must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_fixed_selection(self) -> "DatasetSelectionPlan":
        if (
            self.minimum_received_at_utc is not None
            and self.maximum_received_at_utc is not None
            and self.minimum_received_at_utc >= self.maximum_received_at_utc
        ):
            raise ValueError("dataset receive interval is empty or reversed")
        if self.fixed_markets is not None:
            if self.fixed_markets != tuple(sorted(set(self.fixed_markets))):
                raise ValueError("fixed research markets must be sorted and unique")
            if any(not market.startswith("KRW-") for market in self.fixed_markets):
                raise ValueError("fixed research markets must remain in the KRW universe")
        return self


class AvailabilityLeakagePlan(_FrozenModel):
    features_use_only_received_events_at_or_before_signal: Literal[True]
    entry_occurs_after_configured_order_latency: Literal[True]
    historic_universe_reconstruction_from_future_catalog: Literal[False]
    feature_warmup_seconds: Annotated[int, Field(ge=15)]
    purge_seconds: Annotated[int, Field(ge=0)]
    embargo_seconds: Annotated[int, Field(ge=0)]


class TradeContinuationPlan(_FrozenModel):
    minimum_trade_return_5s_bps: Decimal
    minimum_trade_imbalance_1s: Decimal = Field(ge=-1, le=1)
    minimum_trade_count_5s: Annotated[int, Field(gt=0)]


class BookPressurePlan(_FrozenModel):
    minimum_top_book_imbalance: Decimal = Field(ge=-1, le=1)
    minimum_total_book_imbalance: Decimal = Field(ge=-1, le=1)
    minimum_snapshot_derived_ofi: Decimal


class FeatureEntryPlan(_FrozenModel):
    feature_contract: Literal["realtime-feature-frame-1"]
    trade_continuation: TradeContinuationPlan
    snapshot_book_pressure: BookPressurePlan
    confirmed_continuation: str = Field(min_length=1)
    maximum_spread_bps: Decimal = Field(gt=0)
    order_notional_krw: MonetaryDecimal = Field(gt=0)
    long_only: Literal[True]


class SellShockExhaustionPlan(_FrozenModel):
    maximum_trade_return_5s_bps: Decimal = Field(lt=0)
    maximum_trade_imbalance_5s: Decimal = Field(ge=-1, lt=0)
    minimum_recovery_return_1s_bps: Decimal = Field(ge=0)
    minimum_recovery_trade_imbalance_1s: Decimal = Field(ge=-1, le=1)
    minimum_trade_count_5s: Annotated[int, Field(gt=0)]


class BidReplenishmentReversalPlan(_FrozenModel):
    maximum_trade_return_5s_bps: Decimal = Field(lt=0)
    minimum_top_book_imbalance: Decimal = Field(ge=-1, le=1)
    minimum_total_book_imbalance: Decimal = Field(ge=-1, le=1)
    minimum_snapshot_derived_ofi: Decimal


class ReversalFeatureEntryPlan(_FrozenModel):
    feature_contract: Literal["realtime-feature-frame-1"]
    sell_shock_exhaustion: SellShockExhaustionPlan
    bid_replenishment_reversal: BidReplenishmentReversalPlan
    confirmed_reversal: str = Field(min_length=1)
    maximum_spread_bps: Decimal = Field(gt=0)
    order_notional_krw: MonetaryDecimal = Field(gt=0)
    long_only: Literal[True]


class ExitPlan(_FrozenModel):
    profit_target_bps: Decimal = Field(gt=0)
    stop_loss_bps: Decimal = Field(gt=0)
    maximum_holding_seconds: Annotated[int, Field(gt=0)]
    cooldown_seconds: Annotated[int, Field(ge=0)]
    close_open_position_at_split_boundary: Literal[True]


class CostScenarioPlan(_FrozenModel):
    paper_fill_model: Literal["conservative_l2"]
    maker_fee_rate: MonetaryDecimal = Field(gt=0)
    taker_fee_rate: MonetaryDecimal = Field(gt=0)
    fee_note: str = Field(min_length=1)
    order_latency_ms: Annotated[int, Field(ge=0)]
    cancel_latency_ms: Annotated[int, Field(ge=0)]
    depth_haircut: MonetaryDecimal = Field(ge=0, le=1)
    queue_factor: MonetaryDecimal = Field(ge=0, le=1)
    snapshot_decrease_fill_fraction: MonetaryDecimal = Field(ge=0, le=1)
    slippage_buffer_bps: MonetaryDecimal = Field(ge=0)
    adverse_selection_bps: MonetaryDecimal = Field(ge=0)

    def execution_policy(self) -> PaperExecutionPolicy:
        return PaperExecutionPolicy(
            maker_fee_rate=self.maker_fee_rate,
            taker_fee_rate=self.taker_fee_rate,
            order_latency_ms=self.order_latency_ms,
            cancel_latency_ms=self.cancel_latency_ms,
            depth_haircut=self.depth_haircut,
            queue_factor=self.queue_factor,
            snapshot_decrease_fill_fraction=self.snapshot_decrease_fill_fraction,
            slippage_buffer_bps=self.slippage_buffer_bps,
            adverse_selection_bps=self.adverse_selection_bps,
        )


class ValidationPlan(_FrozenModel):
    minimum_observed_span_hours: Annotated[int, Field(gt=0)]
    minimum_trade_events_per_market: Annotated[int, Field(gt=0)]
    minimum_orderbook_events_per_market: Annotated[int, Field(gt=0)]
    minimum_eligible_markets: Annotated[int, Field(gt=0)]
    walk_forward_folds: Annotated[int, Field(ge=2)]
    minimum_closed_trades_per_rule: Annotated[int, Field(gt=0)]
    planned_trial_count: Annotated[int, Field(gt=0)]
    random_seed: int
    baseline: Literal["always_neutral"]
    multiple_testing_control: str = Field(min_length=1)
    regime_checks: tuple[str, ...] = Field(min_length=1)


class MetricsPlan(_FrozenModel):
    primary: str = Field(min_length=1)
    secondary: tuple[str, ...] = Field(min_length=1)


class DecisionRulesPlan(_FrozenModel):
    blocked: str = Field(min_length=1)
    reject: str = Field(min_length=1)
    continue_research: str = Field(min_length=1)
    paper_candidate: str = Field(min_length=1)
    automatic_promotion: Literal[False]
    human_paper_review_required: Literal[True]
    highest_allowed_label: Literal["PAPER_CANDIDATE"]


class ResearchSafetyPlan(_FrozenModel):
    authentication_used: Literal[False]
    private_network_used: Literal[False]
    order_network_used: Literal[False]
    real_orders_executed: Literal[False]
    live_mode_changed: Literal[False]
    risk_limits_changed: Literal[False]
    model_promoted: Literal[False]
    paper_order_gate_changed: Literal[False]


class ScalpingExperimentPlan(_FrozenModel):
    schema_version: Literal["scalping-experiment-plan-1", "scalping-experiment-plan-2"]
    experiment_id: str = Field(pattern=r"^[a-z0-9-]+$")
    registered_at_utc: datetime
    researcher: str = Field(min_length=1)
    source_revision: str = Field(pattern=r"^[a-f0-9]{7,64}$")
    hypothesis_ids: tuple[str, ...] = Field(min_length=1)
    dataset_selection: DatasetSelectionPlan
    availability_and_leakage: AvailabilityLeakagePlan
    feature_and_entry_rules: FeatureEntryPlan | ReversalFeatureEntryPlan
    exit_rules: ExitPlan
    cost_scenarios: dict[str, CostScenarioPlan]
    validation: ValidationPlan
    metrics: MetricsPlan
    decision_rules: DecisionRulesPlan
    safety: ResearchSafetyPlan

    @field_validator("registered_at_utc")
    @classmethod
    def require_registered_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("experiment registration must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_trial_space(self) -> "ScalpingExperimentPlan":
        if tuple(sorted(self.cost_scenarios)) != ("base", "stress"):
            raise ValueError("scalping plan requires exact base and stress cost scenarios")
        if len(self.hypothesis_ids) != len(set(self.hypothesis_ids)):
            raise ValueError("hypothesis identifiers must be unique")
        planned = (
            len(self.hypothesis_ids) * len(self.cost_scenarios) * self.validation.walk_forward_folds
        )
        if self.validation.planned_trial_count % planned != 0:
            raise ValueError(
                "planned trial count must be a whole partition of the declared search space"
            )
        receive_cutoff = self.dataset_selection.maximum_received_at_utc
        if receive_cutoff is not None and receive_cutoff > self.registered_at_utc:
            raise ValueError("dataset receive cutoff cannot follow experiment registration")
        if self.schema_version == "scalping-experiment-plan-1":
            if not isinstance(self.feature_and_entry_rules, FeatureEntryPlan):
                raise ValueError("version-1 plans require continuation entry rules")
        elif not isinstance(self.feature_and_entry_rules, ReversalFeatureEntryPlan):
            raise ValueError("version-2 plans require reversal entry rules")
        if self.schema_version == "scalping-experiment-plan-2":
            if self.hypothesis_ids != (
                "H-SCALP-004",
                "H-SCALP-005",
                "H-SCALP-006",
            ):
                raise ValueError("version-2 plans require the fixed reversal hypotheses")
            fixed_markets = self.dataset_selection.fixed_markets
            if (
                fixed_markets is None
                or len(fixed_markets) != self.validation.minimum_eligible_markets
            ):
                raise ValueError("version-2 plans require every eligible market to be fixed")
            if self.dataset_selection.minimum_received_at_utc is None:
                raise ValueError("version-2 plans require a prospective receive-time lower bound")
            if self.dataset_selection.maximum_received_at_utc is None:
                raise ValueError("version-2 plans require a fixed receive-time upper bound")
            if self.validation.planned_trial_count != planned * len(fixed_markets):
                raise ValueError("version-2 trials must cover every fixed market exactly once")
        return self

    @property
    def digest(self) -> str:
        values = self.model_dump(mode="json")
        selection = values["dataset_selection"]
        if self.schema_version == "scalping-experiment-plan-1":
            selection.pop("minimum_received_at_utc", None)
            selection.pop("fixed_markets", None)
        payload = orjson.dumps(values, option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()


class MarketSufficiency(_FrozenModel):
    market: str
    observed_span_hours: float = Field(ge=0)
    trade_events: Annotated[int, Field(ge=0)]
    orderbook_events: Annotated[int, Field(ge=0)]
    eligible: bool
    reasons: tuple[str, ...]


class ScalpingDataSufficiency(_FrozenModel):
    meets_requirements: bool
    eligible_markets: tuple[str, ...]
    observed_markets: tuple[MarketSufficiency, ...]
    reasons: tuple[str, ...]


class ScalpingTradeResult(_FrozenModel):
    trade_id: UUID
    market: str
    opened_at_utc: datetime
    closed_at_utc: datetime
    exit_reason: ScalpingExitReason
    quantity: MonetaryDecimal = Field(gt=0)
    entry_notional: MonetaryDecimal = Field(gt=0)
    exit_notional: MonetaryDecimal = Field(gt=0)
    gross_pnl: MonetaryDecimal
    fees: MonetaryDecimal = Field(ge=0)
    net_pnl: MonetaryDecimal
    net_return_bps: Decimal
    holding_seconds: float = Field(ge=0)


class ScalpingBacktestResult(_FrozenModel):
    schema_version: Literal["scalping-backtest-1"] = "scalping-backtest-1"
    run_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    experiment_id: str
    market: str
    rule: ScalpingRule
    cost_scenario: str
    fold_id: str
    code_version: str
    random_seed: int
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    replay_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    started_at_utc: datetime
    ended_at_utc: datetime
    signal_count: Annotated[int, Field(ge=0)]
    order_count: Annotated[int, Field(ge=0)]
    fill_count: Annotated[int, Field(ge=0)]
    non_fill_order_count: Annotated[int, Field(ge=0)]
    closed_trade_count: Annotated[int, Field(ge=0)]
    open_position_at_end: bool
    gross_pnl: MonetaryDecimal
    fees: MonetaryDecimal = Field(ge=0)
    net_pnl: MonetaryDecimal
    spread_cost: MonetaryDecimal = Field(ge=0)
    slippage_cost: MonetaryDecimal = Field(ge=0)
    adverse_selection_cost: MonetaryDecimal = Field(ge=0)
    turnover: MonetaryDecimal = Field(ge=0)
    maximum_drawdown: MonetaryDecimal = Field(ge=0)
    maximum_drawdown_ratio: Decimal = Field(ge=0)
    win_rate: float | None = Field(default=None, ge=0, le=1)
    average_holding_seconds: float | None = Field(default=None, ge=0)
    trades: tuple[ScalpingTradeResult, ...]
    portfolio: PortfolioSnapshot
    authentication_used: Literal[False] = False
    private_network_used: Literal[False] = False
    order_network_used: Literal[False] = False
    real_orders_executed: Literal[False] = False
    live_submission_allowed: Literal[False] = False


class ScalpingResearchReport(_FrozenModel):
    schema_version: Literal["scalping-research-report-1"] = "scalping-research-report-1"
    experiment_id: str
    generated_at_utc: datetime
    source_revision: str = Field(pattern=r"^[a-f0-9]{7,64}$")
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    inventory: RawEventResearchInventory
    sufficiency: ScalpingDataSufficiency
    decision: ScalpingResearchDecision
    summary: str = Field(min_length=1)
    trial_results: tuple[ScalpingBacktestResult, ...] = ()
    final_holdout_used: Literal[False] = False
    human_review_required: Literal[True] = True
    safety: ResearchSafetyPlan


@dataclass(slots=True)
class _OpenTrade:
    opened_at_utc: datetime
    entry_notional: Decimal = Decimal(0)
    entry_fee: Decimal = Decimal(0)
    quantity: Decimal = Decimal(0)
    exit_notional: Decimal = Decimal(0)
    exit_fee: Decimal = Decimal(0)
    exit_reason: ScalpingExitReason | None = None


def load_scalping_experiment_plan(path: Path) -> ScalpingExperimentPlan:
    return ScalpingExperimentPlan.model_validate(orjson.loads(path.read_bytes()))


def evaluate_scalping_data_sufficiency(
    plan: ScalpingExperimentPlan,
    inventory: RawEventResearchInventory,
) -> ScalpingDataSufficiency:
    observed: list[MarketSufficiency] = []
    for item in inventory.markets:
        hours = item.observed_span_seconds / 3600
        reasons: list[str] = []
        if hours < plan.validation.minimum_observed_span_hours:
            reasons.append("OBSERVED_SPAN_TOO_SHORT")
        if item.trade_events < plan.validation.minimum_trade_events_per_market:
            reasons.append("INSUFFICIENT_TRADE_EVENTS")
        if item.orderbook_events < plan.validation.minimum_orderbook_events_per_market:
            reasons.append("INSUFFICIENT_ORDERBOOK_EVENTS")
        observed.append(
            MarketSufficiency(
                market=item.market,
                observed_span_hours=hours,
                trade_events=item.trade_events,
                orderbook_events=item.orderbook_events,
                eligible=not reasons,
                reasons=tuple(reasons),
            )
        )
    fixed_markets = plan.dataset_selection.fixed_markets
    if fixed_markets is not None:
        observed_names = {item.market for item in observed}
        observed.extend(
            MarketSufficiency(
                market=market,
                observed_span_hours=0,
                trade_events=0,
                orderbook_events=0,
                eligible=False,
                reasons=("MISSING_FIXED_MARKET",),
            )
            for market in fixed_markets
            if market not in observed_names
        )
        observed.sort(key=lambda item: item.market)
    eligible = tuple(item.market for item in observed if item.eligible)
    reasons = []
    if len(eligible) < plan.validation.minimum_eligible_markets:
        reasons.append("INSUFFICIENT_ELIGIBLE_MARKETS")
    if inventory.selected_event_count == 0:
        reasons.append("NO_DETAILED_PUBLIC_EVENTS")
    if fixed_markets is not None and eligible != fixed_markets:
        reasons.append("FIXED_MARKET_REQUIREMENTS_NOT_MET")
    return ScalpingDataSufficiency(
        meets_requirements=not reasons,
        eligible_markets=eligible,
        observed_markets=tuple(observed),
        reasons=tuple(reasons),
    )


class ScalpingBacktestEngine:
    """Long-only rule replay through the conservative public-L2 paper broker."""

    def __init__(
        self,
        plan: ScalpingExperimentPlan,
        *,
        market: str,
        rule: ScalpingRule,
        cost_scenario: str,
        fold_id: str,
        code_version: str,
        entry_start_utc: datetime | None = None,
    ) -> None:
        if cost_scenario not in plan.cost_scenarios:
            raise ScalpingResearchError("cost scenario was not preregistered")
        self.plan = plan
        self.market = market
        self.rule = rule
        self.cost_scenario = cost_scenario
        self.fold_id = fold_id
        self.code_version = code_version
        self.entry_start_utc = entry_start_utc

    def run(
        self,
        events: Sequence[EventEnvelope],
        *,
        maximum_events: int | None = None,
        maximum_elapsed_seconds: float | None = None,
    ) -> ScalpingBacktestResult:
        if not events or any(event.market != self.market for event in events):
            raise ScalpingResearchError("trial requires nonempty single-market events")
        if maximum_events is not None and maximum_events < 1:
            raise ValueError("trial event limit must be positive")
        if maximum_elapsed_seconds is not None and maximum_elapsed_seconds <= 0:
            raise ValueError("trial wall-time limit must be positive")
        if maximum_events is not None and len(events) > maximum_events:
            raise ScalpingTrialLimitError(f"trial input exceeds the {maximum_events} event limit")
        started_at = monotonic()

        def require_deadline() -> None:
            if (
                maximum_elapsed_seconds is not None
                and monotonic() - started_at > maximum_elapsed_seconds
            ):
                raise ScalpingTrialLimitError(f"trial exceeded {maximum_elapsed_seconds:g} seconds")

        policy = self.plan.cost_scenarios[self.cost_scenario].execution_policy()
        broker = PaperBroker(policy)
        ledger = PortfolioLedger(market=self.market, initial_cash="1000000")
        pipeline = RealtimePaperPipeline((self.market,))
        trades: list[ScalpingTradeResult] = []
        open_trade: _OpenTrade | None = None
        exit_reasons: dict[UUID, ScalpingExitReason] = {}
        signal_count = 0
        submission_rejections = 0
        last_mark: Decimal | None = None
        peak_equity = Decimal("1000000")
        maximum_drawdown = Decimal(0)
        maximum_drawdown_ratio = Decimal(0)
        cooldown_until: datetime | None = None
        ordered_end = max(event.received_at_utc for event in events)
        processed_events = 0

        def apply_updates(updates: Sequence[PaperExecutionUpdate]) -> None:
            nonlocal open_trade, cooldown_until
            for update in updates:
                ledger.record_order_update(update)
                for fill in update.fills:
                    if fill.side == "bid" and open_trade is None:
                        open_trade = _OpenTrade(opened_at_utc=fill.filled_at)
                    ledger.apply_fill(fill)
                    if fill.side == "bid":
                        assert open_trade is not None
                        open_trade.entry_notional += fill.notional
                        open_trade.entry_fee += fill.fee
                        open_trade.quantity += fill.quantity
                    else:
                        if open_trade is None:
                            raise ScalpingResearchError("sell fill has no open research trade")
                        open_trade.exit_notional += fill.notional
                        open_trade.exit_fee += fill.fee
                        open_trade.exit_reason = exit_reasons.get(
                            fill.order_id, ScalpingExitReason.TIME_STOP
                        )
                        if ledger.position_quantity == 0:
                            gross = open_trade.exit_notional - open_trade.entry_notional
                            fees = open_trade.entry_fee + open_trade.exit_fee
                            net = gross - fees
                            entry_cost = open_trade.entry_notional + open_trade.entry_fee
                            closed_at = fill.filled_at
                            trades.append(
                                ScalpingTradeResult(
                                    trade_id=deterministic_execution_id(
                                        "scalping-trade", fill.fill_id, len(trades) + 1
                                    ),
                                    market=self.market,
                                    opened_at_utc=open_trade.opened_at_utc,
                                    closed_at_utc=closed_at,
                                    exit_reason=open_trade.exit_reason,
                                    quantity=open_trade.quantity,
                                    entry_notional=open_trade.entry_notional,
                                    exit_notional=open_trade.exit_notional,
                                    gross_pnl=gross,
                                    fees=fees,
                                    net_pnl=net,
                                    net_return_bps=net / entry_cost * BPS,
                                    holding_seconds=(
                                        closed_at - open_trade.opened_at_utc
                                    ).total_seconds(),
                                )
                            )
                            open_trade = None
                            cooldown_until = closed_at + timedelta(
                                seconds=self.plan.exit_rules.cooldown_seconds
                            )
                if update.order.status in TERMINAL_STATUSES:
                    ledger.release_order(update.order.order_id, at=update.occurred_at)

        def has_working_order() -> bool:
            return any(order.status not in TERMINAL_STATUSES for order in broker.orders)

        def submit(
            side: Literal["bid", "ask"],
            now: datetime,
            reason: str,
            *,
            reference_price: Decimal | None = None,
        ) -> None:
            nonlocal signal_count, submission_rejections
            if side == "bid":
                if reference_price is None:
                    raise ScalpingResearchError("research entry requires a causal reference price")
                requested_notional = None
                requested_quantity = (
                    self.plan.feature_and_entry_rules.order_notional_krw / reference_price
                ).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
            else:
                requested_notional = None
                requested_quantity = ledger.position_quantity - ledger.locked_quantity
                if requested_quantity <= 0:
                    return
            signal_count += 1
            intent_id = deterministic_execution_id(
                "scalping-intent",
                self.plan.experiment_id,
                self.market,
                self.rule,
                self.cost_scenario,
                self.fold_id,
                signal_count,
                now.isoformat(),
            )
            expected_cost = self._expected_cost_bps(policy)
            intent = OrderIntent(
                intent_id=intent_id,
                strategy_id=f"research-{self.rule.value}",
                strategy_version=self.plan.digest[:16],
                market=self.market,
                side=side,
                requested_notional=requested_notional,
                requested_quantity=requested_quantity,
                order_type="market",
                signal_timestamp=now,
                expires_at=now + timedelta(seconds=2),
                expected_gross_edge_bps=float(self.plan.exit_rules.profit_target_bps),
                expected_cost_bps=float(expected_cost),
                expected_net_edge_bps=float(self.plan.exit_rules.profit_target_bps - expected_cost),
                confidence=0.5,
                uncertainty=0.5,
                reason=reason,
            )
            ledger.record_intent(intent)
            decision = RiskDecision(
                decision_id=deterministic_execution_id("scalping-risk", intent_id),
                intent_id=intent_id,
                decision=RiskDecisionType.ALLOW,
                approved_notional=requested_notional,
                approved_quantity=requested_quantity,
                reason_codes=("PREREGISTERED_RESEARCH_FIXED_SIZE",),
                risk_snapshot_id=deterministic_execution_id("scalping-risk-snapshot", intent_id),
                policy_version="research-fixed-risk-1",
                decided_at=now,
            )
            ledger.record_risk_decision(decision)
            try:
                submitted = broker.submit(intent, decision, submitted_at=now)
            except PaperExecutionRejected:
                submission_rejections += 1
                return
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
                return
            if side == "ask":
                exit_reasons[submitted.order.order_id] = ScalpingExitReason(reason)

        def handle(item: EventEnvelope | DataGap, clock: VirtualClock) -> bytes:
            nonlocal last_mark, peak_equity, maximum_drawdown
            nonlocal maximum_drawdown_ratio, processed_events
            processed_events += 1
            if processed_events % 1_024 == 0:
                require_deadline()
            now = clock.now
            if isinstance(item, DataGap):
                apply_updates(broker.on_item(item, now=now))
                return b"gap"
            event = item
            last_mark = _event_mark(event)
            apply_updates(broker.on_item(event, now=now))
            frame = pipeline.process(event)
            if last_mark is not None:
                equity = ledger.view(mark_price=last_mark, as_of=now).equity
                peak_equity = max(peak_equity, equity)
                drawdown = peak_equity - equity
                maximum_drawdown = max(maximum_drawdown, drawdown)
                if peak_equity > 0:
                    maximum_drawdown_ratio = max(maximum_drawdown_ratio, drawdown / peak_equity)
            if frame is None or has_working_order():
                return b"hold"
            boundary_lead = timedelta(milliseconds=policy.order_latency_ms + 500)
            if ledger.position_quantity > 0:
                reason = self._exit_reason(
                    frame,
                    ledger,
                    open_trade,
                    now,
                    split_boundary=now >= ordered_end - boundary_lead,
                )
                if reason is not None:
                    submit("ask", now, reason.value)
                    return reason.value.encode()
            elif (
                self.rule is not ScalpingRule.ALWAYS_NEUTRAL
                and (self.entry_start_utc is None or now >= self.entry_start_utc)
                and (cooldown_until is None or now >= cooldown_until)
                and self._entry_matches(frame)
            ):
                submit(
                    "bid",
                    now,
                    f"entry:{self.rule.value}",
                    reference_price=frame.best_ask,
                )
                return self.rule.value.encode()
            return b"hold"

        require_deadline()
        replay = ReplayEngine().run(events, handle)
        require_deadline()
        apply_updates(broker.close(closed_at=replay.ended_at_utc))
        if last_mark is None:
            raise ScalpingResearchError("trial has no price-bearing event")
        portfolio = ledger.snapshot(mark_price=last_mark, as_of=replay.ended_at_utc)
        ledger.verify()
        fills = broker.fills
        non_fills = sum(
            1
            for order in broker.orders
            if not any(fill.order_id == order.order_id for fill in fills)
        )
        result_values: dict[str, object] = {
            "schema_version": "scalping-backtest-1",
            "experiment_id": self.plan.experiment_id,
            "market": self.market,
            "rule": self.rule,
            "cost_scenario": self.cost_scenario,
            "fold_id": self.fold_id,
            "code_version": self.code_version,
            "random_seed": self.plan.validation.random_seed,
            "dataset_hash": replay.dataset_hash,
            "replay_output_hash": replay.output_hash,
            "execution_policy_hash": policy.digest,
            "started_at_utc": replay.started_at_utc,
            "ended_at_utc": replay.ended_at_utc,
            "signal_count": signal_count,
            "order_count": len(broker.orders),
            "fill_count": len(fills),
            "non_fill_order_count": non_fills + submission_rejections,
            "closed_trade_count": len(trades),
            "open_position_at_end": ledger.position_quantity > 0,
            "gross_pnl": portfolio.gross_pnl,
            "fees": portfolio.fees,
            "net_pnl": portfolio.net_pnl,
            "spread_cost": portfolio.spread_cost,
            "slippage_cost": portfolio.slippage_cost,
            "adverse_selection_cost": portfolio.adverse_selection_cost,
            "turnover": sum((fill.notional for fill in fills), start=Decimal(0)),
            "maximum_drawdown": maximum_drawdown,
            "maximum_drawdown_ratio": maximum_drawdown_ratio,
            "win_rate": (
                sum(trade.net_pnl > 0 for trade in trades) / len(trades) if trades else None
            ),
            "average_holding_seconds": (
                sum(trade.holding_seconds for trade in trades) / len(trades) if trades else None
            ),
            "trades": tuple(trades),
            "portfolio": portfolio,
            "authentication_used": False,
            "private_network_used": False,
            "order_network_used": False,
            "real_orders_executed": False,
            "live_submission_allowed": False,
        }
        run_id = sha256(
            "|".join(
                (
                    replay.dataset_hash,
                    self.plan.digest,
                    self.market,
                    self.rule,
                    self.cost_scenario,
                    self.fold_id,
                    self.code_version,
                )
            ).encode()
        ).hexdigest()
        output_hash = sha256(
            orjson.dumps(result_values, default=str, option=orjson.OPT_SORT_KEYS)
        ).hexdigest()
        return ScalpingBacktestResult(**result_values, run_id=run_id, output_hash=output_hash)

    def _entry_matches(self, frame: RealtimeFeatureFrame) -> bool:
        if not frame.ready_for_inference or frame.spread_bps is None:
            return False
        entry = self.plan.feature_and_entry_rules
        if Decimal(str(frame.spread_bps)) > entry.maximum_spread_bps:
            return False
        if isinstance(entry, FeatureEntryPlan):
            trade = entry.trade_continuation
            book = entry.snapshot_book_pressure
            trade_match = (
                frame.trade_return_5s_bps is not None
                and Decimal(str(frame.trade_return_5s_bps)) >= trade.minimum_trade_return_5s_bps
                and frame.trade_imbalance_1s is not None
                and Decimal(str(frame.trade_imbalance_1s)) >= trade.minimum_trade_imbalance_1s
                and frame.trade_count_5s >= trade.minimum_trade_count_5s
            )
            book_match = (
                frame.top_book_imbalance is not None
                and Decimal(str(frame.top_book_imbalance)) >= book.minimum_top_book_imbalance
                and frame.total_book_imbalance is not None
                and Decimal(str(frame.total_book_imbalance)) >= book.minimum_total_book_imbalance
                and frame.book_flow_delta is not None
                and Decimal(str(frame.book_flow_delta)) >= book.minimum_snapshot_derived_ofi
            )
            if self.rule is ScalpingRule.TRADE_CONTINUATION:
                return trade_match
            if self.rule is ScalpingRule.SNAPSHOT_BOOK_PRESSURE:
                return book_match
            if self.rule is ScalpingRule.CONFIRMED_CONTINUATION:
                return trade_match and book_match
            return False

        reversal_trade = entry.sell_shock_exhaustion
        reversal_book = entry.bid_replenishment_reversal
        trade_match = (
            frame.trade_return_5s_bps is not None
            and Decimal(str(frame.trade_return_5s_bps))
            <= reversal_trade.maximum_trade_return_5s_bps
            and frame.trade_imbalance_5s is not None
            and Decimal(str(frame.trade_imbalance_5s)) <= reversal_trade.maximum_trade_imbalance_5s
            and frame.trade_return_1s_bps is not None
            and Decimal(str(frame.trade_return_1s_bps))
            >= reversal_trade.minimum_recovery_return_1s_bps
            and frame.trade_imbalance_1s is not None
            and Decimal(str(frame.trade_imbalance_1s))
            >= reversal_trade.minimum_recovery_trade_imbalance_1s
            and frame.trade_count_5s >= reversal_trade.minimum_trade_count_5s
        )
        book_match = (
            frame.trade_return_5s_bps is not None
            and Decimal(str(frame.trade_return_5s_bps)) <= reversal_book.maximum_trade_return_5s_bps
            and frame.top_book_imbalance is not None
            and Decimal(str(frame.top_book_imbalance)) >= reversal_book.minimum_top_book_imbalance
            and frame.total_book_imbalance is not None
            and Decimal(str(frame.total_book_imbalance))
            >= reversal_book.minimum_total_book_imbalance
            and frame.book_flow_delta is not None
            and Decimal(str(frame.book_flow_delta)) >= reversal_book.minimum_snapshot_derived_ofi
        )
        if self.rule is ScalpingRule.SELL_SHOCK_EXHAUSTION:
            return trade_match
        if self.rule is ScalpingRule.BID_REPLENISHMENT_REVERSAL:
            return book_match
        if self.rule is ScalpingRule.CONFIRMED_REVERSAL:
            return trade_match and book_match
        return False

    def _exit_reason(
        self,
        frame: RealtimeFeatureFrame,
        ledger: PortfolioLedger,
        open_trade: _OpenTrade | None,
        now: datetime,
        *,
        split_boundary: bool,
    ) -> ScalpingExitReason | None:
        if split_boundary:
            return ScalpingExitReason.SPLIT_BOUNDARY
        mark = frame.last_trade_price if frame.source_event_type == "trade" else frame.mid_price
        if mark is None:
            return None
        view = ledger.view(mark_price=mark, as_of=now)
        if view.average_entry_price is None:
            return None
        return_bps = (mark - view.average_entry_price) / view.average_entry_price * BPS
        if return_bps >= self.plan.exit_rules.profit_target_bps:
            return ScalpingExitReason.PROFIT_TARGET
        if return_bps <= -self.plan.exit_rules.stop_loss_bps:
            return ScalpingExitReason.STOP_LOSS
        if (
            open_trade is not None
            and (now - open_trade.opened_at_utc).total_seconds()
            >= self.plan.exit_rules.maximum_holding_seconds
        ):
            return ScalpingExitReason.TIME_STOP
        return None

    @staticmethod
    def _expected_cost_bps(policy: PaperExecutionPolicy) -> Decimal:
        return (
            (policy.taker_fee_rate * BPS)
            + policy.slippage_buffer_bps
            + policy.adverse_selection_bps
        ) * 2


def create_blocked_scalping_report(
    plan: ScalpingExperimentPlan,
    inventory: RawEventResearchInventory,
    sufficiency: ScalpingDataSufficiency,
    *,
    source_revision: str,
    generated_at_utc: datetime,
) -> ScalpingResearchReport:
    if sufficiency.meets_requirements:
        raise ScalpingResearchError("blocked report requires an insufficient dataset")
    return ScalpingResearchReport(
        experiment_id=plan.experiment_id,
        generated_at_utc=generated_at_utc,
        source_revision=source_revision,
        plan_sha256=plan.digest,
        inventory=inventory,
        sufficiency=sufficiency,
        decision=ScalpingResearchDecision.BLOCKED,
        summary=(
            "The preregistered public-data minimum was not met, so no strategy trial or final "
            "holdout access occurred. This retained result makes no profitability claim."
        ),
        safety=plan.safety,
    )


def blocked_experiment_ledger(
    plan: ScalpingExperimentPlan,
    inventory: RawEventResearchInventory,
    sufficiency: ScalpingDataSufficiency,
    *,
    source_revision: str,
    generated_at_utc: datetime,
) -> ExperimentLedgerSnapshot:
    if sufficiency.meets_requirements:
        raise ScalpingResearchError("blocked ledger requires an insufficient dataset")
    experiment_id = new_experiment_id(
        plan.experiment_id, inventory.dataset_hash, plan.registered_at_utc
    )
    ledger = ExperimentLedger()
    ledger.preregister(
        ExperimentRegistration(
            experiment_id=experiment_id,
            hypothesis_id="+".join(plan.hypothesis_ids),
            created_at_utc=plan.registered_at_utc,
            researcher=plan.researcher,
            code_version=source_revision,
            dataset_hash=inventory.dataset_hash,
            feature_set=plan.feature_and_entry_rules.feature_contract,
            label_version="cost-inclusive-round-trip-v1",
            model_family="preregistered-deterministic-rules",
            hyperparameter_space=tuple(
                sorted(
                    (
                        ("cost_scenario", tuple(sorted(plan.cost_scenarios))),
                        (
                            "fold",
                            tuple(
                                str(index + 1)
                                for index in range(plan.validation.walk_forward_folds)
                            ),
                        ),
                        ("hypothesis", plan.hypothesis_ids),
                    )
                )
            ),
            planned_metrics=(
                "adverse_selection_cost",
                "average_holding_seconds",
                "fees",
                "gross_pnl",
                "maximum_drawdown",
                "net_pnl",
                "slippage_cost",
                "spread_cost",
                "turnover",
                "win_rate",
            ),
            planned_splits=(SplitRole.VALIDATION, SplitRole.TEST),
            planned_cost_model="conservative_l2 base and stress",
            final_holdout_planned=False,
        )
    )
    max_span = max((item.observed_span_hours for item in sufficiency.observed_markets), default=0.0)
    ledger.close(
        ExperimentSummary(
            experiment_id=experiment_id,
            closed_at_utc=generated_at_utc,
            trial_count=0,
            failure_count=0,
            oos_metrics=(
                ("eligible_markets", float(len(sufficiency.eligible_markets))),
                ("maximum_observed_span_hours", max_span),
            ),
            holdout_used=False,
            decision=ExperimentDecision.HOLD,
            reason="preregistered public-data minimum was not met before any trial",
        )
    )
    ledger.verify()
    return ledger.snapshot()


def write_scalping_research_bundle(
    report: ScalpingResearchReport,
    ledger: ExperimentLedgerSnapshot,
    output_root: Path,
) -> tuple[Path, Path, Path]:
    date_path = report.generated_at_utc.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y/%m/%d")
    destination = output_root / date_path
    destination.mkdir(parents=True, exist_ok=True)
    stem = report.experiment_id
    json_path = destination / f"{stem}.json"
    ledger_path = destination / f"{stem}.ledger.json"
    markdown_path = destination / f"{stem}.md"
    _atomic_json(json_path, report.model_dump(mode="json"))
    _atomic_json(ledger_path, ledger.model_dump(mode="json"))
    rows = "\n".join(
        f"| {item.market} | {item.observed_span_hours:.2f} | {item.trade_events} | "
        f"{item.orderbook_events} | {'yes' if item.eligible else 'no'} | "
        f"{', '.join(item.reasons) or '-'} |"
        for item in report.sufficiency.observed_markets
    )
    body = (
        f"# {report.experiment_id}\n\n"
        f"- Decision: `{report.decision}`\n"
        f"- Generated: `{report.generated_at_utc.isoformat()}`\n"
        f"- Source revision: `{report.source_revision}`\n"
        f"- Plan SHA-256: `{report.plan_sha256}`\n"
        f"- Dataset SHA-256: `{report.inventory.dataset_hash}`\n"
        f"- Detailed public events: `{report.inventory.selected_event_count}`\n"
        f"- Eligible markets: `{len(report.sufficiency.eligible_markets)}`\n"
        f"- Final holdout used: `{str(report.final_holdout_used).lower()}`\n\n"
        f"{report.summary}\n\n"
        "## Data sufficiency\n\n"
        "| Market | Hours | Trades | Orderbooks | Eligible | Reasons |\n"
        "| --- | ---: | ---: | ---: | --- | --- |\n"
        f"{rows}\n\n"
        "No authentication, private/order network, real order, live-mode change, risk-limit "
        "change, model promotion, or paper-order gate change occurred.\n"
    )
    _atomic_bytes(markdown_path, body.encode())
    return markdown_path, json_path, ledger_path


def _event_mark(event: EventEnvelope) -> Decimal:
    if event.event_type == "orderbook":
        book = UpbitOrderbook.model_validate(event.raw_payload)
        return (
            min(unit.ask_price for unit in book.orderbook_units)
            + max(unit.bid_price for unit in book.orderbook_units)
        ) / Decimal(2)
    if event.event_type == "trade":
        return UpbitTrade.model_validate(event.raw_payload).trade_price
    return UpbitTicker.model_validate(event.raw_payload).trade_price


def _atomic_json(path: Path, payload: object) -> None:
    _atomic_bytes(
        path,
        orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n",
    )


def _atomic_bytes(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

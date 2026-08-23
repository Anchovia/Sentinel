"""Fail-closed real-time paper composition outside every real-order boundary."""

import math
import os
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns
from typing import Annotated, Literal, Protocol
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import (
    EventEnvelope,
    OrderIntent,
    OrderStatus,
    PaperExecutionPolicy,
    PaperExecutionUpdate,
    RiskDecision,
    RiskDecisionType,
    deterministic_execution_id,
)
from quantforge.execution.paper import PaperBroker, PaperExecutionRejected
from quantforge.features import FeatureSnapshot
from quantforge.models import (
    AlphaPrediction,
    AlwaysNeutralAlphaBaseline,
    DecisionAction,
    ExecutionRuleBaseline,
    ModelReleaseStatus,
    RuleRegimeBaseline,
)
from quantforge.operations.exports import assert_runtime_export_safe
from quantforge.portfolio import AccountingInvariantError, PortfolioLedger, PortfolioSnapshot
from quantforge.risk import RiskEngine, RiskLimits, RiskSnapshot, StrategyRiskGateway
from quantforge.runtime.paper_recovery import (
    PaperRecoveryIntegrityError,
    PaperRecoveryStatus,
    RealtimePaperRecoveryCheckpoint,
    read_realtime_paper_recovery_checkpoint,
    write_realtime_paper_recovery_checkpoint,
)
from quantforge.runtime.realtime_pipeline import RealtimeFeatureFrame
from quantforge.strategies import (
    LiquidityShockMeanReversion,
    MarketSnapshot,
    OfiMicropriceMomentum,
    RiskContext,
    Strategy,
    StrategyAction,
    StrategyDecision,
    StrategyInput,
    StrategyRouteConfig,
    StrategyRouter,
    StrategyStatus,
)

TERMINAL_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
        OrderStatus.PREVENTED,
    }
)


class RealtimePaperBlocked(ValueError):
    """Raised before an inconsistent model, decision, or accounting state can continue."""


class RealtimePaperDecisionState(StrEnum):
    HOLD = "HOLD"
    ABSTAIN = "ABSTAIN"
    RISK_REJECTED = "RISK_REJECTED"
    PAPER_ORDER = "PAPER_ORDER"
    PAPER_FILL = "PAPER_FILL"


class RealtimeAlphaModel(Protocol):
    """Injected alpha artifact; a matching human approval is independently required."""

    model_version: str
    artifact_hash: str

    def predict(
        self,
        frame: RealtimeFeatureFrame,
        features: FeatureSnapshot,
        *,
        predicted_at_utc: datetime,
        estimated_round_trip_cost_bps: Decimal,
    ) -> AlphaPrediction: ...


class RealtimeModelApproval(BaseModel):
    """Human-supplied paper approval bound to one immutable alpha artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["realtime-model-approval-1"] = "realtime-model-approval-1"
    approval_reference: str = Field(min_length=1, max_length=200)
    approved_by: str = Field(min_length=1, max_length=200)
    approved_at_utc: datetime
    valid_until_utc: datetime
    model_created_at_utc: datetime
    market_scope: tuple[str, ...] = Field(min_length=1)
    model_version: str = Field(min_length=1, max_length=128)
    artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    release_status: Literal[ModelReleaseStatus.PAPER] = ModelReleaseStatus.PAPER

    @field_validator("approved_at_utc", "valid_until_utc", "model_created_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("real-time model approval timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_approval(self) -> "RealtimeModelApproval":
        if self.valid_until_utc <= self.approved_at_utc:
            raise ValueError("real-time model approval validity is invalid")
        if self.model_created_at_utc > self.approved_at_utc:
            raise ValueError("model cannot be created after its approval")
        if len(self.market_scope) != len(set(self.market_scope)) or any(
            not market.startswith("KRW-") for market in self.market_scope
        ):
            raise ValueError("real-time model approval market scope is invalid")
        return self

    def valid_for(self, market: str, at_utc: datetime) -> bool:
        return market in self.market_scope and self.approved_at_utc <= at_utc < self.valid_until_utc


class RealtimePaperDecisionPolicy(BaseModel):
    """Versioned paper-only composition policy; it is not a live risk approval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["realtime-paper-policy-1"] = "realtime-paper-policy-1"
    initial_cash_krw: Decimal = Field(default=Decimal("1000000"), gt=0)
    paper_order_simulation_enabled: bool = False
    inference_valid_seconds: int = Field(default=15, ge=1, le=300)
    decision_budget_ms: float = Field(default=5.0, gt=0)
    latency_window_size: int = Field(default=20_000, ge=1)
    risk_limits: RiskLimits
    routes: tuple[StrategyRouteConfig, ...]
    execution: PaperExecutionPolicy

    @model_validator(mode="after")
    def validate_paper_only(self) -> "RealtimePaperDecisionPolicy":
        if not self.routes or any(
            route.status is not StrategyStatus.ACTIVE for route in self.routes
        ):
            raise ValueError("real-time paper routes must be explicitly active proposal routes")
        return self

    @property
    def digest(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()

    @classmethod
    def conservative_default(cls) -> "RealtimePaperDecisionPolicy":
        return cls(
            risk_limits=RiskLimits(
                policy_version="phase11-paper-1",
                min_order_notional_krw="5000",
                max_order_notional_krw="50000",
                max_position_notional_per_market="200000",
                max_total_exposure_krw="500000",
                max_total_exposure_pct="0.50",
                max_concurrent_positions=3,
                max_daily_loss_krw="50000",
                max_daily_loss_pct="0.05",
                max_drawdown_pct="0.10",
                max_strategy_loss_krw="20000",
                max_consecutive_losses=5,
                max_orders_per_minute=10,
                max_orders_per_market_per_minute=4,
                max_turnover_per_day="2000000",
                max_relative_spread_bps="20",
                max_expected_slippage_bps="10",
                max_data_age_ms=2_000,
                max_clock_skew_ms=500,
                max_unknown_orders=0,
                max_balance_age_seconds=30,
                max_balance_reconciliation_age_seconds=30,
                max_model_age_seconds=3_600,
                max_prediction_age_seconds=10,
                max_prediction_uncertainty=0.50,
                min_expected_net_edge_bps="3",
            ),
            routes=(
                StrategyRouteConfig(
                    strategy_id="ofi-microprice-momentum",
                    status=StrategyStatus.ACTIVE,
                    priority=100,
                    correlation_group="short-horizon-order-flow",
                    capacity_notional="50000",
                    cooldown_seconds=30,
                    max_strategy_loss="20000",
                ),
                StrategyRouteConfig(
                    strategy_id="liquidity-shock-mean-reversion",
                    status=StrategyStatus.ACTIVE,
                    priority=80,
                    correlation_group="short-horizon-reversal",
                    capacity_notional="30000",
                    cooldown_seconds=60,
                    max_strategy_loss="15000",
                ),
            ),
            execution=PaperExecutionPolicy(),
        )


class RealtimePaperDecisionSnapshot(BaseModel):
    """Secret-free shadow/paper decision, execution, and accounting evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["realtime-paper-decision-1"] = "realtime-paper-decision-1"
    generated_at_utc: datetime
    markets: tuple[str, ...] = Field(min_length=1)
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision_state: RealtimePaperDecisionState
    decision_reason: str = Field(min_length=1)
    latest_strategy_id: str | None = None
    latest_reason_codes: tuple[str, ...] = ()
    model_release_status: ModelReleaseStatus
    model_approval_valid: bool
    recovery_status: PaperRecoveryStatus = PaperRecoveryStatus.NOT_CONFIGURED
    recovery_blocked: bool = False
    recovery_checkpoint_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    paper_order_simulation_enabled: bool
    processed_events: Annotated[int, Field(ge=0)]
    feature_ready_frames: Annotated[int, Field(ge=0)]
    inference_frames: Annotated[int, Field(ge=0)]
    strategy_trade_proposals: Annotated[int, Field(ge=0)]
    risk_approvals: Annotated[int, Field(ge=0)]
    risk_rejections: Annotated[int, Field(ge=0)]
    submission_rejections: Annotated[int, Field(ge=0)]
    paper_orders: Annotated[int, Field(ge=0)]
    paper_fills: Annotated[int, Field(ge=0)]
    ledger_records: Annotated[int, Field(ge=0)]
    turnover_krw: Decimal = Field(ge=0)
    decision_budget_ms: float = Field(gt=0)
    decision_budget_breaches: Annotated[int, Field(ge=0)]
    decision_latency_p50_ms: float = Field(ge=0)
    decision_latency_p95_ms: float = Field(ge=0)
    decision_latency_p99_ms: float = Field(ge=0)
    decision_latency_max_ms: float = Field(ge=0)
    observed_events_per_second: float = Field(ge=0)
    portfolios: tuple[PortfolioSnapshot, ...] = ()
    authentication_used: bool = False
    private_network_used: bool = False
    real_order_submission_available: bool = False
    live_submission_allowed: bool = False

    @field_validator("generated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("real-time paper decision timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_safety(self) -> "RealtimePaperDecisionSnapshot":
        if any(
            (
                self.authentication_used,
                self.private_network_used,
                self.real_order_submission_available,
                self.live_submission_allowed,
            )
        ):
            raise ValueError(
                "real-time paper decision snapshot cannot expose real-order capability"
            )
        if self.risk_approvals > self.strategy_trade_proposals:
            raise ValueError("risk approvals cannot exceed strategy trade proposals")
        if self.paper_fills and not self.paper_orders:
            raise ValueError("paper fills require a simulated order")
        if (
            not self.paper_order_simulation_enabled
            and not self.recovery_blocked
            and (self.paper_orders or self.paper_fills)
        ):
            raise ValueError("disabled paper-order simulation cannot contain orders or fills")
        if self.recovery_blocked and self.paper_order_simulation_enabled:
            raise ValueError("blocked paper recovery cannot enable simulated orders")
        return self


class RealtimePaperOrchestrator:
    """Compose inference, proposal routing, independent risk, paper broker, and exact ledger."""

    def __init__(
        self,
        markets: tuple[str, ...],
        *,
        policy: RealtimePaperDecisionPolicy | None = None,
        alpha_model: RealtimeAlphaModel | None = None,
        approval: RealtimeModelApproval | None = None,
        strategies: tuple[Strategy, ...] | None = None,
        recovery_path: Path | None = None,
        clock_ns: Callable[[], int] = perf_counter_ns,
    ) -> None:
        if not markets or len(markets) != len(set(markets)):
            raise ValueError("real-time paper markets must be nonempty and unique")
        if (alpha_model is None) != (approval is None):
            raise RealtimePaperBlocked(
                "alpha model and human paper approval must be supplied together"
            )
        if (
            alpha_model is not None
            and approval is not None
            and (
                alpha_model.model_version != approval.model_version
                or alpha_model.artifact_hash != approval.artifact_hash
            )
        ):
            raise RealtimePaperBlocked("alpha model does not match its human paper approval")
        self.markets = markets
        self.policy = policy or RealtimePaperDecisionPolicy.conservative_default()
        self.alpha_model = alpha_model
        self.approval = approval
        self.strategies = strategies or (OfiMicropriceMomentum(), LiquidityShockMeanReversion())
        configured = {route.strategy_id for route in self.policy.routes}
        supplied = {strategy.strategy_id for strategy in self.strategies}
        if supplied - configured:
            raise RealtimePaperBlocked("a strategy is missing its reviewed paper route")
        self._clock_ns = clock_ns
        self._router = StrategyRouter(self.policy.routes)
        self._gateway = StrategyRiskGateway(RiskEngine(self.policy.risk_limits))
        self._broker = PaperBroker(self.policy.execution)
        self._ledgers = {
            market: PortfolioLedger(market=market, initial_cash=self.policy.initial_cash_krw)
            for market in markets
        }
        self._regime = RuleRegimeBaseline()
        self._execution = ExecutionRuleBaseline(depth_haircut=self.policy.execution.depth_haircut)
        self._neutral = AlwaysNeutralAlphaBaseline()
        self._neutral_hash = sha256(self._neutral.artifact_bytes).hexdigest()
        self._latest_marks: dict[str, Decimal] = {}
        self._latencies_ms: deque[float] = deque(maxlen=self.policy.latency_window_size)
        self._order_times: deque[datetime] = deque()
        self._market_order_times: dict[str, deque[datetime]] = {
            market: deque() for market in markets
        }
        self._processed_events = 0
        self._feature_ready_frames = 0
        self._inference_frames = 0
        self._strategy_trade_proposals = 0
        self._risk_approvals = 0
        self._risk_rejections = 0
        self._submission_rejections = 0
        self._paper_orders = 0
        self._paper_fills = 0
        self._turnover_krw = Decimal(0)
        self._budget_breaches = 0
        self._first_event_at_utc: datetime | None = None
        self._last_event_at_utc: datetime | None = None
        self._peak_equity = {market: self.policy.initial_cash_krw for market in markets}
        self._state = RealtimePaperDecisionState.HOLD
        self._reason = "FEATURES_NOT_READY"
        self._latest_strategy_id: str | None = None
        self._latest_reason_codes: tuple[str, ...] = ()
        self._last_event_id: UUID | None = None
        self._recovery_path = recovery_path
        self._loaded_checkpoint: RealtimePaperRecoveryCheckpoint | None = None
        self._recovery_status = (
            PaperRecoveryStatus.NOT_CONFIGURED if recovery_path is None else PaperRecoveryStatus.NEW
        )
        self._recovery_blocked = False
        self._recovery_checkpoint_hash: str | None = None
        self._recovery_session_active = False
        self._recovery_dirty = False
        if recovery_path is not None and recovery_path.exists():
            self._restore_checkpoint(recovery_path)

    @property
    def paper_order_simulation_available(self) -> bool:
        return self.policy.paper_order_simulation_enabled and not self._recovery_blocked

    def begin_recovery_session(self, *, started_at_utc: datetime) -> None:
        """Mark the durable state active before consuming public events."""

        self._require_utc(started_at_utc)
        if self._recovery_path is None:
            return
        if self._recovery_session_active:
            raise RealtimePaperBlocked("paper recovery session is already active")
        if self._loaded_checkpoint is not None:
            if (
                self._loaded_checkpoint.clean_shutdown
                and not self._loaded_checkpoint.recovery_blocked
            ):
                self._recovery_status = PaperRecoveryStatus.VERIFIED_CLEAN
            elif (
                not self.policy.paper_order_simulation_enabled
                and self._loaded_checkpoint_is_economically_empty()
            ):
                self._recovery_blocked = False
                self._recovery_status = PaperRecoveryStatus.EMPTY_UNCLEAN_RECOVERED
                self._state = RealtimePaperDecisionState.HOLD
                self._reason = "EMPTY_UNCLEAN_PAPER_STATE_RECOVERED"
            else:
                self._recovery_blocked = True
                self._recovery_status = PaperRecoveryStatus.UNCLEAN_RECONCILED
                updates = self._broker.cancel_all(
                    canceled_at=started_at_utc,
                    reason="unclean paper recovery canceled every non-terminal order",
                )
                for market in self.markets:
                    selected = tuple(update for update in updates if update.order.market == market)
                    self._apply_updates(market, selected)
                self._state = RealtimePaperDecisionState.HOLD
                self._reason = "PAPER_RECOVERY_BLOCKED"
        self._recovery_session_active = True
        self.persist_recovery_checkpoint(generated_at_utc=started_at_utc, clean_shutdown=False)

    def persist_recovery_checkpoint(
        self,
        *,
        generated_at_utc: datetime,
        clean_shutdown: bool,
    ) -> RealtimePaperRecoveryCheckpoint | None:
        """Persist complete economic state; clean checkpoints cannot contain open orders."""

        self._require_utc(generated_at_utc)
        if self._recovery_path is None:
            return None
        checkpoint = RealtimePaperRecoveryCheckpoint.create(
            generated_at_utc=generated_at_utc,
            clean_shutdown=clean_shutdown,
            recovery_blocked=self._recovery_blocked,
            policy_hash=self.policy.digest,
            markets=self.markets,
            broker=self._broker.export_state(),
            ledgers=tuple(self._ledgers[market].export_state() for market in self.markets),
            latest_marks=tuple(
                (market, self._latest_marks[market])
                for market in self.markets
                if market in self._latest_marks
            ),
            peak_equities=tuple((market, self._peak_equity[market]) for market in self.markets),
            processed_events=self._processed_events,
            feature_ready_frames=self._feature_ready_frames,
            inference_frames=self._inference_frames,
            strategy_trade_proposals=self._strategy_trade_proposals,
            risk_approvals=self._risk_approvals,
            risk_rejections=self._risk_rejections,
            submission_rejections=self._submission_rejections,
            paper_orders=self._paper_orders,
            paper_fills=self._paper_fills,
            turnover_krw=self._turnover_krw,
            first_event_at_utc=self._first_event_at_utc,
            last_event_at_utc=self._last_event_at_utc,
            last_event_id=self._last_event_id,
            order_times=tuple(self._order_times),
            market_order_times=tuple(
                (market, tuple(self._market_order_times[market])) for market in self.markets
            ),
            decision_state=self._state.value,
            decision_reason=self._reason,
            latest_strategy_id=self._latest_strategy_id,
            latest_reason_codes=self._latest_reason_codes,
        )
        write_realtime_paper_recovery_checkpoint(checkpoint, self._recovery_path)
        self._recovery_checkpoint_hash = checkpoint.checkpoint_hash
        self._recovery_dirty = False
        return checkpoint

    def process(
        self,
        event: EventEnvelope,
        frame: RealtimeFeatureFrame | None,
    ) -> None:
        started_ns = self._clock_ns()
        self._recovery_dirty = False
        try:
            if event.market not in self._ledgers:
                raise RealtimePaperBlocked("event market is outside the paper decision universe")
            if event.is_duplicate:
                return
            if frame is not None and (
                frame.source_event_id != event.event_id or frame.market != event.market
            ):
                raise RealtimePaperBlocked("feature frame is not bound to its source event")
            updates = self._broker.on_item(event, now=event.received_at_utc)
            fills = self._apply_updates(event.market, updates)
            self._processed_events += 1
            if self._first_event_at_utc is None:
                self._first_event_at_utc = event.received_at_utc
            self._last_event_at_utc = event.received_at_utc
            self._last_event_id = event.event_id
            if frame is None or not frame.ready_for_inference:
                self._state = RealtimePaperDecisionState.HOLD
                self._reason = (
                    "|".join(frame.hold_reasons) if frame is not None else "NO_FEATURE_FRAME"
                )
                self._latest_strategy_id = None
                self._latest_reason_codes = frame.hold_reasons if frame is not None else ()
                if fills:
                    self._state = RealtimePaperDecisionState.PAPER_FILL
                    self._reason = "PAPER_FILL_APPLIED"
                return
            self._feature_ready_frames += 1
            inputs = self._strategy_input(frame)
            self._inference_frames += 1
            route = self._router.route(inputs, self.strategies)
            selected = route.selected
            self._latest_strategy_id = selected.strategy_id
            self._latest_reason_codes = selected.reason_codes
            if selected.action is StrategyAction.TRADE:
                self._strategy_trade_proposals += 1
            risk_snapshot = self._risk_snapshot(inputs, selected, frame)
            result = self._gateway.process(selected, risk_snapshot)
            if result.intent is None or result.risk_decision is None:
                self._state = (
                    RealtimePaperDecisionState.ABSTAIN
                    if selected.action is StrategyAction.ABSTAIN
                    else RealtimePaperDecisionState.HOLD
                )
                self._reason = (
                    "NO_APPROVED_ALPHA_MODEL"
                    if not self._approval_valid(event.market, event.received_at_utc)
                    else (
                        "PAPER_RECOVERY_BLOCKED"
                        if self._recovery_blocked
                        else (
                            "PAPER_ORDER_SIMULATION_DISABLED"
                            if not self.policy.paper_order_simulation_enabled
                            else selected.reason_codes[0]
                        )
                    )
                )
            else:
                self._handle_gateway(event.market, result.intent, result.risk_decision)
            if fills and self._state in {
                RealtimePaperDecisionState.HOLD,
                RealtimePaperDecisionState.ABSTAIN,
            }:
                self._state = RealtimePaperDecisionState.PAPER_FILL
                self._reason = "PAPER_FILL_APPLIED"
        finally:
            try:
                if self._recovery_dirty and self._recovery_session_active:
                    self.persist_recovery_checkpoint(
                        generated_at_utc=event.received_at_utc,
                        clean_shutdown=False,
                    )
            finally:
                elapsed_ms = max(0, self._clock_ns() - started_ns) / 1_000_000
                self._latencies_ms.append(elapsed_ms)
                self._budget_breaches += int(elapsed_ms > self.policy.decision_budget_ms)

    def close(self, *, closed_at_utc: datetime) -> None:
        self._require_utc(closed_at_utc)
        updates = self._broker.close(closed_at=closed_at_utc)
        for market in self.markets:
            selected = tuple(update for update in updates if update.order.market == market)
            self._apply_updates(market, selected)
        self._state = RealtimePaperDecisionState.HOLD
        self._reason = "PAPER_RUNTIME_STOPPED"
        if self._recovery_session_active:
            self.persist_recovery_checkpoint(
                generated_at_utc=closed_at_utc,
                clean_shutdown=True,
            )
            self._recovery_session_active = False

    def snapshot(self, *, generated_at_utc: datetime) -> RealtimePaperDecisionSnapshot:
        latencies = sorted(self._latencies_ms)
        elapsed_seconds = (
            (self._last_event_at_utc - self._first_event_at_utc).total_seconds()
            if self._first_event_at_utc is not None and self._last_event_at_utc is not None
            else 0
        )
        portfolios = tuple(
            self._portfolio(market, generated_at_utc)
            for market in self.markets
            if market in self._latest_marks
        )
        approval_valid = any(
            self._approval_valid(market, generated_at_utc) for market in self.markets
        )
        return RealtimePaperDecisionSnapshot(
            generated_at_utc=generated_at_utc,
            markets=self.markets,
            policy_hash=self.policy.digest,
            decision_state=self._state,
            decision_reason=self._reason,
            latest_strategy_id=self._latest_strategy_id,
            latest_reason_codes=self._latest_reason_codes,
            model_release_status=(
                ModelReleaseStatus.PAPER if approval_valid else ModelReleaseStatus.EXPERIMENTAL
            ),
            model_approval_valid=approval_valid,
            recovery_status=self._recovery_status,
            recovery_blocked=self._recovery_blocked,
            recovery_checkpoint_hash=self._recovery_checkpoint_hash,
            paper_order_simulation_enabled=self.paper_order_simulation_available,
            processed_events=self._processed_events,
            feature_ready_frames=self._feature_ready_frames,
            inference_frames=self._inference_frames,
            strategy_trade_proposals=self._strategy_trade_proposals,
            risk_approvals=self._risk_approvals,
            risk_rejections=self._risk_rejections,
            submission_rejections=self._submission_rejections,
            paper_orders=self._paper_orders,
            paper_fills=self._paper_fills,
            ledger_records=sum(len(ledger.records) for ledger in self._ledgers.values()),
            turnover_krw=self._turnover_krw,
            decision_budget_ms=self.policy.decision_budget_ms,
            decision_budget_breaches=self._budget_breaches,
            decision_latency_p50_ms=self._percentile(latencies, 0.50),
            decision_latency_p95_ms=self._percentile(latencies, 0.95),
            decision_latency_p99_ms=self._percentile(latencies, 0.99),
            decision_latency_max_ms=max(latencies, default=0.0),
            observed_events_per_second=(
                self._processed_events / elapsed_seconds if elapsed_seconds > 0 else 0.0
            ),
            portfolios=portfolios,
        )

    def _strategy_input(self, frame: RealtimeFeatureFrame) -> StrategyInput:
        now = frame.available_at_utc
        market = frame.market
        mark = frame.mid_price
        if mark is None or frame.best_ask is None or frame.best_bid is None:
            raise RealtimePaperBlocked("ready feature frame has no executable book")
        self._latest_marks[market] = mark
        event_time = min(frame.event_time_utc, now)
        values = {
            "snapshot_derived_ofi_5": frame.book_flow_delta,
            "trade_imbalance": frame.trade_imbalance_5s,
            "microprice": float(frame.microprice) if frame.microprice is not None else None,
            "mid_price": float(mark),
            "return_1": (
                frame.trade_return_1s_bps / 10_000
                if frame.trade_return_1s_bps is not None
                else None
            ),
            "book_resilience_proxy": None,
            "trade_arrival_rate": float(frame.trade_count_1s),
            "trend_bps": frame.trade_return_15s_bps,
            "volatility_bps": frame.realized_volatility_15s_bps,
            "spread_bps": frame.spread_bps,
            "top_book_imbalance": frame.top_book_imbalance,
            "total_book_imbalance": frame.total_book_imbalance,
        }
        input_hash = sha256(
            orjson.dumps(frame.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        ).hexdigest()
        features = FeatureSnapshot(
            feature_set="realtime-microstructure",
            feature_version="1",
            market=market,
            event_time_utc=event_time,
            available_at_utc=now,
            computed_at_utc=now,
            values=values,
            input_hash=input_hash,
            quality_flags=frame.quality_warnings,
        )
        regime_values = tuple(
            sorted(
                (name, value)
                for name, value in {
                    "spread_bps": frame.spread_bps,
                    "trend_bps": frame.trade_return_15s_bps,
                    "volatility_bps": frame.realized_volatility_15s_bps,
                }.items()
                if value is not None
            )
        )
        regime = self._regime.predict(
            regime_values,
            market=market,
            predicted_at_utc=now,
            valid_for=timedelta(seconds=self.policy.inference_valid_seconds),
            feature_snapshot_hash=features.snapshot_hash,
        )
        estimated_cost = self._estimated_round_trip_cost(frame)
        alpha = self._alpha_prediction(frame, features, estimated_cost)
        requested_quantity = Decimal("10000") / frame.best_ask
        opposing_quantity = (frame.ask_depth_krw or Decimal(0)) / frame.best_ask
        execution = self._execution.predict(
            market=market,
            predicted_at_utc=now,
            requested_quantity=requested_quantity,
            opposing_depth=opposing_quantity,
            spread_bps=Decimal(str(frame.spread_bps or 0)),
            queue_ahead=Decimal(0),
            latency_ms=self.policy.execution.order_latency_ms,
            maker_fee_bps=self.policy.execution.maker_fee_rate * Decimal(10_000),
            taker_fee_bps=self.policy.execution.taker_fee_rate * Decimal(10_000),
            slippage_bps=self.policy.execution.slippage_buffer_bps,
            adverse_selection_bps=self.policy.execution.adverse_selection_bps,
        )
        portfolio = self._portfolio(market, now)
        drawdown = self._drawdown(market, portfolio.equity)
        limits = self.policy.risk_limits
        daily_loss = max(Decimal(0), -portfolio.net_pnl)
        return StrategyInput(
            decision_at_utc=now,
            market=MarketSnapshot(
                snapshot_id=deterministic_execution_id("realtime-market", frame.frame_id),
                market=market,
                event_time_utc=event_time,
                available_at_utc=now,
                mid_price=mark,
                relative_spread_bps=Decimal(str(frame.spread_bps or 0)),
                bid_depth=frame.bid_depth_krw or Decimal(0),
                ask_depth=frame.ask_depth_krw or Decimal(0),
                market_active=True,
                warning_active="EXCHANGE_CLOCK_AHEAD" in frame.hold_reasons,
                data_gap=not frame.ready_for_inference,
            ),
            features=features,
            regime=regime,
            alpha=alpha,
            execution=execution,
            portfolio=portfolio,
            risk=RiskContext(
                context_id=deterministic_execution_id("realtime-risk-context", frame.frame_id),
                market=market,
                as_of_utc=now,
                trading_mode="paper",
                kill_switch_active=not self.paper_order_simulation_available,
                strategy_paused=False,
                daily_loss_capacity_remaining_krw=max(
                    Decimal(0), limits.max_daily_loss_krw - daily_loss
                ),
                position_capacity_remaining_krw=max(
                    Decimal(0),
                    limits.max_position_notional_per_market - portfolio.market_value,
                ),
                turnover_capacity_remaining_krw=max(
                    Decimal(0), limits.max_turnover_per_day - self._turnover_krw
                ),
                drawdown_pct=drawdown,
            ),
        )

    def _alpha_prediction(
        self,
        frame: RealtimeFeatureFrame,
        features: FeatureSnapshot,
        estimated_cost: Decimal,
    ) -> AlphaPrediction:
        now = frame.available_at_utc
        if self._approval_valid(frame.market, now):
            assert self.alpha_model is not None
            prediction = self.alpha_model.predict(
                frame,
                features,
                predicted_at_utc=now,
                estimated_round_trip_cost_bps=estimated_cost,
            )
            if (
                prediction.market != frame.market
                or prediction.model_version != self.alpha_model.model_version
                or prediction.artifact_hash != self.alpha_model.artifact_hash
                or prediction.feature_snapshot_hash != features.snapshot_hash
                or prediction.predicted_at_utc != now
            ):
                raise RealtimePaperBlocked("approved alpha prediction violates artifact lineage")
            return prediction
        return AlphaPrediction(
            prediction_id=deterministic_execution_id(
                "realtime-neutral-alpha", self._neutral_hash, frame.frame_id
            ),
            market=frame.market,
            predicted_at_utc=now,
            valid_until_utc=now + timedelta(seconds=self.policy.inference_valid_seconds),
            horizon_seconds=self.policy.inference_valid_seconds,
            p_down=0.0,
            p_neutral=1.0,
            p_up=0.0,
            expected_gross_return_bps=Decimal(0),
            estimated_round_trip_cost_bps=estimated_cost,
            expected_net_return_bps=-estimated_cost,
            prediction_interval_bps=(-estimated_cost, estimated_cost),
            uncertainty=0.0,
            confidence=1.0,
            action=DecisionAction.ABSTAIN,
            abstention_reasons=("NO_APPROVED_ALPHA_MODEL",),
            feature_snapshot_hash=features.snapshot_hash,
            model_version=self._neutral.model_version,
            artifact_hash=self._neutral_hash,
        )

    def _risk_snapshot(
        self,
        inputs: StrategyInput,
        selected: StrategyDecision,
        frame: RealtimeFeatureFrame,
    ) -> RiskSnapshot:
        market = inputs.market.market
        now = inputs.decision_at_utc
        self._prune_order_times(now)
        portfolio = inputs.portfolio
        approval_valid = self._approval_valid(market, now)
        approval = self.approval
        model_age = (
            max(0, int((now - approval.model_created_at_utc).total_seconds()))
            if approval_valid and approval is not None
            else self.policy.risk_limits.max_model_age_seconds + 1
        )
        side = selected.side or "bid"
        depth = inputs.market.ask_depth if side == "bid" else inputs.market.bid_depth
        data_age = math.ceil(max(frame.book_age_ms or 0, frame.trade_age_ms or 0))
        clock_skew = math.ceil(abs(min(0.0, frame.ingress_latency_ms)))
        daily_loss = max(Decimal(0), -portfolio.net_pnl)
        drawdown = self._drawdown(market, portfolio.equity)
        open_order = any(order.status not in TERMINAL_STATUSES for order in self._broker.orders)
        return RiskSnapshot(
            snapshot_id=deterministic_execution_id(
                "realtime-risk", selected.decision_id, inputs.market.snapshot_id
            ),
            market=market,
            captured_at_utc=now,
            trading_mode="paper",
            kill_switch_active=not self.paper_order_simulation_available,
            market_active=inputs.market.market_active,
            warning_active=inputs.market.warning_active,
            public_websocket_healthy=not inputs.market.data_gap,
            private_websocket_healthy=False,
            rest_healthy=False,
            data_age_ms=data_age,
            clock_skew_ms=clock_skew,
            balance_age_seconds=0,
            reconciliation_age_seconds=0,
            model_available=self.alpha_model is not None,
            model_release_approved=approval_valid,
            model_age_seconds=model_age,
            features_complete=not inputs.market.data_gap,
            prediction_age_seconds=0,
            prediction_uncertainty=inputs.alpha.uncertainty,
            expected_net_edge_bps=inputs.alpha.expected_net_return_bps,
            relative_spread_bps=inputs.market.relative_spread_bps,
            expected_slippage_bps=inputs.execution.best_slippage_bps,
            opposing_depth_notional=depth,
            reference_price=inputs.market.mid_price,
            position_notional=portfolio.market_value,
            total_exposure_krw=sum(
                (
                    self._portfolio(item, now).market_value
                    for item in self.markets
                    if item in self._latest_marks
                ),
                start=Decimal(0),
            ),
            total_equity_krw=sum(
                (
                    self._portfolio(item, now).equity
                    if item in self._latest_marks
                    else self.policy.initial_cash_krw
                    for item in self.markets
                ),
                start=Decimal(0),
            ),
            concurrent_positions=sum(
                ledger.position_quantity > 0 for ledger in self._ledgers.values()
            ),
            available_cash_krw=portfolio.available_cash,
            locked_cash_krw=portfolio.locked_cash,
            daily_loss_krw=daily_loss,
            daily_loss_pct=(daily_loss / self.policy.initial_cash_krw),
            drawdown_pct=drawdown,
            strategy_loss_krw=daily_loss,
            consecutive_losses=0,
            orders_last_minute=len(self._order_times),
            market_orders_last_minute=len(self._market_order_times[market]),
            turnover_today_krw=self._turnover_krw,
            existing_open_order=open_order,
            identifier_unique=True,
            unknown_orders=0,
            volatility_scale=1.0,
            liquidity_scale=min(1.0, float(depth / Decimal("10000"))) if depth > 0 else 0.0,
            correlation_penalty=0.0,
        )

    def _handle_gateway(
        self,
        market: str,
        intent: OrderIntent,
        decision: RiskDecision,
    ) -> None:
        ledger = self._ledgers[market]
        ledger.record_intent(intent)
        ledger.record_risk_decision(decision)
        self._recovery_dirty = True
        if decision.decision not in {RiskDecisionType.ALLOW, RiskDecisionType.RESIZE}:
            self._risk_rejections += 1
            self._state = RealtimePaperDecisionState.RISK_REJECTED
            self._reason = decision.reason_codes[0]
            self._latest_reason_codes = decision.reason_codes
            return
        self._risk_approvals += 1
        try:
            submitted = self._broker.submit(intent, decision, submitted_at=decision.decided_at)
        except PaperExecutionRejected as exc:
            self._submission_rejections += 1
            self._state = RealtimePaperDecisionState.RISK_REJECTED
            self._reason = type(exc).__name__
            return
        ledger.record_order_update(submitted)
        try:
            ledger.reserve_order(
                submitted.order,
                at=submitted.occurred_at,
                cash_amount=self._broker.reservation_cash(submitted.order),
            )
        except AccountingInvariantError as exc:
            self._submission_rejections += 1
            rejected = self._broker.reject_preflight(
                submitted.order.order_id,
                rejected_at=submitted.occurred_at,
                reason=str(exc),
            )
            ledger.record_order_update(rejected)
            self._state = RealtimePaperDecisionState.RISK_REJECTED
            self._reason = "ACCOUNTING_PREFLIGHT_REJECTED"
            return
        self._paper_orders += 1
        self._order_times.append(submitted.occurred_at)
        self._market_order_times[market].append(submitted.occurred_at)
        self._state = RealtimePaperDecisionState.PAPER_ORDER
        self._reason = decision.decision.value

    def _apply_updates(self, market: str, updates: tuple[PaperExecutionUpdate, ...]) -> int:
        ledger = self._ledgers[market]
        fills = 0
        if updates:
            self._recovery_dirty = True
        for update in updates:
            ledger.record_order_update(update)
            for fill in update.fills:
                ledger.apply_fill(fill)
                self._turnover_krw += fill.notional
                self._paper_fills += 1
                fills += 1
            if update.order.status in TERMINAL_STATUSES:
                ledger.release_order(update.order.order_id, at=update.occurred_at)
        ledger.verify()
        return fills

    def _portfolio(self, market: str, at_utc: datetime) -> PortfolioSnapshot:
        mark = self._latest_marks[market]
        return self._ledgers[market].view(mark_price=mark, as_of=at_utc)

    def _drawdown(self, market: str, equity: Decimal) -> Decimal:
        self._peak_equity[market] = max(self._peak_equity[market], equity)
        peak = self._peak_equity[market]
        return (peak - equity) / peak if peak > 0 and equity < peak else Decimal(0)

    def _restore_checkpoint(self, path: Path) -> None:
        try:
            checkpoint = read_realtime_paper_recovery_checkpoint(path)
            if checkpoint.policy_hash != self.policy.digest:
                raise RealtimePaperBlocked("paper recovery checkpoint policy mismatch")
            if checkpoint.markets != self.markets:
                raise RealtimePaperBlocked("paper recovery checkpoint market mismatch")
            self._broker = PaperBroker.from_state(
                checkpoint.broker,
                policy=self.policy.execution,
                markets=self.markets,
            )
            self._ledgers = {
                state.market: PortfolioLedger.from_state(state) for state in checkpoint.ledgers
            }
            self._latest_marks = dict(checkpoint.latest_marks)
            self._peak_equity = dict(checkpoint.peak_equities)
            self._processed_events = checkpoint.processed_events
            self._feature_ready_frames = checkpoint.feature_ready_frames
            self._inference_frames = checkpoint.inference_frames
            self._strategy_trade_proposals = checkpoint.strategy_trade_proposals
            self._risk_approvals = checkpoint.risk_approvals
            self._risk_rejections = checkpoint.risk_rejections
            self._submission_rejections = checkpoint.submission_rejections
            self._paper_orders = checkpoint.paper_orders
            self._paper_fills = checkpoint.paper_fills
            self._turnover_krw = checkpoint.turnover_krw
            self._first_event_at_utc = checkpoint.first_event_at_utc
            self._last_event_at_utc = checkpoint.last_event_at_utc
            self._last_event_id = checkpoint.last_event_id
            self._order_times = deque(checkpoint.order_times)
            self._market_order_times = {
                market: deque(times) for market, times in checkpoint.market_order_times
            }
            self._state = RealtimePaperDecisionState(checkpoint.decision_state)
            self._reason = checkpoint.decision_reason
            self._latest_strategy_id = checkpoint.latest_strategy_id
            self._latest_reason_codes = checkpoint.latest_reason_codes
            self._loaded_checkpoint = checkpoint
            self._recovery_blocked = checkpoint.recovery_blocked
            self._recovery_checkpoint_hash = checkpoint.checkpoint_hash
        except (
            AccountingInvariantError,
            PaperExecutionRejected,
            PaperRecoveryIntegrityError,
            ValueError,
        ) as exc:
            if isinstance(exc, RealtimePaperBlocked):
                raise
            raise RealtimePaperBlocked("paper recovery checkpoint restore failed") from exc

    def _loaded_checkpoint_is_economically_empty(self) -> bool:
        checkpoint = self._loaded_checkpoint
        if checkpoint is None:
            return True
        return (
            checkpoint.paper_orders == 0
            and checkpoint.paper_fills == 0
            and checkpoint.turnover_krw == 0
            and not checkpoint.broker.orders
            and not checkpoint.broker.fills
            and all(
                ledger.cash_balance == ledger.initial_cash
                and ledger.locked_cash == 0
                and ledger.realized_gross_pnl == 0
                and ledger.cumulative_fees == 0
                and ledger.spread_cost == 0
                and ledger.slippage_cost == 0
                and ledger.adverse_selection_cost == 0
                and not ledger.lots
                and not ledger.records
                and not ledger.reservations
                and not ledger.applied_fill_ids
                for ledger in checkpoint.ledgers
            )
        )

    @staticmethod
    def _require_utc(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise RealtimePaperBlocked("paper recovery timestamp must be UTC-aware")

    def _approval_valid(self, market: str, at_utc: datetime) -> bool:
        return (
            self.approval is not None
            and self.alpha_model is not None
            and self.approval.valid_for(market, at_utc)
            and self.approval.model_version == self.alpha_model.model_version
            and self.approval.artifact_hash == self.alpha_model.artifact_hash
        )

    def _prune_order_times(self, now: datetime) -> None:
        cutoff = now - timedelta(minutes=1)
        while self._order_times and self._order_times[0] <= cutoff:
            self._order_times.popleft()
        for times in self._market_order_times.values():
            while times and times[0] <= cutoff:
                times.popleft()

    def _estimated_round_trip_cost(self, frame: RealtimeFeatureFrame) -> Decimal:
        execution = self.policy.execution
        return (
            Decimal(str(frame.spread_bps or 0))
            + execution.taker_fee_rate * Decimal(20_000)
            + execution.slippage_buffer_bps
            + execution.adverse_selection_bps
        )

    @staticmethod
    def _percentile(values: list[float], ratio: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, math.ceil(len(values) * ratio) - 1)
        return values[index]


def write_realtime_paper_decision_snapshot(
    snapshot: RealtimePaperDecisionSnapshot,
    output_root: Path,
) -> Path:
    payload = snapshot.model_dump(mode="json")
    assert_runtime_export_safe(payload)
    destination_dir = output_root / "ops"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "realtime-paper-decision.json"
    temporary = destination_dir / f".realtime-paper-decision.{uuid4().hex}.tmp"
    encoded = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def read_realtime_paper_decision_snapshot(path: Path) -> RealtimePaperDecisionSnapshot:
    payload = orjson.loads(path.read_bytes())
    assert_runtime_export_safe(payload)
    return RealtimePaperDecisionSnapshot.model_validate(payload)

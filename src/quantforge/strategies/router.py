"""Deterministic edge/priority router; correlated votes are not counted independently."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from quantforge.domain import deterministic_execution_id
from quantforge.strategies.contracts import (
    OrderPreference,
    Strategy,
    StrategyAction,
    StrategyDecision,
    StrategyInput,
    StrategyStatus,
)


class StrategyRouteConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str
    status: StrategyStatus
    priority: int = 0
    correlation_group: str
    capacity_notional: Decimal = Field(gt=0)
    cooldown_seconds: int = Field(ge=0)
    max_strategy_loss: Decimal = Field(ge=0)


class StrategyRoute(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    route_id: UUID
    market: str
    routed_at_utc: datetime
    selected: StrategyDecision
    considered_decision_ids: tuple[UUID, ...]
    rejected_reasons: tuple[tuple[str, str], ...]


class StrategyRouter:
    def __init__(self, configs: tuple[StrategyRouteConfig, ...]) -> None:
        self._configs = {config.strategy_id: config for config in configs}
        if len(self._configs) != len(configs):
            raise ValueError("strategy route configs must be unique")
        self._last_selected: dict[str, datetime] = {}

    def route(
        self,
        inputs: StrategyInput,
        strategies: tuple[Strategy, ...],
        *,
        strategy_losses: dict[str, Decimal] | None = None,
    ) -> StrategyRoute:
        losses = strategy_losses or {}
        decisions: list[StrategyDecision] = []
        rejected: list[tuple[str, str]] = []
        candidates: list[tuple[str, Decimal, int, str, StrategyDecision]] = []
        for strategy in sorted(strategies, key=lambda item: item.strategy_id):
            config = self._configs.get(strategy.strategy_id)
            if config is None:
                rejected.append((strategy.strategy_id, "MISSING_ROUTE_CONFIG"))
                continue
            decision = strategy.evaluate(inputs)
            decisions.append(decision)
            if config.status is not StrategyStatus.ACTIVE:
                rejected.append((strategy.strategy_id, f"STATUS_{config.status}"))
                continue
            if inputs.risk.kill_switch_active:
                rejected.append((strategy.strategy_id, "ROUTER_KILL_SWITCH"))
                continue
            if inputs.risk.strategy_paused:
                rejected.append((strategy.strategy_id, "STRATEGY_PAUSED_BY_RISK"))
                continue
            if losses.get(strategy.strategy_id, Decimal(0)) >= config.max_strategy_loss:
                rejected.append((strategy.strategy_id, "STRATEGY_LOSS_LIMIT"))
                continue
            last = self._last_selected.get(strategy.strategy_id)
            if last is not None and inputs.decision_at_utc < last + timedelta(
                seconds=config.cooldown_seconds
            ):
                rejected.append((strategy.strategy_id, "COOLDOWN"))
                continue
            if decision.action is not StrategyAction.TRADE:
                rejected.append((strategy.strategy_id, decision.reason_codes[0]))
                continue
            requested = decision.target_notional
            if requested is None and decision.target_quantity is not None:
                requested = decision.target_quantity * inputs.market.mid_price
            capacity = min(
                config.capacity_notional,
                inputs.risk.position_capacity_remaining_krw,
                inputs.risk.turnover_capacity_remaining_krw,
                inputs.risk.daily_loss_capacity_remaining_krw,
            )
            if requested is None or requested > capacity:
                rejected.append((strategy.strategy_id, "CAPACITY_EXCEEDED"))
                continue
            candidates.append(
                (
                    config.correlation_group,
                    decision.expected_net_edge_bps,
                    config.priority,
                    strategy.strategy_id,
                    decision,
                )
            )
        if candidates:
            group_winners: list[tuple[str, Decimal, int, str, StrategyDecision]] = []
            for group in sorted({candidate[0] for candidate in candidates}):
                group_candidates = [candidate for candidate in candidates if candidate[0] == group]
                winner = sorted(
                    group_candidates,
                    key=lambda item: (-item[1], -item[2], item[3]),
                )[0]
                group_winners.append(winner)
                rejected.extend(
                    (candidate[3], "CORRELATED_SIGNAL_DEDUPLICATED")
                    for candidate in group_candidates
                    if candidate[3] != winner[3]
                )
            _, _, _, strategy_id, selected = sorted(
                group_winners,
                key=lambda item: (-item[1], -item[2], item[3]),
            )[0]
            self._last_selected[strategy_id] = inputs.decision_at_utc
        else:
            selected = StrategyDecision(
                decision_id=deterministic_execution_id(
                    "strategy-route-hold", inputs.market.snapshot_id, inputs.decision_at_utc
                ),
                action=StrategyAction.HOLD,
                market=inputs.market.market,
                order_preference=OrderPreference.NO_ORDER,
                expected_horizon_seconds=inputs.alpha.horizon_seconds,
                expected_gross_edge_bps=inputs.alpha.expected_gross_return_bps,
                expected_cost_bps=inputs.alpha.estimated_round_trip_cost_bps,
                expected_net_edge_bps=inputs.alpha.expected_net_return_bps,
                confidence=inputs.alpha.confidence,
                uncertainty=inputs.alpha.uncertainty,
                decided_at_utc=inputs.decision_at_utc,
                valid_until_utc=inputs.alpha.valid_until_utc,
                invalidation_conditions=("NEW_INPUT",),
                exit_plan="no position change",
                reason_codes=("NO_ROUTABLE_STRATEGY",),
                strategy_id="strategy-router",
                strategy_version="1.0.0",
            )
        considered = tuple(decision.decision_id for decision in decisions)
        route_id = deterministic_execution_id(
            "strategy-route", inputs.market.snapshot_id, *considered, selected.decision_id
        )
        return StrategyRoute(
            route_id=route_id,
            market=inputs.market.market,
            routed_at_utc=inputs.decision_at_utc,
            selected=selected,
            considered_decision_ids=considered,
            rejected_reasons=tuple(sorted(rejected)),
        )

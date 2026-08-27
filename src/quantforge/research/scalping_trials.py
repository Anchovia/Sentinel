"""Bounded, resumable execution of preregistered short-horizon trials."""

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import EventEnvelope, deterministic_execution_id
from quantforge.research.experiments import (
    ExperimentLedger,
    ExperimentLedgerError,
    ExperimentLedgerSnapshot,
    ExperimentRecordType,
    ExperimentRegistration,
    TrialResult,
    TrialStatus,
    new_experiment_id,
    read_experiment_ledger,
    write_experiment_ledger,
)
from quantforge.research.scalping import (
    ScalpingBacktestEngine,
    ScalpingBacktestResult,
    ScalpingExperimentPlan,
    ScalpingResearchError,
    ScalpingRule,
    ScalpingTrialLimitError,
    evaluate_scalping_data_sufficiency,
)
from quantforge.research.splits import SplitRole
from quantforge.storage import RawEventResearchInventory, read_raw_events

_HYPOTHESIS_RULES = {
    "H-SCALP-001": ScalpingRule.TRADE_CONTINUATION,
    "H-SCALP-002": ScalpingRule.SNAPSHOT_BOOK_PRESSURE,
    "H-SCALP-003": ScalpingRule.CONFIRMED_CONTINUATION,
}
_PLANNED_METRICS = (
    "adverse_selection_cost",
    "average_holding_seconds",
    "closed_trade_count",
    "fees",
    "gross_pnl",
    "maximum_drawdown",
    "median_closed_trade_net_return_bps",
    "net_pnl",
    "non_fill_order_count",
    "slippage_cost",
    "spread_cost",
    "turnover",
    "win_rate",
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScalpingWalkForwardWindow(_FrozenModel):
    fold_id: str = Field(pattern=r"^[1-9][0-9]*$")
    split_role: Literal[SplitRole.VALIDATION, SplitRole.TEST]
    warmup_start_utc: datetime
    entry_start_utc: datetime
    evaluation_end_utc: datetime
    partition_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("warmup_start_utc", "entry_start_utc", "evaluation_end_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("walk-forward timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> "ScalpingWalkForwardWindow":
        if not self.warmup_start_utc < self.entry_start_utc < self.evaluation_end_utc:
            raise ValueError("walk-forward window is empty or reversed")
        return self


class ScalpingTrialSpecification(_FrozenModel):
    trial_id: UUID
    hypothesis_id: str
    rule: ScalpingRule
    cost_scenario: Literal["base", "stress"]
    fold_id: str = Field(pattern=r"^[1-9][0-9]*$")
    split_role: Literal[SplitRole.VALIDATION, SplitRole.TEST]
    partition_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_hypothesis_rule(self) -> "ScalpingTrialSpecification":
        if _HYPOTHESIS_RULES.get(self.hypothesis_id) is not self.rule:
            raise ValueError("trial hypothesis and rule do not match")
        return self


class ScalpingTrialExecutionPlan(_FrozenModel):
    schema_version: Literal["scalping-trial-execution-plan-1"] = "scalping-trial-execution-plan-1"
    experiment_id: UUID
    experiment_name: str
    experiment_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    registration_record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_revision: str = Field(pattern=r"^[a-f0-9]{7,64}$")
    created_at_utc: datetime
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    registered_manifest_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_manifest_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    eligible_markets: tuple[str, ...] = Field(min_length=3)
    selection_start_utc: datetime
    final_holdout_start_utc: datetime
    selection_end_utc: datetime
    windows: tuple[ScalpingWalkForwardWindow, ...] = Field(min_length=1)
    trials: tuple[ScalpingTrialSpecification, ...] = Field(min_length=1)
    maximum_events_per_market: Annotated[int, Field(gt=0)]
    maximum_total_events_per_trial: Annotated[int, Field(gt=0)]
    maximum_elapsed_seconds_per_trial: Annotated[float, Field(gt=0)]
    final_holdout_access: Literal[False] = False
    champion_available: Literal[False] = False
    automatic_promotion: Literal[False] = False
    authentication_used: Literal[False] = False
    private_network_used: Literal[False] = False
    order_network_used: Literal[False] = False
    real_orders_executed: Literal[False] = False
    live_submission_allowed: Literal[False] = False

    @field_validator(
        "created_at_utc",
        "selection_start_utc",
        "final_holdout_start_utc",
        "selection_end_utc",
    )
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("trial execution timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_closed_space(self) -> "ScalpingTrialExecutionPlan":
        if self.eligible_markets != tuple(sorted(set(self.eligible_markets))):
            raise ValueError("eligible markets must be sorted and unique")
        if any(not market.startswith("KRW-") for market in self.eligible_markets):
            raise ValueError("eligible markets must remain in the KRW universe")
        if not (self.selection_start_utc < self.final_holdout_start_utc < self.selection_end_utc):
            raise ValueError("sealed holdout interval is empty or reversed")
        folds = tuple(window.fold_id for window in self.windows)
        if folds != tuple(str(index + 1) for index in range(len(self.windows))):
            raise ValueError("walk-forward folds must be contiguous and ordered")
        window_by_fold = {window.fold_id: window for window in self.windows}
        combinations = tuple(
            (trial.hypothesis_id, trial.cost_scenario, trial.fold_id) for trial in self.trials
        )
        if len(combinations) != len(set(combinations)):
            raise ValueError("trial combinations must be unique")
        if len({trial.trial_id for trial in self.trials}) != len(self.trials):
            raise ValueError("trial identifiers must be unique")
        for trial in self.trials:
            window = window_by_fold.get(trial.fold_id)
            if (
                window is None
                or trial.split_role is not window.split_role
                or trial.partition_hash != window.partition_hash
            ):
                raise ValueError("trial does not match its registered walk-forward window")
        if any(
            window.evaluation_end_utc >= self.final_holdout_start_utc for window in self.windows
        ):
            raise ValueError("walk-forward trial window reaches the sealed final holdout")
        return self

    @property
    def digest(self) -> str:
        payload = orjson.dumps(self.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        return sha256(payload).hexdigest()


class ScalpingTrialAggregate(_FrozenModel):
    signal_count: Annotated[int, Field(ge=0)]
    order_count: Annotated[int, Field(ge=0)]
    fill_count: Annotated[int, Field(ge=0)]
    non_fill_order_count: Annotated[int, Field(ge=0)]
    closed_trade_count: Annotated[int, Field(ge=0)]
    gross_pnl: Decimal
    fees: Decimal = Field(ge=0)
    net_pnl: Decimal
    spread_cost: Decimal = Field(ge=0)
    slippage_cost: Decimal = Field(ge=0)
    adverse_selection_cost: Decimal = Field(ge=0)
    turnover: Decimal = Field(ge=0)
    maximum_drawdown: Decimal = Field(ge=0)
    maximum_drawdown_ratio: Decimal = Field(ge=0)
    win_rate: float | None = Field(default=None, ge=0, le=1)
    average_holding_seconds: float | None = Field(default=None, ge=0)
    median_closed_trade_net_return_bps: Decimal | None = None


class ScalpingTrialArtifact(_FrozenModel):
    schema_version: Literal["scalping-trial-artifact-1"] = "scalping-trial-artifact-1"
    trial_id: UUID
    experiment_id: UUID
    experiment_name: str
    experiment_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_revision: str = Field(pattern=r"^[a-f0-9]{7,64}$")
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    partition_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hypothesis_id: str
    rule: ScalpingRule
    cost_scenario: Literal["base", "stress"]
    fold_id: str
    split_role: Literal[SplitRole.VALIDATION, SplitRole.TEST]
    markets: tuple[str, ...]
    input_event_count: Annotated[int, Field(ge=0)]
    candidate_results: tuple[ScalpingBacktestResult, ...]
    neutral_baseline_results: tuple[ScalpingBacktestResult, ...]
    candidate: ScalpingTrialAggregate
    neutral_baseline: ScalpingTrialAggregate
    champion_comparison_performed: Literal[False] = False
    champion_unavailable_reason: Literal["NO_APPROVED_CHAMPION"] = "NO_APPROVED_CHAMPION"
    final_holdout_used: Literal[False] = False
    authentication_used: Literal[False] = False
    private_network_used: Literal[False] = False
    order_network_used: Literal[False] = False
    real_orders_executed: Literal[False] = False
    live_submission_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_market_results(self) -> "ScalpingTrialArtifact":
        candidate_markets = tuple(item.market for item in self.candidate_results)
        baseline_markets = tuple(item.market for item in self.neutral_baseline_results)
        if candidate_markets != self.markets or baseline_markets != self.markets:
            raise ValueError("trial market results do not match the execution plan")
        if any(item.rule is not self.rule for item in self.candidate_results):
            raise ValueError("candidate result rule does not match its trial")
        if any(
            item.rule is not ScalpingRule.ALWAYS_NEUTRAL for item in self.neutral_baseline_results
        ):
            raise ValueError("trial baseline must remain always neutral")
        if any(
            candidate.dataset_hash != baseline.dataset_hash
            for candidate, baseline in zip(
                self.candidate_results,
                self.neutral_baseline_results,
                strict=True,
            )
        ):
            raise ValueError("candidate and baseline inputs differ")
        return self

    @property
    def digest(self) -> str:
        payload = orjson.dumps(
            self.model_dump(mode="json"),
            default=str,
            option=orjson.OPT_SORT_KEYS,
        )
        return sha256(payload).hexdigest()


type ScalpingTrialEventLoader = Callable[
    [str, ScalpingWalkForwardWindow, int, float], Sequence[EventEnvelope]
]


@dataclass(frozen=True, slots=True)
class ScalpingTrialRunOutcome:
    trial: TrialResult
    artifact_path: Path | None
    ledger_path: Path
    completed_trial_count: int
    planned_trial_count: int


def create_scalping_trial_execution_plan(
    plan: ScalpingExperimentPlan,
    registration_snapshot: ExperimentLedgerSnapshot,
    inventory: RawEventResearchInventory,
    *,
    source_revision: str,
    created_at_utc: datetime,
    maximum_events_per_market: int = 500_000,
    maximum_total_events_per_trial: int = 3_000_000,
    maximum_elapsed_seconds_per_trial: float = 900.0,
) -> ScalpingTrialExecutionPlan:
    """Close the exact 18-trial execution space without reading holdout event content."""

    registration = validate_scalping_trial_registration_seed(plan, registration_snapshot)
    expected_experiment_id = registration.experiment_id
    _validate_registration_contract(plan, registration, inventory)
    if created_at_utc < plan.registered_at_utc:
        raise ScalpingResearchError("trial execution plan predates experiment registration")
    sufficiency = evaluate_scalping_data_sufficiency(plan, inventory)
    if not sufficiency.meets_requirements:
        raise ScalpingResearchError("trial execution plan requires sufficient registered data")
    if inventory.manifest_set_sha256 is None:
        raise ScalpingResearchError("trial execution plan requires manifest lineage")
    if tuple(plan.hypothesis_ids) != tuple(_HYPOTHESIS_RULES):
        raise ScalpingResearchError("trial execution requires the exact registered hypotheses")

    inventory_by_market = {item.market: item for item in inventory.markets}
    eligible_markets = tuple(sorted(sufficiency.eligible_markets))
    selection_start = max(
        inventory_by_market[market].first_received_at_utc for market in eligible_markets
    )
    selection_end = min(
        inventory_by_market[market].last_received_at_utc for market in eligible_markets
    )
    if plan.dataset_selection.maximum_received_at_utc is not None:
        selection_end = min(selection_end, plan.dataset_selection.maximum_received_at_utc)
    total_microseconds = int((selection_end - selection_start) / timedelta(microseconds=1))
    development_microseconds = int(
        Decimal(total_microseconds) * (Decimal(1) - plan.dataset_selection.final_holdout_fraction)
    )
    block_microseconds = development_microseconds // (plan.validation.walk_forward_folds + 1)
    if block_microseconds <= 0:
        raise ScalpingResearchError("registered data span cannot form chronological folds")
    final_holdout_start = selection_start + timedelta(microseconds=development_microseconds)

    windows: list[ScalpingWalkForwardWindow] = []
    for index in range(1, plan.validation.walk_forward_folds + 1):
        entry_start = selection_start + timedelta(
            microseconds=block_microseconds * index,
            seconds=plan.availability_and_leakage.embargo_seconds,
        )
        evaluation_end = selection_start + timedelta(
            microseconds=block_microseconds * (index + 1),
            seconds=-plan.availability_and_leakage.purge_seconds,
        )
        warmup_start = entry_start - timedelta(
            seconds=plan.availability_and_leakage.feature_warmup_seconds
        )
        split_role = (
            SplitRole.TEST if index == plan.validation.walk_forward_folds else SplitRole.VALIDATION
        )
        partition_payload = {
            "dataset_hash": inventory.dataset_hash,
            "eligible_markets": eligible_markets,
            "fold_id": str(index),
            "split_role": split_role,
            "warmup_start_utc": warmup_start,
            "entry_start_utc": entry_start,
            "evaluation_end_utc": evaluation_end,
            "purge_seconds": plan.availability_and_leakage.purge_seconds,
            "embargo_seconds": plan.availability_and_leakage.embargo_seconds,
        }
        partition_hash = sha256(
            orjson.dumps(
                partition_payload,
                default=str,
                option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
            )
        ).hexdigest()
        windows.append(
            ScalpingWalkForwardWindow(
                fold_id=str(index),
                split_role=split_role,
                warmup_start_utc=warmup_start,
                entry_start_utc=entry_start,
                evaluation_end_utc=evaluation_end,
                partition_hash=partition_hash,
            )
        )

    trials = tuple(
        ScalpingTrialSpecification(
            trial_id=deterministic_execution_id(
                "scalping-trial",
                expected_experiment_id,
                hypothesis_id,
                cost_scenario,
                window.fold_id,
                window.partition_hash,
            ),
            hypothesis_id=hypothesis_id,
            rule=_HYPOTHESIS_RULES[hypothesis_id],
            cost_scenario=cost_scenario,
            fold_id=window.fold_id,
            split_role=window.split_role,
            partition_hash=window.partition_hash,
        )
        for hypothesis_id in plan.hypothesis_ids
        for cost_scenario in sorted(plan.cost_scenarios)
        for window in windows
    )
    if len(trials) != plan.validation.planned_trial_count:
        raise ScalpingResearchError("execution trial count differs from preregistration")
    registered_manifest = plan.dataset_selection.manifest_set_sha256
    return ScalpingTrialExecutionPlan(
        experiment_id=expected_experiment_id,
        experiment_name=plan.experiment_id,
        experiment_plan_sha256=plan.digest,
        registration_record_hash=registration_snapshot.records[0].record_hash,
        source_revision=source_revision,
        created_at_utc=created_at_utc,
        dataset_hash=inventory.dataset_hash,
        registered_manifest_set_sha256=registered_manifest,
        observed_manifest_set_sha256=inventory.manifest_set_sha256,
        eligible_markets=eligible_markets,
        selection_start_utc=selection_start,
        final_holdout_start_utc=final_holdout_start,
        selection_end_utc=selection_end,
        windows=tuple(windows),
        trials=trials,
        maximum_events_per_market=maximum_events_per_market,
        maximum_total_events_per_trial=maximum_total_events_per_trial,
        maximum_elapsed_seconds_per_trial=maximum_elapsed_seconds_per_trial,
    )


def validate_scalping_trial_registration_seed(
    plan: ScalpingExperimentPlan,
    registration_snapshot: ExperimentLedgerSnapshot,
) -> ExperimentRegistration:
    """Fail fast when a seed ledger cannot authorize the declared trial computation."""

    ledger = ExperimentLedger.from_snapshot(registration_snapshot)
    if len(registration_snapshot.records) != 1 or (
        registration_snapshot.records[0].record_type is not ExperimentRecordType.REGISTRATION
    ):
        raise ScalpingResearchError("trial planning requires a registration-only seed ledger")
    payload = ExperimentRegistration.model_validate_json(
        registration_snapshot.records[0].payload_json
    )
    expected_experiment_id = new_experiment_id(
        plan.experiment_id,
        payload.dataset_hash,
        plan.registered_at_utc,
    )
    registration = ledger.registration_for(expected_experiment_id)
    expected_parameters = (
        ("cost_scenario", tuple(sorted(plan.cost_scenarios))),
        (
            "fold",
            tuple(str(index + 1) for index in range(plan.validation.walk_forward_folds)),
        ),
        ("hypothesis", plan.hypothesis_ids),
    )
    expected_splits = (SplitRole.VALIDATION, SplitRole.TEST, SplitRole.FINAL_HOLDOUT)
    if registration.feature_set != plan.feature_and_entry_rules.feature_contract:
        raise ScalpingResearchError("registered feature contract does not match the plan")
    if registration.hyperparameter_space != expected_parameters:
        raise ScalpingResearchError("registered hyperparameter space does not match the plan")
    if registration.planned_splits != expected_splits or not registration.final_holdout_planned:
        raise ScalpingResearchError("registered split contract does not match the plan")
    if registration.planned_metrics != _PLANNED_METRICS:
        raise ScalpingResearchError("registered metrics do not cover the experiment plan")
    if f"plan_sha256={plan.digest}" not in registration.planned_cost_model:
        raise ScalpingResearchError("registered cost model is not bound to the experiment plan")
    return registration


def write_scalping_trial_execution_plan(
    plan: ScalpingTrialExecutionPlan,
    destination: Path,
) -> Path:
    payload = (
        orjson.dumps(
            plan.model_dump(mode="json"),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ScalpingResearchError("existing trial execution plan is immutable")
        return destination
    _atomic_bytes(destination, payload)
    return destination


def load_scalping_trial_execution_plan(source: Path) -> ScalpingTrialExecutionPlan:
    return ScalpingTrialExecutionPlan.model_validate_json(source.read_bytes())


def run_next_scalping_trial(
    plan: ScalpingExperimentPlan,
    execution_plan: ScalpingTrialExecutionPlan,
    registration_snapshot: ExperimentLedgerSnapshot,
    *,
    working_ledger_path: Path,
    artifact_root: Path,
    input_root: Path | None = None,
    event_loader: ScalpingTrialEventLoader | None = None,
) -> ScalpingTrialRunOutcome:
    """Execute and durably retain exactly the next unrecorded non-holdout trial."""

    _validate_execution_plan(plan, execution_plan, registration_snapshot)
    if working_ledger_path.exists():
        current_snapshot = read_experiment_ledger(working_ledger_path)
    else:
        current_snapshot = registration_snapshot
    if not current_snapshot.records or (
        current_snapshot.records[0].record_hash != execution_plan.registration_record_hash
    ):
        raise ExperimentLedgerError("working ledger does not descend from the registration seed")
    if any(
        record.record_type is ExperimentRecordType.HOLDOUT_ACCESS
        for record in current_snapshot.records
    ):
        raise ScalpingResearchError("bounded trial runner refuses a ledger with holdout access")
    if any(
        record.record_type is ExperimentRecordType.DECISION for record in current_snapshot.records
    ):
        raise ScalpingResearchError("bounded trial runner refuses a closed experiment ledger")

    ledger = ExperimentLedger.from_snapshot(current_snapshot)
    registration = ledger.registration_for(execution_plan.experiment_id)
    recorded_trials = ledger.trials_for(execution_plan.experiment_id)
    recorded_ids = tuple(item.trial_id for item in recorded_trials)
    planned_ids = tuple(item.trial_id for item in execution_plan.trials)
    if recorded_ids != planned_ids[: len(recorded_ids)]:
        raise ExperimentLedgerError("working ledger does not follow registered trial order")
    if len(recorded_trials) == len(execution_plan.trials):
        raise ScalpingResearchError("all preregistered trials are already retained")
    specification = execution_plan.trials[len(recorded_trials)]
    window = next(item for item in execution_plan.windows if item.fold_id == specification.fold_id)

    if event_loader is None:
        if input_root is None:
            raise ValueError("filesystem trial execution requires an input root")
        event_loader = _raw_event_loader(plan, input_root)
    elif input_root is not None:
        raise ValueError("trial execution accepts either an input root or an event loader")

    wall_started_at = datetime.now(UTC)
    timer_started_at = monotonic()
    artifact_path: Path | None = None
    try:
        candidate_results: list[ScalpingBacktestResult] = []
        baseline_results: list[ScalpingBacktestResult] = []
        input_event_count = 0
        for market in execution_plan.eligible_markets:
            events = tuple(
                event_loader(
                    market,
                    window,
                    execution_plan.maximum_events_per_market,
                    _remaining_seconds(execution_plan, timer_started_at),
                )
            )
            _validate_loaded_events(plan, execution_plan, window, market, events)
            input_event_count += len(events)
            if input_event_count > execution_plan.maximum_total_events_per_trial:
                raise ScalpingTrialLimitError(
                    "trial input exceeds the registered total-event limit"
                )
            candidate = ScalpingBacktestEngine(
                plan,
                market=market,
                rule=specification.rule,
                cost_scenario=specification.cost_scenario,
                fold_id=specification.fold_id,
                code_version=execution_plan.source_revision,
                entry_start_utc=window.entry_start_utc,
            ).run(
                events,
                maximum_events=execution_plan.maximum_events_per_market,
                maximum_elapsed_seconds=_remaining_seconds(execution_plan, timer_started_at),
            )
            baseline = ScalpingBacktestEngine(
                plan,
                market=market,
                rule=ScalpingRule.ALWAYS_NEUTRAL,
                cost_scenario=specification.cost_scenario,
                fold_id=specification.fold_id,
                code_version=execution_plan.source_revision,
                entry_start_utc=window.entry_start_utc,
            ).run(
                events,
                maximum_events=execution_plan.maximum_events_per_market,
                maximum_elapsed_seconds=_remaining_seconds(execution_plan, timer_started_at),
            )
            candidate_results.append(candidate)
            baseline_results.append(baseline)

        artifact = ScalpingTrialArtifact(
            trial_id=specification.trial_id,
            experiment_id=execution_plan.experiment_id,
            experiment_name=execution_plan.experiment_name,
            experiment_plan_sha256=execution_plan.experiment_plan_sha256,
            execution_plan_sha256=execution_plan.digest,
            source_revision=execution_plan.source_revision,
            dataset_hash=execution_plan.dataset_hash,
            partition_hash=specification.partition_hash,
            hypothesis_id=specification.hypothesis_id,
            rule=specification.rule,
            cost_scenario=specification.cost_scenario,
            fold_id=specification.fold_id,
            split_role=specification.split_role,
            markets=execution_plan.eligible_markets,
            input_event_count=input_event_count,
            candidate_results=tuple(candidate_results),
            neutral_baseline_results=tuple(baseline_results),
            candidate=_aggregate_results(candidate_results),
            neutral_baseline=_aggregate_results(baseline_results),
        )
        _remaining_seconds(execution_plan, timer_started_at)
        artifact_path = (
            artifact_root / execution_plan.experiment_name / (f"{specification.trial_id}.json")
        )
        _write_trial_artifact(artifact, artifact_path)
        trial = TrialResult(
            trial_id=specification.trial_id,
            experiment_id=execution_plan.experiment_id,
            started_at_utc=wall_started_at,
            ended_at_utc=datetime.now(UTC),
            random_seed=plan.validation.random_seed,
            split_role=specification.split_role,
            split_hash=specification.partition_hash,
            hyperparameters=_trial_hyperparameters(specification),
            metrics=_trial_metrics(artifact.candidate),
            status=TrialStatus.SUCCEEDED,
            artifact_hash=artifact.digest,
            holdout_used=False,
        )
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"[:1_000]
        trial = TrialResult(
            trial_id=specification.trial_id,
            experiment_id=execution_plan.experiment_id,
            started_at_utc=wall_started_at,
            ended_at_utc=datetime.now(UTC),
            random_seed=plan.validation.random_seed,
            split_role=specification.split_role,
            split_hash=specification.partition_hash,
            hyperparameters=_trial_hyperparameters(specification),
            metrics=(),
            status=TrialStatus.FAILED,
            failure_reason=failure,
            artifact_hash=None,
            holdout_used=False,
        )

    if trial.started_at_utc < registration.created_at_utc:
        raise ExperimentLedgerError("trial execution predates its registration")
    ledger.record_trial(trial)
    write_experiment_ledger(ledger.snapshot(), working_ledger_path)
    return ScalpingTrialRunOutcome(
        trial=trial,
        artifact_path=artifact_path,
        ledger_path=working_ledger_path,
        completed_trial_count=len(recorded_trials) + 1,
        planned_trial_count=len(execution_plan.trials),
    )


def _validate_registration_contract(
    plan: ScalpingExperimentPlan,
    registration: ExperimentRegistration,
    inventory: RawEventResearchInventory,
) -> None:
    if registration.dataset_hash != inventory.dataset_hash:
        raise ScalpingResearchError("registered dataset hash does not match the inventory")
    selection = plan.dataset_selection
    if (
        inventory.maximum_exchange_timestamp_utc != selection.maximum_exchange_timestamp_utc
        or inventory.maximum_received_at_utc != selection.maximum_received_at_utc
        or inventory.exclude_marked_duplicates != selection.exclude_marked_duplicates
        or inventory.exclude_quality_flagged_events != selection.exclude_quality_flagged_events
    ):
        raise ScalpingResearchError("inventory selection does not match the experiment plan")


def _validate_execution_plan(
    plan: ScalpingExperimentPlan,
    execution_plan: ScalpingTrialExecutionPlan,
    registration_snapshot: ExperimentLedgerSnapshot,
) -> None:
    if execution_plan.experiment_name != plan.experiment_id:
        raise ScalpingResearchError("execution plan names a different experiment")
    if execution_plan.experiment_plan_sha256 != plan.digest:
        raise ScalpingResearchError("execution plan hash does not match the experiment plan")
    if not registration_snapshot.records or (
        execution_plan.registration_record_hash != registration_snapshot.records[0].record_hash
    ):
        raise ScalpingResearchError("execution plan does not match the registration seed")
    if len(execution_plan.trials) != plan.validation.planned_trial_count:
        raise ScalpingResearchError("execution plan trial count does not match registration")
    if execution_plan.created_at_utc < plan.registered_at_utc:
        raise ScalpingResearchError("execution plan predates experiment registration")
    registration = validate_scalping_trial_registration_seed(plan, registration_snapshot)
    if registration.experiment_id != execution_plan.experiment_id:
        raise ScalpingResearchError("execution plan uses a different experiment identifier")
    if registration.dataset_hash != execution_plan.dataset_hash:
        raise ScalpingResearchError("execution dataset hash differs from registration")


def _raw_event_loader(
    plan: ScalpingExperimentPlan,
    input_root: Path,
) -> ScalpingTrialEventLoader:
    def load(
        market: str,
        window: ScalpingWalkForwardWindow,
        maximum_events: int,
        maximum_elapsed_seconds: float,
    ) -> Sequence[EventEnvelope]:
        return read_raw_events(
            input_root,
            markets=frozenset({market}),
            event_types=frozenset({"trade", "orderbook"}),
            maximum_exchange_timestamp_utc=(plan.dataset_selection.maximum_exchange_timestamp_utc),
            minimum_received_at_utc=window.warmup_start_utc,
            maximum_received_at_utc=window.evaluation_end_utc,
            exclude_marked_duplicates=plan.dataset_selection.exclude_marked_duplicates,
            exclude_quality_flagged_events=(plan.dataset_selection.exclude_quality_flagged_events),
            maximum_events=maximum_events,
            maximum_elapsed_seconds=maximum_elapsed_seconds,
        )

    return load


def _validate_loaded_events(
    plan: ScalpingExperimentPlan,
    execution_plan: ScalpingTrialExecutionPlan,
    window: ScalpingWalkForwardWindow,
    market: str,
    events: Sequence[EventEnvelope],
) -> None:
    if not events:
        raise ScalpingResearchError(f"trial market has no events: {market}")
    if len(events) > execution_plan.maximum_events_per_market:
        raise ScalpingTrialLimitError("trial market exceeds its registered event limit")
    if any(item.market != market for item in events):
        raise ScalpingResearchError("trial loader returned a different market")
    if any(
        item.received_at_utc < window.warmup_start_utc
        or item.received_at_utc > window.evaluation_end_utc
        for item in events
    ):
        raise ScalpingResearchError("trial loader crossed its availability window")
    if any(
        item.exchange_timestamp > plan.dataset_selection.maximum_exchange_timestamp_utc
        for item in events
    ):
        raise ScalpingResearchError("trial loader crossed its exchange-time cutoff")
    if plan.dataset_selection.exclude_marked_duplicates and any(
        item.is_duplicate for item in events
    ):
        raise ScalpingResearchError("trial loader included a marked duplicate")
    if plan.dataset_selection.exclude_quality_flagged_events and any(
        item.quality_flags for item in events
    ):
        raise ScalpingResearchError("trial loader included a quality-flagged event")


def _remaining_seconds(
    execution_plan: ScalpingTrialExecutionPlan,
    started_at: float,
) -> float:
    remaining = execution_plan.maximum_elapsed_seconds_per_trial - (monotonic() - started_at)
    if remaining <= 0:
        raise ScalpingTrialLimitError("trial exceeded its registered wall-time limit")
    return remaining


def _aggregate_results(results: Sequence[ScalpingBacktestResult]) -> ScalpingTrialAggregate:
    trades = tuple(trade for result in results for trade in result.trades)
    return ScalpingTrialAggregate(
        signal_count=sum(item.signal_count for item in results),
        order_count=sum(item.order_count for item in results),
        fill_count=sum(item.fill_count for item in results),
        non_fill_order_count=sum(item.non_fill_order_count for item in results),
        closed_trade_count=len(trades),
        gross_pnl=sum((item.gross_pnl for item in results), start=Decimal(0)),
        fees=sum((item.fees for item in results), start=Decimal(0)),
        net_pnl=sum((item.net_pnl for item in results), start=Decimal(0)),
        spread_cost=sum((item.spread_cost for item in results), start=Decimal(0)),
        slippage_cost=sum((item.slippage_cost for item in results), start=Decimal(0)),
        adverse_selection_cost=sum(
            (item.adverse_selection_cost for item in results), start=Decimal(0)
        ),
        turnover=sum((item.turnover for item in results), start=Decimal(0)),
        maximum_drawdown=sum((item.maximum_drawdown for item in results), start=Decimal(0)),
        maximum_drawdown_ratio=max(
            (item.maximum_drawdown_ratio for item in results), default=Decimal(0)
        ),
        win_rate=(sum(trade.net_pnl > 0 for trade in trades) / len(trades) if trades else None),
        average_holding_seconds=(
            sum(trade.holding_seconds for trade in trades) / len(trades) if trades else None
        ),
        median_closed_trade_net_return_bps=(
            median(trade.net_return_bps for trade in trades) if trades else None
        ),
    )


def _trial_metrics(aggregate: ScalpingTrialAggregate) -> tuple[tuple[str, float], ...]:
    values: dict[str, float] = {
        "adverse_selection_cost": float(aggregate.adverse_selection_cost),
        "closed_trade_count": float(aggregate.closed_trade_count),
        "fees": float(aggregate.fees),
        "gross_pnl": float(aggregate.gross_pnl),
        "maximum_drawdown": float(aggregate.maximum_drawdown),
        "net_pnl": float(aggregate.net_pnl),
        "non_fill_order_count": float(aggregate.non_fill_order_count),
        "slippage_cost": float(aggregate.slippage_cost),
        "spread_cost": float(aggregate.spread_cost),
        "turnover": float(aggregate.turnover),
    }
    if aggregate.average_holding_seconds is not None:
        values["average_holding_seconds"] = aggregate.average_holding_seconds
    if aggregate.median_closed_trade_net_return_bps is not None:
        values["median_closed_trade_net_return_bps"] = float(
            aggregate.median_closed_trade_net_return_bps
        )
    if aggregate.win_rate is not None:
        values["win_rate"] = aggregate.win_rate
    return tuple(sorted(values.items()))


def _trial_hyperparameters(
    specification: ScalpingTrialSpecification,
) -> tuple[tuple[str, str], ...]:
    return (
        ("cost_scenario", specification.cost_scenario),
        ("fold", specification.fold_id),
        ("hypothesis", specification.hypothesis_id),
    )


def _write_trial_artifact(artifact: ScalpingTrialArtifact, destination: Path) -> None:
    payload = (
        orjson.dumps(
            artifact.model_dump(mode="json"),
            default=str,
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ScalpingResearchError("existing trial artifact differs from deterministic output")
        return
    _atomic_bytes(destination, payload)


def _atomic_bytes(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

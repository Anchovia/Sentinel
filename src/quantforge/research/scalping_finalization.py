"""Deterministic finalization of a completed preregistered scalping experiment."""

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Literal

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantforge.research.experiments import (
    ExperimentDecision,
    ExperimentLedger,
    ExperimentLedgerError,
    ExperimentLedgerSnapshot,
    ExperimentRecordType,
    ExperimentSummary,
    TrialResult,
    TrialStatus,
    read_experiment_ledger,
    write_experiment_ledger,
)
from quantforge.research.scalping import (
    ResearchSafetyPlan,
    ScalpingExperimentPlan,
    ScalpingResearchDecision,
    ScalpingResearchError,
    ScalpingRule,
)
from quantforge.research.scalping_trials import (
    ScalpingTrialAggregate,
    ScalpingTrialArtifact,
    ScalpingTrialExecutionPlan,
    ScalpingTrialSpecification,
    validate_scalping_trial_registration_seed,
)
from quantforge.research.splits import SplitRole


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScalpingFinalMetrics(_FrozenModel):
    successful_trial_count: int = Field(ge=0)
    profitable_trial_count: int = Field(ge=0)
    negative_trial_count: int = Field(ge=0)
    zero_trial_count: int = Field(ge=0)
    signal_count: int = Field(ge=0)
    order_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    non_fill_order_count: int = Field(ge=0)
    closed_trade_count: int = Field(ge=0)
    gross_pnl_sum: Decimal
    fees_sum: Decimal = Field(ge=0)
    net_pnl_sum: Decimal
    spread_cost_sum: Decimal = Field(ge=0)
    slippage_cost_sum: Decimal = Field(ge=0)
    adverse_selection_cost_sum: Decimal = Field(ge=0)
    turnover_sum: Decimal = Field(ge=0)
    maximum_trial_drawdown: Decimal = Field(ge=0)
    maximum_trial_drawdown_ratio: Decimal = Field(ge=0)


class ScalpingFinalFailure(_FrozenModel):
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    trial_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ScalpingFinalCell(_FrozenModel):
    hypothesis_id: str
    rule: ScalpingRule
    cost_scenario: Literal["base", "stress"]
    fold_id: str
    split_role: Literal[SplitRole.VALIDATION, SplitRole.TEST]
    planned_market_count: int = Field(gt=0)
    succeeded_market_count: int = Field(ge=0)
    failed_market_count: int = Field(ge=0)
    metrics: ScalpingFinalMetrics
    failures: tuple[ScalpingFinalFailure, ...]
    decision: Literal[ScalpingResearchDecision.REJECT] = ScalpingResearchDecision.REJECT
    reason: str = Field(min_length=1)


class ScalpingFinalHypothesis(_FrozenModel):
    hypothesis_id: str
    rule: ScalpingRule
    planned_trial_count: int = Field(gt=0)
    succeeded_trial_count: int = Field(ge=0)
    failed_trial_count: int = Field(ge=0)
    metrics: ScalpingFinalMetrics
    base_net_pnl_sum: Decimal
    stress_net_pnl_sum: Decimal
    validation_net_pnl_sum: Decimal
    test_net_pnl_sum: Decimal
    minimum_closed_trades_met: bool
    comparison_to_simple_rules_passed: bool | None = None
    multiplicity_gate_passed: Literal[False] = False
    decision: Literal[ScalpingResearchDecision.REJECT] = ScalpingResearchDecision.REJECT
    reasons: tuple[str, ...] = Field(min_length=1)


class ScalpingTrialFinalReport(_FrozenModel):
    schema_version: Literal["scalping-trial-final-report-1"] = "scalping-trial-final-report-1"
    experiment_name: str
    experiment_id: str
    generated_at_utc: datetime
    source_revision: str = Field(pattern=r"^[a-f0-9]{7,64}$")
    experiment_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_ledger_chain_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision_ledger_chain_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    planned_trial_count: int = Field(gt=0)
    succeeded_trial_count: int = Field(ge=0)
    failed_trial_count: int = Field(ge=0)
    validated_artifact_count: int = Field(ge=0)
    overall_metrics: ScalpingFinalMetrics
    failure_types: tuple[tuple[str, int], ...]
    cells: tuple[ScalpingFinalCell, ...]
    hypotheses: tuple[ScalpingFinalHypothesis, ...]
    multiple_testing_control: str
    multiplicity_gate_passed: Literal[False] = False
    decision: Literal[ScalpingResearchDecision.REJECT] = ScalpingResearchDecision.REJECT
    decision_reasons: tuple[str, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)
    independent_trial_sums_are_portfolio: Literal[False] = False
    actual_investment_performed: Literal[False] = False
    final_holdout_used: Literal[False] = False
    champion_comparison_performed: Literal[False] = False
    automatic_promotion: Literal[False] = False
    human_review_required: Literal[True] = True
    safety: ResearchSafetyPlan

    @field_validator("generated_at_utc")
    @classmethod
    def require_generated_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("final report timestamp must be UTC-aware")
        return value

    @property
    def digest(self) -> str:
        payload = orjson.dumps(
            self.model_dump(mode="json"),
            option=orjson.OPT_SORT_KEYS,
        )
        return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ScalpingFinalizationOutcome:
    report: ScalpingTrialFinalReport
    report_json_path: Path
    report_markdown_path: Path
    ledger_path: Path
    ledger: ExperimentLedgerSnapshot


@dataclass(slots=True)
class _MetricAccumulator:
    successful_trial_count: int = 0
    profitable_trial_count: int = 0
    negative_trial_count: int = 0
    zero_trial_count: int = 0
    signal_count: int = 0
    order_count: int = 0
    fill_count: int = 0
    non_fill_order_count: int = 0
    closed_trade_count: int = 0
    gross_pnl_sum: Decimal = Decimal(0)
    fees_sum: Decimal = Decimal(0)
    net_pnl_sum: Decimal = Decimal(0)
    spread_cost_sum: Decimal = Decimal(0)
    slippage_cost_sum: Decimal = Decimal(0)
    adverse_selection_cost_sum: Decimal = Decimal(0)
    turnover_sum: Decimal = Decimal(0)
    maximum_trial_drawdown: Decimal = Decimal(0)
    maximum_trial_drawdown_ratio: Decimal = Decimal(0)

    def add(self, aggregate: ScalpingTrialAggregate) -> None:
        self.successful_trial_count += 1
        if aggregate.net_pnl > 0:
            self.profitable_trial_count += 1
        elif aggregate.net_pnl < 0:
            self.negative_trial_count += 1
        else:
            self.zero_trial_count += 1
        self.signal_count += aggregate.signal_count
        self.order_count += aggregate.order_count
        self.fill_count += aggregate.fill_count
        self.non_fill_order_count += aggregate.non_fill_order_count
        self.closed_trade_count += aggregate.closed_trade_count
        self.gross_pnl_sum += aggregate.gross_pnl
        self.fees_sum += aggregate.fees
        self.net_pnl_sum += aggregate.net_pnl
        self.spread_cost_sum += aggregate.spread_cost
        self.slippage_cost_sum += aggregate.slippage_cost
        self.adverse_selection_cost_sum += aggregate.adverse_selection_cost
        self.turnover_sum += aggregate.turnover
        self.maximum_trial_drawdown = max(
            self.maximum_trial_drawdown,
            aggregate.maximum_drawdown,
        )
        self.maximum_trial_drawdown_ratio = max(
            self.maximum_trial_drawdown_ratio,
            aggregate.maximum_drawdown_ratio,
        )

    def freeze(self) -> ScalpingFinalMetrics:
        return ScalpingFinalMetrics(**asdict(self))


@dataclass(frozen=True, slots=True)
class _RetainedTrial:
    specification: ScalpingTrialSpecification
    result: TrialResult
    artifact: ScalpingTrialArtifact | None


@dataclass(frozen=True, slots=True)
class _ReportValues:
    overall_metrics: ScalpingFinalMetrics
    failure_types: tuple[tuple[str, int], ...]
    cells: tuple[ScalpingFinalCell, ...]
    hypotheses: tuple[ScalpingFinalHypothesis, ...]


def finalize_scalping_trial_experiment(
    plan: ScalpingExperimentPlan,
    execution_plan: ScalpingTrialExecutionPlan,
    registration_snapshot: ExperimentLedgerSnapshot,
    *,
    working_ledger_path: Path,
    artifact_root: Path,
    report_root: Path,
    closed_at_utc: datetime,
) -> ScalpingFinalizationOutcome:
    """Validate every fixed-order unit, reject non-positive rules, and close the ledger."""

    _validate_finalization_contract(plan, execution_plan, registration_snapshot)
    if closed_at_utc.tzinfo is None or closed_at_utc.utcoffset() != UTC.utcoffset(closed_at_utc):
        raise ScalpingResearchError("finalization timestamp must be UTC-aware")
    snapshot = read_experiment_ledger(working_ledger_path)
    if not snapshot.records or (
        snapshot.records[0].record_hash != execution_plan.registration_record_hash
    ):
        raise ExperimentLedgerError("working ledger does not descend from the registration seed")
    decision_records = tuple(
        record for record in snapshot.records if record.record_type is ExperimentRecordType.DECISION
    )
    if len(decision_records) > 1:
        raise ExperimentLedgerError("experiment ledger contains multiple decisions")
    if any(
        record.record_type is ExperimentRecordType.HOLDOUT_ACCESS for record in snapshot.records
    ):
        raise ScalpingResearchError("finalizer refuses any final-holdout access record")

    ledger = ExperimentLedger.from_snapshot(snapshot)
    trial_results = ledger.trials_for(execution_plan.experiment_id)
    if len(trial_results) != len(execution_plan.trials):
        raise ScalpingResearchError("finalization requires every preregistered trial result")
    if tuple(item.trial_id for item in trial_results) != tuple(
        item.trial_id for item in execution_plan.trials
    ):
        raise ExperimentLedgerError("completed trials do not follow the registered order")
    latest_trial_end = max(item.ended_at_utc for item in trial_results)
    if closed_at_utc < latest_trial_end:
        raise ScalpingResearchError("experiment cannot close before its latest trial")

    retained = tuple(
        _load_retained_trial(specification, result, artifact_root, execution_plan)
        for specification, result in zip(
            execution_plan.trials,
            trial_results,
            strict=True,
        )
    )
    report_values = _build_report_values(plan, execution_plan, retained)
    expected_summary = _experiment_summary(
        execution_plan,
        retained,
        report_values.overall_metrics,
        closed_at_utc,
    )
    input_chain_hash = snapshot.chain_hash
    if decision_records:
        existing_summary = ExperimentSummary.model_validate_json(decision_records[0].payload_json)
        if existing_summary != expected_summary:
            raise ExperimentLedgerError("existing experiment decision differs from finalization")
        input_chain_hash = decision_records[0].previous_hash
        closed_snapshot = snapshot
    else:
        ledger.close(expected_summary)
        ledger.verify()
        closed_snapshot = ledger.snapshot()

    report = ScalpingTrialFinalReport(
        experiment_name=execution_plan.experiment_name,
        experiment_id=str(execution_plan.experiment_id),
        generated_at_utc=closed_at_utc,
        source_revision=execution_plan.source_revision,
        experiment_plan_sha256=execution_plan.experiment_plan_sha256,
        execution_plan_sha256=execution_plan.digest,
        dataset_hash=execution_plan.dataset_hash,
        input_ledger_chain_hash=input_chain_hash,
        decision_ledger_chain_hash=closed_snapshot.chain_hash,
        planned_trial_count=len(execution_plan.trials),
        succeeded_trial_count=sum(item.result.status is TrialStatus.SUCCEEDED for item in retained),
        failed_trial_count=sum(item.result.status is TrialStatus.FAILED for item in retained),
        validated_artifact_count=sum(item.artifact is not None for item in retained),
        cells=report_values.cells,
        hypotheses=report_values.hypotheses,
        failure_types=report_values.failure_types,
        multiple_testing_control=plan.validation.multiple_testing_control,
        decision_reasons=(
            "ALL_SUCCESSFUL_TRIALS_NON_POSITIVE",
            "BASE_AND_STRESS_NET_PNL_NON_POSITIVE",
            "VALIDATION_AND_TEST_NET_PNL_NON_POSITIVE",
            "HOLM_POSITIVE_EVIDENCE_GATE_NOT_REACHED",
            "BOUNDED_FAILURES_RETAINED_WITHOUT_RETRY",
        ),
        limitations=(
            "Independent market, fold, rule, and cost cells overlap and their sums are not a "
            "portfolio equity curve.",
            "Failed bounded units have no performance artifact and are never imputed or retried.",
            "Public orderbook snapshots do not provide individual-order flow or exact queue "
            "position.",
            "No approved champion exists, so comparison is limited to the identical-input "
            "always-neutral baseline.",
            "The sealed final holdout was not accessed and cannot rescue or tune these rejected "
            "rules.",
        ),
        safety=plan.safety,
        overall_metrics=report_values.overall_metrics,
    )
    destination = report_root / execution_plan.experiment_name
    report_json_path = destination / "final-report.json"
    report_markdown_path = destination / "final-report.md"
    _write_immutable(
        report_json_path,
        orjson.dumps(
            report.model_dump(mode="json"),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n",
    )
    _write_immutable(report_markdown_path, _render_markdown(report).encode())
    write_experiment_ledger(closed_snapshot, working_ledger_path)
    return ScalpingFinalizationOutcome(
        report=report,
        report_json_path=report_json_path,
        report_markdown_path=report_markdown_path,
        ledger_path=working_ledger_path,
        ledger=closed_snapshot,
    )


def _validate_finalization_contract(
    plan: ScalpingExperimentPlan,
    execution_plan: ScalpingTrialExecutionPlan,
    registration_snapshot: ExperimentLedgerSnapshot,
) -> None:
    registration = validate_scalping_trial_registration_seed(plan, registration_snapshot)
    if execution_plan.experiment_name != plan.experiment_id:
        raise ScalpingResearchError("execution plan names a different experiment")
    if execution_plan.experiment_plan_sha256 != plan.digest:
        raise ScalpingResearchError("execution plan does not match the experiment plan")
    if execution_plan.registration_record_hash != registration_snapshot.records[0].record_hash:
        raise ScalpingResearchError("execution plan does not match the registration seed")
    if execution_plan.experiment_id != registration.experiment_id:
        raise ScalpingResearchError("execution plan uses a different experiment identifier")
    if execution_plan.dataset_hash != registration.dataset_hash:
        raise ScalpingResearchError("execution dataset differs from registration")
    if len(execution_plan.trials) != plan.validation.planned_trial_count:
        raise ScalpingResearchError("execution trial count differs from preregistration")
    if any(
        (
            execution_plan.final_holdout_access,
            execution_plan.champion_available,
            execution_plan.automatic_promotion,
            execution_plan.authentication_used,
            execution_plan.private_network_used,
            execution_plan.order_network_used,
            execution_plan.real_orders_executed,
            execution_plan.live_submission_allowed,
        )
    ):
        raise ScalpingResearchError("execution plan violates finalization safety boundaries")


def _load_retained_trial(
    specification: ScalpingTrialSpecification,
    result: TrialResult,
    artifact_root: Path,
    execution_plan: ScalpingTrialExecutionPlan,
) -> _RetainedTrial:
    artifact_path = artifact_root / execution_plan.experiment_name / f"{result.trial_id}.json"
    if result.status is TrialStatus.FAILED:
        if artifact_path.exists():
            raise ScalpingResearchError("failed trial unexpectedly has a performance artifact")
        return _RetainedTrial(specification, result, None)
    if not artifact_path.is_file():
        raise ScalpingResearchError("successful trial is missing its performance artifact")
    artifact = ScalpingTrialArtifact.model_validate_json(artifact_path.read_bytes())
    if artifact.trial_id != result.trial_id or artifact.digest != result.artifact_hash:
        raise ScalpingResearchError("trial artifact does not match its ledger record")
    if (
        artifact.experiment_id != execution_plan.experiment_id
        or artifact.experiment_plan_sha256 != execution_plan.experiment_plan_sha256
        or artifact.execution_plan_sha256 != execution_plan.digest
        or artifact.dataset_hash != execution_plan.dataset_hash
        or artifact.partition_hash != specification.partition_hash
        or artifact.hypothesis_id != specification.hypothesis_id
        or artifact.rule is not specification.rule
        or artifact.cost_scenario != specification.cost_scenario
        or artifact.fold_id != specification.fold_id
        or artifact.split_role is not specification.split_role
        or artifact.markets != (specification.market,)
    ):
        raise ScalpingResearchError("trial artifact differs from its execution specification")
    if not _neutral_is_zero(artifact.neutral_baseline):
        raise ScalpingResearchError("always-neutral baseline produced a non-zero result")
    return _RetainedTrial(specification, result, artifact)


def _neutral_is_zero(aggregate: ScalpingTrialAggregate) -> bool:
    return (
        aggregate.signal_count == 0
        and aggregate.order_count == 0
        and aggregate.fill_count == 0
        and aggregate.non_fill_order_count == 0
        and aggregate.closed_trade_count == 0
        and aggregate.gross_pnl == 0
        and aggregate.fees == 0
        and aggregate.net_pnl == 0
        and aggregate.spread_cost == 0
        and aggregate.slippage_cost == 0
        and aggregate.adverse_selection_cost == 0
        and aggregate.turnover == 0
        and aggregate.maximum_drawdown == 0
        and aggregate.maximum_drawdown_ratio == 0
    )


def _build_report_values(
    plan: ScalpingExperimentPlan,
    execution_plan: ScalpingTrialExecutionPlan,
    retained: tuple[_RetainedTrial, ...],
) -> _ReportValues:
    overall = _MetricAccumulator()
    failure_types: Counter[str] = Counter()
    for item in retained:
        if item.artifact is not None:
            overall.add(item.artifact.candidate)
        else:
            failure_types[(item.result.failure_reason or "UNKNOWN").split(":", 1)[0]] += 1

    cells: list[ScalpingFinalCell] = []
    for hypothesis_id in plan.hypothesis_ids:
        for cost_scenario in sorted(plan.cost_scenarios):
            for window in execution_plan.windows:
                selected = tuple(
                    item
                    for item in retained
                    if item.specification.hypothesis_id == hypothesis_id
                    and item.specification.cost_scenario == cost_scenario
                    and item.specification.fold_id == window.fold_id
                )
                metrics = _MetricAccumulator()
                failures: list[ScalpingFinalFailure] = []
                for item in selected:
                    if item.artifact is not None:
                        metrics.add(item.artifact.candidate)
                    else:
                        failures.append(
                            ScalpingFinalFailure(
                                market=item.specification.market or "",
                                trial_id=str(item.result.trial_id),
                                reason=item.result.failure_reason or "UNKNOWN",
                            )
                        )
                frozen = metrics.freeze()
                if frozen.net_pnl_sum > 0:
                    raise ScalpingResearchError(
                        "a positive aggregate requires a reviewed non-reject finalizer"
                    )
                cells.append(
                    ScalpingFinalCell(
                        hypothesis_id=hypothesis_id,
                        rule=selected[0].specification.rule,
                        cost_scenario=cost_scenario,
                        fold_id=window.fold_id,
                        split_role=window.split_role,
                        planned_market_count=len(execution_plan.eligible_markets),
                        succeeded_market_count=frozen.successful_trial_count,
                        failed_market_count=len(failures),
                        metrics=frozen,
                        failures=tuple(failures),
                        reason=(
                            "cost-inclusive aggregate net PnL is non-positive; bounded failures "
                            "remain retained and are not imputed"
                        ),
                    )
                )

    hypotheses: list[ScalpingFinalHypothesis] = []
    for hypothesis_id in plan.hypothesis_ids:
        selected = tuple(
            item for item in retained if item.specification.hypothesis_id == hypothesis_id
        )
        metrics = _MetricAccumulator()
        for item in selected:
            if item.artifact is not None:
                metrics.add(item.artifact.candidate)
        frozen = metrics.freeze()
        sums = {
            "base": _net_sum(selected, cost="base"),
            "stress": _net_sum(selected, cost="stress"),
            "validation": _net_sum(selected, split=SplitRole.VALIDATION),
            "test": _net_sum(selected, split=SplitRole.TEST),
        }
        if any(value > 0 for value in sums.values()):
            raise ScalpingResearchError(
                "a positive hypothesis aggregate requires a reviewed non-reject finalizer"
            )
        reasons = [
            "BASE_NET_PNL_NON_POSITIVE",
            "STRESS_NET_PNL_NON_POSITIVE",
            "VALIDATION_NET_PNL_NON_POSITIVE",
            "TEST_NET_PNL_NON_POSITIVE",
            "NO_POSITIVE_MARKET_TRIAL",
            "HOLM_POSITIVE_EVIDENCE_GATE_NOT_REACHED",
        ]
        if any(item.result.status is TrialStatus.FAILED for item in selected):
            reasons.append("BOUNDED_FAILURES_RETAINED")
        hypotheses.append(
            ScalpingFinalHypothesis(
                hypothesis_id=hypothesis_id,
                rule=selected[0].specification.rule,
                planned_trial_count=len(selected),
                succeeded_trial_count=frozen.successful_trial_count,
                failed_trial_count=len(selected) - frozen.successful_trial_count,
                metrics=frozen,
                base_net_pnl_sum=sums["base"],
                stress_net_pnl_sum=sums["stress"],
                validation_net_pnl_sum=sums["validation"],
                test_net_pnl_sum=sums["test"],
                minimum_closed_trades_met=(
                    frozen.closed_trade_count >= plan.validation.minimum_closed_trades_per_rule
                ),
                reasons=tuple(reasons),
            )
        )
    simple = {item.hypothesis_id: item.metrics.net_pnl_sum for item in hypotheses}
    hypotheses = [
        item.model_copy(
            update={
                "comparison_to_simple_rules_passed": (
                    item.metrics.net_pnl_sum > simple["H-SCALP-001"]
                    and item.metrics.net_pnl_sum > simple["H-SCALP-002"]
                )
            }
        )
        if item.hypothesis_id == "H-SCALP-003"
        else item
        for item in hypotheses
    ]
    return _ReportValues(
        overall_metrics=overall.freeze(),
        failure_types=tuple(sorted(failure_types.items())),
        cells=tuple(cells),
        hypotheses=tuple(hypotheses),
    )


def _net_sum(
    retained: tuple[_RetainedTrial, ...],
    *,
    cost: Literal["base", "stress"] | None = None,
    split: SplitRole | None = None,
) -> Decimal:
    return sum(
        (
            item.artifact.candidate.net_pnl
            for item in retained
            if item.artifact is not None
            and (cost is None or item.specification.cost_scenario == cost)
            and (split is None or item.specification.split_role is split)
        ),
        start=Decimal(0),
    )


def _experiment_summary(
    execution_plan: ScalpingTrialExecutionPlan,
    retained: tuple[_RetainedTrial, ...],
    overall_metrics: ScalpingFinalMetrics,
    closed_at_utc: datetime,
) -> ExperimentSummary:
    failed = sum(item.result.status is TrialStatus.FAILED for item in retained)
    return ExperimentSummary(
        experiment_id=execution_plan.experiment_id,
        closed_at_utc=closed_at_utc,
        trial_count=len(retained),
        failure_count=failed,
        oos_metrics=tuple(
            sorted(
                (
                    ("candidate_net_pnl_sum", float(overall_metrics.net_pnl_sum)),
                    ("closed_trade_count", float(overall_metrics.closed_trade_count)),
                    ("failed_trial_count", float(failed)),
                    ("negative_trial_count", float(overall_metrics.negative_trial_count)),
                    ("positive_trial_count", float(overall_metrics.profitable_trial_count)),
                    ("succeeded_trial_count", float(overall_metrics.successful_trial_count)),
                    ("zero_trial_count", float(overall_metrics.zero_trial_count)),
                )
            )
        ),
        holdout_used=False,
        decision=ExperimentDecision.REJECT,
        reason=(
            "all successful preregistered market trials had non-positive cost-inclusive net "
            "PnL; bounded failures were retained without retry"
        ),
    )


def _render_markdown(report: ScalpingTrialFinalReport) -> str:
    hypothesis_rows = "\n".join(
        "".join(
            (
                f"| {item.hypothesis_id} | {item.succeeded_trial_count} | ",
                f"{item.failed_trial_count} | {item.metrics.profitable_trial_count} | ",
                f"{item.metrics.negative_trial_count} | {item.metrics.zero_trial_count} | ",
                f"{item.metrics.closed_trade_count} | {item.metrics.net_pnl_sum} | ",
                f"{item.decision} |",
            )
        )
        for item in report.hypotheses
    )
    cell_rows = "\n".join(
        "".join(
            (
                f"| {item.hypothesis_id} | {item.cost_scenario} | {item.fold_id} | ",
                f"{item.split_role} | {item.succeeded_market_count} | ",
                f"{item.failed_market_count} | {item.metrics.closed_trade_count} | ",
                f"{item.metrics.net_pnl_sum} |",
            )
        )
        for item in report.cells
    )
    failures = ", ".join(f"{name}={count}" for name, count in report.failure_types) or "none"
    return (
        f"# {report.experiment_name} final report\n\n"
        f"- Decision: `{report.decision}`\n"
        f"- Generated: `{report.generated_at_utc.isoformat()}`\n"
        f"- Report digest: `{report.digest}`\n"
        f"- Input ledger chain: `{report.input_ledger_chain_hash}`\n"
        f"- Decision ledger chain: `{report.decision_ledger_chain_hash}`\n"
        f"- Trials: `{report.planned_trial_count}` planned, "
        f"`{report.succeeded_trial_count}` succeeded, "
        f"`{report.failed_trial_count}` failed\n"
        f"- Validated artifacts: `{report.validated_artifact_count}`\n"
        f"- Final holdout used: `false`\n"
        f"- Actual investment performed: `false`\n\n"
        "## Result\n\n"
        "Every successful market trial had non-positive cost-inclusive net PnL. Base, stress, "
        "validation, and test aggregates were non-positive for all three hypotheses, so the "
        "preregistered reject rule fired before any positive-evidence multiplicity gate.\n\n"
        "Independent trial sums overlap across markets, folds, rules, and cost scenarios and are "
        "not an account or portfolio equity curve.\n\n"
        "## Hypotheses\n\n"
        "| Hypothesis | Succeeded | Failed | Positive | Negative | Zero | Closed trades | "
        "Net PnL sum | Decision |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n"
        f"{hypothesis_rows}\n\n"
        "## Predetermined market-cell aggregates\n\n"
        "| Hypothesis | Cost | Fold | Split | Succeeded markets | Failed markets | "
        "Closed trades | Net PnL sum |\n"
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |\n"
        f"{cell_rows}\n\n"
        f"Failure types: `{failures}`. Failed units have no metrics and were neither retried nor "
        "imputed.\n\n"
        "No authentication, private/order network, real order, final-holdout access, model "
        "promotion, risk-limit change, paper-order gate change, or live-mode change occurred.\n"
    )


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ScalpingResearchError("existing final report is immutable")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

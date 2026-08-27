from datetime import timedelta
from pathlib import Path

import orjson
import pytest
from pydantic import ValidationError

from factories import BASE_TIME, make_orderbook_event, make_trade_event
from quantforge.domain import EventEnvelope
from quantforge.research import (
    ExperimentLedger,
    ExperimentLedgerSnapshot,
    ExperimentRegistration,
    SplitRole,
    TrialStatus,
    new_experiment_id,
    read_experiment_ledger,
)
from quantforge.research.scalping import (
    ScalpingExperimentPlan,
    ScalpingResearchError,
    ScalpingTrialLimitError,
    load_scalping_experiment_plan,
)
from quantforge.research.scalping_trials import (
    ScalpingTrialExecutionPlan,
    ScalpingWalkForwardWindow,
    create_scalping_trial_execution_plan,
    load_scalping_trial_execution_plan,
    run_next_scalping_trial,
    validate_scalping_trial_registration_seed,
    write_scalping_trial_execution_plan,
)
from quantforge.storage import RawEventMarketInventory, RawEventResearchInventory

ROOT = Path(__file__).parents[2]
V2_PLAN_PATH = ROOT / "research" / "experiments" / "2026-08-27-scalping-challenger-v2.json"
V2_LEDGER_PATH = V2_PLAN_PATH.with_suffix(".ledger.json")
V3_PLAN_PATH = V2_PLAN_PATH.with_name("2026-08-27-scalping-challenger-v3.json")
V3_LEDGER_PATH = V3_PLAN_PATH.with_suffix(".ledger.json")
V3_EXECUTION_PATH = V3_PLAN_PATH.with_suffix(".execution.json")
V4_PLAN_PATH = V3_PLAN_PATH.with_name("2026-08-28-scalping-challenger-v4.json")
V4_LEDGER_PATH = V4_PLAN_PATH.with_suffix(".ledger.json")
V4_EXECUTION_PATH = V4_PLAN_PATH.with_suffix(".execution.json")
DATASET_HASH = "a" * 64
MANIFEST_HASH = "b" * 64
SOURCE_REVISION = "2" * 40
PLANNED_METRICS = (
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


def _plan() -> ScalpingExperimentPlan:
    original = load_scalping_experiment_plan(V2_PLAN_PATH)
    cutoff = BASE_TIME + timedelta(hours=24)
    selection = original.dataset_selection.model_copy(
        update={
            "manifest_set_sha256": MANIFEST_HASH,
            "maximum_exchange_timestamp_utc": cutoff,
            "maximum_received_at_utc": cutoff,
        }
    )
    return original.model_copy(
        update={
            "experiment_id": "qf-scalp-test-v3",
            "registered_at_utc": cutoff + timedelta(minutes=1),
            "source_revision": "1" * 40,
            "dataset_selection": selection,
        }
    )


def _inventory(plan: ScalpingExperimentPlan) -> RawEventResearchInventory:
    markets = tuple(
        RawEventMarketInventory(
            market=f"KRW-T{index}",
            trade_events=20_000,
            orderbook_events=20_000,
            first_received_at_utc=BASE_TIME,
            last_received_at_utc=BASE_TIME + timedelta(hours=24),
        )
        for index in range(3)
    )
    return RawEventResearchInventory(
        dataset_hash=DATASET_HASH,
        manifest_set_sha256=MANIFEST_HASH,
        maximum_exchange_timestamp_utc=(plan.dataset_selection.maximum_exchange_timestamp_utc),
        maximum_received_at_utc=plan.dataset_selection.maximum_received_at_utc,
        exclude_marked_duplicates=True,
        exclude_quality_flagged_events=True,
        selected_file_count=6,
        selected_event_count=120_000,
        markets=markets,
    )


def _registration_snapshot(
    plan: ScalpingExperimentPlan,
    inventory: RawEventResearchInventory,
    *,
    planned_metrics: tuple[str, ...] = PLANNED_METRICS,
    market_partitioned: bool = False,
) -> ExperimentLedgerSnapshot:
    hyperparameter_space = (
        ("cost_scenario", ("base", "stress")),
        ("fold", ("1", "2", "3")),
        ("hypothesis", plan.hypothesis_ids),
    )
    if market_partitioned:
        hyperparameter_space = (
            *hyperparameter_space,
            ("market", tuple(item.market for item in inventory.markets)),
        )
    registration = ExperimentRegistration(
        experiment_id=new_experiment_id(
            plan.experiment_id,
            inventory.dataset_hash,
            plan.registered_at_utc,
        ),
        hypothesis_id="+".join(plan.hypothesis_ids),
        created_at_utc=plan.registered_at_utc,
        researcher=plan.researcher,
        code_version=plan.source_revision,
        dataset_hash=inventory.dataset_hash,
        feature_set=plan.feature_and_entry_rules.feature_contract,
        label_version="cost-inclusive-round-trip-v1",
        model_family="preregistered-deterministic-rules",
        hyperparameter_space=hyperparameter_space,
        planned_metrics=planned_metrics,
        planned_splits=(SplitRole.VALIDATION, SplitRole.TEST, SplitRole.FINAL_HOLDOUT),
        planned_cost_model=f"conservative_l2 base and stress; plan_sha256={plan.digest}",
        final_holdout_planned=True,
    )
    ledger = ExperimentLedger()
    ledger.preregister(registration)
    return ledger.snapshot()


def _execution_fixture() -> tuple[
    ScalpingExperimentPlan,
    ExperimentLedgerSnapshot,
    ScalpingTrialExecutionPlan,
]:
    plan = _plan()
    inventory = _inventory(plan)
    registration = _registration_snapshot(plan, inventory)
    execution = create_scalping_trial_execution_plan(
        plan,
        registration,
        inventory,
        source_revision=SOURCE_REVISION,
        created_at_utc=plan.registered_at_utc + timedelta(minutes=1),
        maximum_events_per_market=100,
        maximum_total_events_per_trial=300,
        maximum_elapsed_seconds_per_trial=30,
    )
    return plan, registration, execution


def _market_partitioned_execution_fixture() -> tuple[
    ScalpingExperimentPlan,
    ExperimentLedgerSnapshot,
    ScalpingTrialExecutionPlan,
]:
    plan = _plan()
    plan = plan.model_copy(
        update={"validation": plan.validation.model_copy(update={"planned_trial_count": 54})}
    )
    inventory = _inventory(plan)
    registration = _registration_snapshot(plan, inventory, market_partitioned=True)
    execution = create_scalping_trial_execution_plan(
        plan,
        registration,
        inventory,
        source_revision=SOURCE_REVISION,
        created_at_utc=plan.registered_at_utc + timedelta(minutes=1),
        maximum_events_per_market=100,
        maximum_elapsed_seconds_per_trial=30,
    )
    return plan, registration, execution


def _event_loader(
    market: str,
    window: ScalpingWalkForwardWindow,
    maximum_events: int,
    maximum_elapsed_seconds: float,
) -> tuple[EventEnvelope, ...]:
    assert maximum_events == 100
    assert maximum_elapsed_seconds > 0
    events = (
        make_orderbook_event(sequence=1, received_offset_ms=0, market=market),
        make_trade_event(
            sequence=2,
            exchange_offset_ms=100,
            received_offset_ms=100,
            market=market,
        ),
        make_orderbook_event(sequence=3, received_offset_ms=200, market=market),
    )
    offset = window.entry_start_utc - BASE_TIME
    return tuple(
        event.model_copy(
            update={
                "exchange_timestamp": event.exchange_timestamp + offset,
                "received_at_utc": event.received_at_utc + offset,
            }
        )
        for event in events
    )


def test_execution_plan_closes_exact_non_holdout_trial_space() -> None:
    plan, registration, execution = _execution_fixture()
    repeated = create_scalping_trial_execution_plan(
        plan,
        registration,
        _inventory(plan),
        source_revision=SOURCE_REVISION,
        created_at_utc=plan.registered_at_utc + timedelta(minutes=1),
        maximum_events_per_market=100,
        maximum_total_events_per_trial=300,
        maximum_elapsed_seconds_per_trial=30,
    )

    assert execution == repeated
    assert len(execution.trials) == 18
    assert len({trial.trial_id for trial in execution.trials}) == 18
    assert sum(trial.split_role is SplitRole.VALIDATION for trial in execution.trials) == 12
    assert sum(trial.split_role is SplitRole.TEST for trial in execution.trials) == 6
    assert all(
        window.evaluation_end_utc < execution.final_holdout_start_utc
        for window in execution.windows
    )
    assert execution.final_holdout_access is False


def test_market_partitioned_plan_closes_one_market_per_work_unit() -> None:
    _, _, execution = _market_partitioned_execution_fixture()

    assert execution.schema_version == "scalping-trial-execution-plan-2"
    assert len(execution.trials) == 54
    assert len({trial.trial_id for trial in execution.trials}) == 54
    assert sum(trial.split_role is SplitRole.VALIDATION for trial in execution.trials) == 36
    assert sum(trial.split_role is SplitRole.TEST for trial in execution.trials) == 18
    assert {trial.market for trial in execution.trials} == set(execution.eligible_markets)
    assert execution.maximum_total_events_per_trial == 100


def test_market_partitioned_runner_checkpoints_exactly_one_market(tmp_path: Path) -> None:
    plan, registration, execution = _market_partitioned_execution_fixture()
    loaded_markets: list[str] = []

    def record_loader(
        market: str,
        window: ScalpingWalkForwardWindow,
        maximum_events: int,
        maximum_elapsed_seconds: float,
    ) -> tuple[EventEnvelope, ...]:
        loaded_markets.append(market)
        return _event_loader(market, window, maximum_events, maximum_elapsed_seconds)

    outcome = run_next_scalping_trial(
        plan,
        execution,
        registration,
        working_ledger_path=tmp_path / "ledger.json",
        artifact_root=tmp_path / "artifacts",
        event_loader=record_loader,
    )

    assert outcome.trial.status is TrialStatus.SUCCEEDED
    assert loaded_markets == [execution.trials[0].market]
    assert outcome.trial.hyperparameters[-1] == ("market", execution.trials[0].market)
    assert outcome.artifact_path is not None
    artifact = orjson.loads(outcome.artifact_path.read_bytes())
    assert artifact["markets"] == loaded_markets


def test_execution_plan_rejects_incomplete_v2_metric_registration() -> None:
    plan = load_scalping_experiment_plan(V2_PLAN_PATH)
    inventory = RawEventResearchInventory(
        dataset_hash="4002405439cbe4afbedf64ea90a84be486640754a0a2de12a4d726760dae8fd6",
        manifest_set_sha256=plan.dataset_selection.manifest_set_sha256,
        maximum_exchange_timestamp_utc=plan.dataset_selection.maximum_exchange_timestamp_utc,
        maximum_received_at_utc=plan.dataset_selection.maximum_received_at_utc,
        exclude_marked_duplicates=True,
        exclude_quality_flagged_events=True,
        selected_file_count=6,
        selected_event_count=120_000,
        markets=tuple(
            RawEventMarketInventory(
                market=f"KRW-T{index}",
                trade_events=20_000,
                orderbook_events=20_000,
                first_received_at_utc=BASE_TIME,
                last_received_at_utc=BASE_TIME + timedelta(hours=24),
            )
            for index in range(3)
        ),
    )
    registration = ExperimentLedgerSnapshot.model_validate_json(V2_LEDGER_PATH.read_bytes())

    with pytest.raises(ScalpingResearchError, match="metrics"):
        create_scalping_trial_execution_plan(
            plan,
            registration,
            inventory,
            source_revision=SOURCE_REVISION,
            created_at_utc=plan.registered_at_utc + timedelta(minutes=1),
        )


def test_v3_registration_is_metric_complete_and_bound_to_runner_revision() -> None:
    plan = load_scalping_experiment_plan(V3_PLAN_PATH)
    registration = read_experiment_ledger(V3_LEDGER_PATH)

    payload = validate_scalping_trial_registration_seed(plan, registration)

    assert plan.source_revision == "a2e2593f9d2c598a5f7e1051e5f85cf8e770b264"
    assert plan.digest == "453f6e913ccb9d2e4c7df28d1e44edd250b336e89c6b6f3d66fb032bb5e29516"
    assert payload.planned_metrics == PLANNED_METRICS
    assert len(registration.records) == 1


def test_v4_registration_closes_exact_market_partition_space() -> None:
    plan = load_scalping_experiment_plan(V4_PLAN_PATH)
    registration = read_experiment_ledger(V4_LEDGER_PATH)

    payload = validate_scalping_trial_registration_seed(plan, registration)
    parameter_map = dict(payload.hyperparameter_space)

    assert plan.source_revision == "2f9672973905a785eb0e10a8903b4b521a848185"
    assert plan.digest == "8d3a5fe1bcd5f22b16c0bc8fc7a93b8e2390581dc37eca068cf96a79b97057ee"
    assert plan.validation.planned_trial_count == 270
    assert len(parameter_map["market"]) == 15
    assert payload.planned_metrics == PLANNED_METRICS
    assert registration.chain_hash == (
        "8a1827182eecb96abd9306773ad5cc3c39fc28c3582090895c459ae53ba6678f"
    )
    assert len(registration.records) == 1


def test_committed_v3_execution_plan_seals_exact_non_holdout_work_units(
    tmp_path: Path,
) -> None:
    plan = load_scalping_experiment_plan(V3_PLAN_PATH)
    registration = read_experiment_ledger(V3_LEDGER_PATH)
    execution = load_scalping_trial_execution_plan(V3_EXECUTION_PATH)

    assert execution.digest == "c692a59d9704a0a8e9fd4ccd587a3f4c0d6a2a7a42ef85f0e3e6b5a24ca3122a"
    assert execution.experiment_plan_sha256 == plan.digest
    assert execution.registration_record_hash == registration.records[0].record_hash
    assert execution.source_revision == plan.source_revision
    assert len(execution.eligible_markets) == 15
    assert len(execution.trials) == 18
    assert sum(trial.split_role is SplitRole.VALIDATION for trial in execution.trials) == 12
    assert sum(trial.split_role is SplitRole.TEST for trial in execution.trials) == 6
    assert all(
        window.evaluation_end_utc < execution.final_holdout_start_utc
        for window in execution.windows
    )
    assert execution.final_holdout_access is False
    repeated_path = tmp_path / V3_EXECUTION_PATH.name
    write_scalping_trial_execution_plan(execution, repeated_path)
    assert repeated_path.read_bytes() == V3_EXECUTION_PATH.read_bytes()


def test_committed_v4_execution_plan_seals_market_work_units() -> None:
    plan = load_scalping_experiment_plan(V4_PLAN_PATH)
    registration = read_experiment_ledger(V4_LEDGER_PATH)
    execution = load_scalping_trial_execution_plan(V4_EXECUTION_PATH)

    assert execution.schema_version == "scalping-trial-execution-plan-2"
    assert execution.digest == "b4d60606d0ac6234c97f847fd0311322c857d0eb5d05ff77e9fa2a3db2564446"
    assert execution.experiment_plan_sha256 == plan.digest
    assert execution.registration_record_hash == registration.records[0].record_hash
    assert execution.source_revision == plan.source_revision
    assert execution.observed_manifest_set_sha256 == (
        "524e3cc94c207191c3a93394fc91c44bd5410566fd64db49ee92f5029cc19101"
    )
    assert len(execution.eligible_markets) == 15
    assert len(execution.trials) == 270
    assert sum(trial.split_role is SplitRole.VALIDATION for trial in execution.trials) == 180
    assert sum(trial.split_role is SplitRole.TEST for trial in execution.trials) == 90
    assert all(trial.market in execution.eligible_markets for trial in execution.trials)
    assert execution.maximum_events_per_market == 500_000
    assert execution.maximum_total_events_per_trial == 500_000
    assert execution.maximum_elapsed_seconds_per_trial == 900
    assert execution.final_holdout_access is False


def test_runner_records_one_trial_at_a_time_with_neutral_baseline(tmp_path: Path) -> None:
    plan, registration, execution = _execution_fixture()
    working_ledger = tmp_path / "ledger.json"
    artifact_root = tmp_path / "artifacts"

    first = run_next_scalping_trial(
        plan,
        execution,
        registration,
        working_ledger_path=working_ledger,
        artifact_root=artifact_root,
        event_loader=_event_loader,
    )
    second = run_next_scalping_trial(
        plan,
        execution,
        registration,
        working_ledger_path=working_ledger,
        artifact_root=artifact_root,
        event_loader=_event_loader,
    )
    snapshot = read_experiment_ledger(working_ledger)
    assert first.artifact_path is not None
    first_artifact = orjson.loads(first.artifact_path.read_bytes())

    assert first.trial.status is TrialStatus.SUCCEEDED
    assert second.trial.status is TrialStatus.SUCCEEDED
    assert first.trial.trial_id != second.trial.trial_id
    assert len(snapshot.records) == 3
    assert first_artifact["final_holdout_used"] is False
    assert first_artifact["champion_comparison_performed"] is False
    assert all(
        result["rule"] == "always_neutral" for result in first_artifact["neutral_baseline_results"]
    )
    assert first.completed_trial_count == 1
    assert second.completed_trial_count == 2


def test_runner_retains_failed_trial_and_advances_without_retry(tmp_path: Path) -> None:
    plan, registration, execution = _execution_fixture()
    working_ledger = tmp_path / "failed-ledger.json"

    def fail_loader(
        market: str,
        window: ScalpingWalkForwardWindow,
        maximum_events: int,
        maximum_elapsed_seconds: float,
    ) -> tuple[EventEnvelope, ...]:
        del market, window, maximum_events, maximum_elapsed_seconds
        raise ScalpingTrialLimitError("synthetic bounded failure")

    failed = run_next_scalping_trial(
        plan,
        execution,
        registration,
        working_ledger_path=working_ledger,
        artifact_root=tmp_path / "artifacts",
        event_loader=fail_loader,
    )
    recovered = run_next_scalping_trial(
        plan,
        execution,
        registration,
        working_ledger_path=working_ledger,
        artifact_root=tmp_path / "artifacts",
        event_loader=_event_loader,
    )

    assert failed.trial.status is TrialStatus.FAILED
    assert "synthetic bounded failure" in (failed.trial.failure_reason or "")
    assert failed.artifact_path is None
    assert recovered.trial.trial_id != failed.trial.trial_id
    assert recovered.completed_trial_count == 2


def test_execution_contract_rejects_any_final_holdout_trial() -> None:
    _, _, execution = _execution_fixture()
    payload = execution.model_dump(mode="json")
    payload["trials"][0]["split_role"] = "final_holdout"

    with pytest.raises(ValidationError):
        ScalpingTrialExecutionPlan.model_validate(payload)

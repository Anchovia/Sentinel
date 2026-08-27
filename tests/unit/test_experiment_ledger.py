from datetime import timedelta
from pathlib import Path
from uuid import UUID

import orjson
import pytest

from factories import BASE_TIME
from quantforge.research import (
    ExperimentDecision,
    ExperimentLedger,
    ExperimentLedgerError,
    ExperimentRegistration,
    ExperimentSummary,
    SplitRole,
    TrialResult,
    TrialStatus,
    new_experiment_id,
    read_experiment_ledger,
    write_experiment_ledger,
)

DATASET_HASH = "d" * 64


def _registration(*, holdout: bool = False) -> ExperimentRegistration:
    experiment_id = new_experiment_id("H-001", DATASET_HASH, BASE_TIME)
    splits = (SplitRole.TRAIN, SplitRole.VALIDATION, SplitRole.TEST)
    if holdout:
        splits = (*splits, SplitRole.FINAL_HOLDOUT)
    return ExperimentRegistration(
        experiment_id=experiment_id,
        hypothesis_id="H-001",
        created_at_utc=BASE_TIME,
        researcher="quantforge-test",
        code_version="phase4-test",
        dataset_hash=DATASET_HASH,
        feature_set="phase4-fixture",
        label_version="alpha-1s-v1",
        model_family="logistic_alpha",
        hyperparameter_space=(("learning_rate", ("0.01", "0.05")),),
        planned_metrics=("brier", "net_return_bps"),
        planned_splits=splits,
        planned_cost_model="conservative_l2-fee-nonzero",
        final_holdout_planned=holdout,
    )


def _trial(
    registration: ExperimentRegistration,
    *,
    trial_id: int = 1,
    status: TrialStatus = TrialStatus.SUCCEEDED,
    split_role: SplitRole = SplitRole.TEST,
) -> TrialResult:
    return TrialResult(
        trial_id=UUID(int=trial_id),
        experiment_id=registration.experiment_id,
        started_at_utc=BASE_TIME + timedelta(seconds=1),
        ended_at_utc=BASE_TIME + timedelta(seconds=2),
        random_seed=7,
        split_role=split_role,
        split_hash="e" * 64,
        hyperparameters=(("learning_rate", "0.01"),),
        metrics=() if status is TrialStatus.FAILED else (("brier", 0.2),),
        status=status,
        failure_reason="intentional negative result" if status is TrialStatus.FAILED else None,
        artifact_hash=None if status is TrialStatus.FAILED else "a" * 64,
        holdout_used=split_role is SplitRole.FINAL_HOLDOUT,
        approved_review_id=(
            "manual-final-review-1" if split_role is SplitRole.FINAL_HOLDOUT else None
        ),
    )


def test_trial_requires_preregistration_and_declared_search_space() -> None:
    registration = _registration()
    ledger = ExperimentLedger()
    with pytest.raises(ExperimentLedgerError, match="prior"):
        ledger.record_trial(_trial(registration))

    ledger.preregister(registration)
    undeclared = _trial(registration).model_copy(
        update={"hyperparameters": (("learning_rate", "0.99"),)}
    )
    with pytest.raises(ExperimentLedgerError, match="not preregistered"):
        ledger.record_trial(undeclared)


def test_failed_trials_are_retained_and_summary_reconciles() -> None:
    registration = _registration()
    ledger = ExperimentLedger()
    ledger.preregister(registration)
    ledger.record_trial(_trial(registration, status=TrialStatus.FAILED))
    summary = ExperimentSummary(
        experiment_id=registration.experiment_id,
        closed_at_utc=BASE_TIME + timedelta(seconds=3),
        trial_count=1,
        failure_count=1,
        oos_metrics=(),
        holdout_used=False,
        decision=ExperimentDecision.REJECT,
        reason="negative OOS result retained",
    )
    ledger.close(summary)
    ledger.verify()

    assert ledger.trials_for(registration.experiment_id)[0].failure_reason
    with pytest.raises(ExperimentLedgerError, match="closed"):
        ledger.record_trial(_trial(registration, trial_id=2))


def test_final_holdout_requires_preregistration_and_is_one_shot() -> None:
    registration = _registration(holdout=True)
    ledger = ExperimentLedger()
    ledger.preregister(registration)
    ledger.record_trial(_trial(registration, trial_id=1, split_role=SplitRole.FINAL_HOLDOUT))
    with pytest.raises(ExperimentLedgerError, match="only once"):
        ledger.record_trial(_trial(registration, trial_id=2, split_role=SplitRole.FINAL_HOLDOUT))

    not_planned = _registration()
    another = ExperimentLedger()
    another.preregister(not_planned)
    with pytest.raises(ExperimentLedgerError, match="split was not preregistered"):
        another.record_trial(_trial(not_planned, split_role=SplitRole.FINAL_HOLDOUT))


def test_ledger_hash_chain_and_atomic_snapshot(tmp_path: Path) -> None:
    registration = _registration()
    ledger = ExperimentLedger()
    ledger.preregister(registration)
    ledger.record_trial(_trial(registration))
    ledger.verify()
    snapshot = ledger.snapshot()
    path = write_experiment_ledger(snapshot, tmp_path / "experiments.json")
    parsed = orjson.loads(path.read_bytes())
    loaded = read_experiment_ledger(path)
    restored = ExperimentLedger.from_snapshot(loaded)

    assert parsed["chain_hash"] == snapshot.chain_hash
    assert len(parsed["records"]) == 2
    assert restored.snapshot() == snapshot
    assert not list(tmp_path.glob("*.tmp"))

    ledger._records[0] = ledger._records[0].model_copy(update={"payload_json": "{}"})
    with pytest.raises(ExperimentLedgerError, match="hash"):
        ledger.verify()


def test_summary_counts_cannot_hide_failures() -> None:
    registration = _registration()
    ledger = ExperimentLedger()
    ledger.preregister(registration)
    ledger.record_trial(_trial(registration, status=TrialStatus.FAILED))
    bad = ExperimentSummary(
        experiment_id=registration.experiment_id,
        closed_at_utc=BASE_TIME + timedelta(seconds=3),
        trial_count=1,
        failure_count=0,
        oos_metrics=(),
        holdout_used=False,
        decision=ExperimentDecision.HOLD,
        reason="bad summary fixture",
    )
    with pytest.raises(ExperimentLedgerError, match="failure count"):
        ledger.close(bad)

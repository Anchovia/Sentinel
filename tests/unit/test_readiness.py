import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantforge.operations import UnsafeRuntimeExport
from quantforge.readiness import (
    BackupRestoreEvidence,
    CanaryPlanEvidence,
    CostModelEvidence,
    DataAvailabilityEvidence,
    IncidentEvidence,
    LiveLockEvidence,
    ModelStabilityEvidence,
    OperatorRunbookEvidence,
    OrderTestEvidence,
    PaperHistoryEvidence,
    PerformanceEvidence,
    ReadinessEvaluator,
    ReadinessEvidence,
    ReadinessPolicy,
    ReadinessStatus,
    ReconciliationEvidence,
    ReleaseApprovalEvidence,
    SecurityEvidence,
    load_readiness_evidence,
    load_readiness_policy,
    read_readiness_report,
    write_readiness_report,
)
from quantforge.readiness.models import GateStatus

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "configs" / "readiness.default.yaml"
NOW = datetime(2026, 8, 23, tzinfo=UTC)
SOURCE_HASH = "1" * 64
MODEL_HASH = "2" * 64
REVISION = "a" * 40


def _preferred_evidence() -> ReadinessEvidence:
    return ReadinessEvidence(
        evidence_id="preferred-fixture",
        generated_at_utc=NOW,
        source_revision=REVISION,
        paper_history=PaperHistoryEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            period_start_utc=NOW - timedelta(days=100),
            period_end_utc=NOW,
            trade_count=2500,
            observed_regimes=("calm", "trend", "volatile", "illiquid"),
        ),
        reconciliation=ReconciliationEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            window_days=30,
            successful_days=30,
            reconciliation_runs=90,
            mismatch_count=0,
            unknown_order_count=0,
            last_success_at_utc=NOW,
        ),
        data_availability=DataAvailabilityEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            window_days=90,
            availability_ratio=Decimal("0.9995"),
            gap_count=1,
            checksum_failure_count=0,
            schema_compatible=True,
            freshest_event_at_utc=NOW,
        ),
        incidents=IncidentEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            window_days=90,
            unresolved_critical=0,
            unresolved_high=0,
            critical_opened=0,
            high_opened=1,
        ),
        model_stability=ModelStabilityEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            stability_days=45,
            calibration_error=Decimal("0.03"),
            drift_score=Decimal("0.10"),
            artifact_integrity_verified=True,
            active_artifact_hashes=(MODEL_HASH,),
        ),
        performance=PerformanceEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            paper_trade_count=2500,
            maximum_drawdown_ratio=Decimal("0.08"),
            cost_adjusted_expectancy_lower_bps=Decimal("0.8"),
            all_costs_included=True,
        ),
        cost_model=CostModelEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            observation_count=1500,
            mean_absolute_error_bps=Decimal("3"),
            includes_fees=True,
            includes_spread=True,
            includes_slippage=True,
            includes_latency=True,
            includes_adverse_selection=True,
        ),
        order_test=OrderTestEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            endpoint_supported_by_manifest=True,
            dry_run_verified=True,
            completed_at_utc=NOW,
        ),
        backup_restore=BackupRestoreEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            restore_verified=True,
            checksum_verified=True,
            isolated_target=True,
            production_grade=True,
            encrypted=True,
            off_host=True,
            objectives_measured=True,
            tested_at_utc=NOW,
        ),
        security=SecurityEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            audit_passed=True,
            high_or_critical_findings=0,
            secret_scan_passed=True,
            dependency_audit_passed=True,
            dashboard_auth_reviewed=True,
            network_policy_reviewed=True,
            withdrawal_permission_disabled=True,
            api_key_ip_allowlist_reviewed=True,
            live_gates_tested=True,
            completed_at_utc=NOW,
        ),
        operator_runbook=OperatorRunbookEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            verified=True,
            reviewed_operator_count=2,
            incident_drill_passed=True,
            cancel_only_drill_passed=True,
            reconciliation_drill_passed=True,
            recovery_drill_passed=True,
            completed_at_utc=NOW,
        ),
        live_locks=LiveLockEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            default_mode_paper=True,
            order_submission_default_false=True,
            six_gate_guard_verified=True,
            single_flag_cannot_enable_live=True,
            operator_unlock_absent=True,
            live_adapter_implemented_and_reviewed=True,
            order_network_allowlist_reviewed=True,
        ),
        release_approval=ReleaseApprovalEvidence(
            observed_at_utc=NOW,
            source_sha256=SOURCE_HASH,
            release_manifest_approval_id="review-release-1",
            risk_policy_approval_id="review-risk-1",
            model_release_approval_id="review-model-1",
            operator_canary_review_id="review-operator-1",
            approved_code_revision=REVISION,
            approved_model_hashes=(MODEL_HASH,),
            canary_plan=CanaryPlanEvidence(
                markets=("KRW-BTC",),
                maximum_order_notional_krw=Decimal("5000"),
                maximum_total_exposure_krw=Decimal("10000"),
                maximum_duration_minutes=30,
            ),
        ),
    )


def test_missing_evidence_is_fail_closed() -> None:
    evidence = load_readiness_evidence(ROOT / "tests/fixtures/readiness/not-ready.json")
    report = ReadinessEvaluator().evaluate(
        evidence, load_readiness_policy(POLICY_PATH), evaluated_at_utc=NOW
    )

    assert report.status is ReadinessStatus.NOT_READY
    assert len(report.gates) == 13
    assert all(gate.status is GateStatus.FAIL for gate in report.gates)
    assert report.activation_performed is False
    assert report.safety.real_orders_executed is False
    assert report.safety.order_network_used is False


def test_all_preferred_evidence_only_allows_manual_canary_review() -> None:
    report = ReadinessEvaluator().evaluate(
        _preferred_evidence(), load_readiness_policy(POLICY_PATH), evaluated_at_utc=NOW
    )

    assert report.status is ReadinessStatus.READY_FOR_MANUAL_CANARY_REVIEW
    assert all(gate.status is GateStatus.PASS for gate in report.gates)
    assert report.human_approval_required is True
    assert report.activation_performed is False
    assert report.safety.runtime_settings_changed is False


def test_hard_minimums_below_preferred_are_conditional() -> None:
    evidence = _preferred_evidence()
    evidence = evidence.model_copy(
        update={
            "paper_history": evidence.paper_history.model_copy(
                update={
                    "period_start_utc": NOW - timedelta(days=45),
                    "trade_count": 800,
                    "observed_regimes": ("calm", "trend", "volatile"),
                }
            ),
            "performance": evidence.performance.model_copy(update={"paper_trade_count": 800}),
        }
    )

    report = ReadinessEvaluator().evaluate(
        evidence, load_readiness_policy(POLICY_PATH), evaluated_at_utc=NOW
    )

    assert report.status is ReadinessStatus.CONDITIONALLY_READY
    paper_gate = next(gate for gate in report.gates if gate.gate.value == "paper_history")
    assert paper_gate.status is GateStatus.CONDITIONAL


def test_unknown_order_overrides_other_ready_evidence() -> None:
    evidence = _preferred_evidence()
    evidence = evidence.model_copy(
        update={
            "reconciliation": evidence.reconciliation.model_copy(update={"unknown_order_count": 1})
        }
    )

    report = ReadinessEvaluator().evaluate(
        evidence, load_readiness_policy(POLICY_PATH), evaluated_at_utc=NOW
    )

    assert report.status is ReadinessStatus.NOT_READY
    gate = next(gate for gate in report.gates if gate.gate.value == "reconciliation")
    assert gate.status is GateStatus.FAIL
    assert "unknown orders must be zero" in gate.reasons


def test_stale_security_and_local_backup_proof_fail() -> None:
    evidence = _preferred_evidence()
    evidence = evidence.model_copy(
        update={
            "security": evidence.security.model_copy(
                update={"completed_at_utc": NOW - timedelta(days=8)}
            ),
            "backup_restore": evidence.backup_restore.model_copy(
                update={
                    "production_grade": False,
                    "encrypted": False,
                    "off_host": False,
                    "objectives_measured": False,
                }
            ),
        }
    )

    report = ReadinessEvaluator().evaluate(
        evidence, load_readiness_policy(POLICY_PATH), evaluated_at_utc=NOW
    )

    assert report.status is ReadinessStatus.NOT_READY
    failed = {gate.gate.value for gate in report.gates if gate.status is GateStatus.FAIL}
    assert {"security", "backup_restore"}.issubset(failed)


def test_release_approval_must_bind_code_and_model_artifacts() -> None:
    payload = _preferred_evidence().model_dump(mode="json")
    payload["release_approval"]["approved_code_revision"] = "b" * 40

    with pytest.raises(ValidationError, match="source revision"):
        ReadinessEvidence.model_validate(payload)

    payload = _preferred_evidence().model_dump(mode="json")
    payload["release_approval"]["approved_model_hashes"] = ["3" * 64]
    with pytest.raises(ValidationError, match="active model"):
        ReadinessEvidence.model_validate(payload)

    payload = _preferred_evidence().model_dump(mode="json")
    payload["release_approval"]["risk_policy_approval_id"] = payload["release_approval"][
        "release_manifest_approval_id"
    ]
    with pytest.raises(ValidationError, match="approvals must be distinct"):
        ReadinessEvidence.model_validate(payload)


def test_oversized_canary_plan_cannot_reach_manual_review() -> None:
    evidence = _preferred_evidence()
    evidence = evidence.model_copy(
        update={
            "release_approval": evidence.release_approval.model_copy(
                update={
                    "canary_plan": evidence.release_approval.canary_plan.model_copy(
                        update={"maximum_order_notional_krw": Decimal("10001")}
                    )
                }
            )
        }
    )

    report = ReadinessEvaluator().evaluate(
        evidence, load_readiness_policy(POLICY_PATH), evaluated_at_utc=NOW
    )

    assert report.status is ReadinessStatus.NOT_READY
    gate = next(gate for gate in report.gates if gate.gate.value == "release_approval")
    assert gate.status is GateStatus.FAIL


def test_readiness_runtime_has_no_exchange_or_http_import() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src/quantforge/readiness").glob("*.py")
    )

    assert "quantforge.exchange" not in source
    assert "requests" not in source
    assert "httpx" not in source


def test_future_dated_evidence_fails_its_gate() -> None:
    evidence = _preferred_evidence()
    evidence = evidence.model_copy(
        update={
            "paper_history": evidence.paper_history.model_copy(
                update={"observed_at_utc": NOW + timedelta(minutes=1)}
            )
        }
    )

    report = ReadinessEvaluator().evaluate(
        evidence, load_readiness_policy(POLICY_PATH), evaluated_at_utc=NOW
    )

    assert report.status is ReadinessStatus.NOT_READY
    gate = next(gate for gate in report.gates if gate.gate.value == "paper_history")
    assert "component observation is later than the evidence bundle" in gate.reasons


def test_preferred_policy_cannot_be_weaker_than_hard_policy() -> None:
    payload = load_readiness_policy(POLICY_PATH).model_dump()
    payload["preferred_minimum_paper_days"] = 1

    with pytest.raises(ValidationError, match="preferred minimum"):
        ReadinessPolicy.model_validate(payload)


def test_readiness_report_atomic_round_trip(tmp_path: Path) -> None:
    report = ReadinessEvaluator().evaluate(
        _preferred_evidence(), load_readiness_policy(POLICY_PATH), evaluated_at_utc=NOW
    )

    path = write_readiness_report(report, tmp_path)

    assert path == tmp_path / "readiness" / "latest.json"
    assert read_readiness_report(path) == report
    assert not tuple(path.parent.glob("*.tmp"))


def test_evidence_loader_rejects_secret_shaped_content(tmp_path: Path) -> None:
    payload = json.loads(
        (ROOT / "tests/fixtures/readiness/not-ready.json").read_text(encoding="utf-8")
    )
    payload["authorization"] = "Bearer abc.def.ghi"
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UnsafeRuntimeExport):
        load_readiness_evidence(path)

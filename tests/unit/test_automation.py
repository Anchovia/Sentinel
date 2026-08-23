import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from quantforge.automation import (
    AutomationActor,
    AutomationBoundaryError,
    AutomationOutcome,
    AutomationReport,
    AutomationSeverity,
    SkillName,
    assert_paths_allowed,
    assert_report_boundary,
    inspect_git_worktree,
    load_report,
    load_trigger,
    load_write_allowlist,
)
from quantforge.automation.contracts import AutomationSafety, WorktreeProof
from quantforge.operations import UnsafeRuntimeExport

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = ROOT / "automation" / "write-allowlist.yaml"
FIXTURES = ROOT / "tests" / "fixtures" / "automation"


def _report(
    *,
    actor: AutomationActor = AutomationActor.WORK,
    skill: SkillName = SkillName.OPS_AUDIT,
    report_path: str = "reports/work/ops/2026/08/23/report.md",
    writes: tuple[str, ...] | None = None,
    outcome: AutomationOutcome = AutomationOutcome.NO_ACTION,
    severity: AutomationSeverity = AutomationSeverity.NORMAL,
    worktree: WorktreeProof | None = None,
) -> AutomationReport:
    return AutomationReport(
        run_id="test-run-1",
        task_id=f"{actor}.manual",
        actor=actor,
        skill=skill,
        started_at_utc=datetime(2026, 8, 23, tzinfo=UTC),
        completed_at_utc=datetime(2026, 8, 23, 0, 0, 1, tzinfo=UTC),
        source_revision="1111111",
        severity=severity,
        outcome=outcome,
        summary="No actionable issue detected in the deterministic fixture.",
        report_path=report_path,
        writes=writes or (report_path,),
        validation=("schema pass",),
        worktree=worktree,
        safety=AutomationSafety(),
    )


def test_work_noop_fixture_is_valid_and_allowlisted() -> None:
    report = load_report(FIXTURES / "work-noop-report.json")
    contract = load_write_allowlist(ALLOWLIST)

    assert report.outcome is AutomationOutcome.NO_ACTION
    assert_report_boundary(report, contract, ROOT)


def test_work_source_write_is_rejected() -> None:
    report = _report(
        writes=("reports/work/ops/report.md", "src/quantforge/cli.py"),
        report_path="reports/work/ops/report.md",
    )

    with pytest.raises(AutomationBoundaryError, match="denied"):
        assert_report_boundary(report, load_write_allowlist(ALLOWLIST), ROOT)


def test_work_cannot_claim_change_candidate() -> None:
    with pytest.raises(ValidationError, match="Work cannot produce"):
        _report(outcome=AutomationOutcome.CHANGE_CANDIDATE)


def test_codex_report_requires_worktree_proof() -> None:
    with pytest.raises(ValidationError, match="dedicated worktree proof"):
        _report(
            actor=AutomationActor.CODEX,
            skill=SkillName.CODE_AUDIT,
            report_path="reports/codex/code-audit/report.md",
        )


def test_codex_report_is_rejected_in_primary_checkout() -> None:
    report = load_report(FIXTURES / "codex-noop-report.json")

    with pytest.raises(AutomationBoundaryError, match="dedicated worktree"):
        assert_report_boundary(report, load_write_allowlist(ALLOWLIST), ROOT)


def test_linked_worktree_is_detected_without_shell(tmp_path: Path) -> None:
    common = tmp_path / "common" / ".git"
    worktree_git = common / "worktrees" / "audit"
    checkout = tmp_path / "checkout"
    worktree_git.mkdir(parents=True)
    checkout.mkdir()
    (checkout / ".git").write_text(f"gitdir: {worktree_git}\n", encoding="utf-8")
    (worktree_git / "commondir").write_text("../..\n", encoding="utf-8")
    (worktree_git / "HEAD").write_text("1111111\n", encoding="utf-8")

    state = inspect_git_worktree(checkout)

    assert state.dedicated is True
    assert state.branch is None
    assert state.common_git_directory == common.resolve()


def test_change_candidate_requires_non_main_branch_evidence_and_validation() -> None:
    with pytest.raises(ValidationError, match="non-main candidate branch"):
        _report(
            actor=AutomationActor.CODEX,
            skill=SkillName.CODE_AUDIT,
            report_path="reports/codex/code-audit/report.md",
            outcome=AutomationOutcome.CHANGE_CANDIDATE,
            worktree=WorktreeProof(base_revision="1111111"),
        )


def test_paths_reject_traversal_and_protected_risk_files() -> None:
    with pytest.raises(ValidationError, match="traversal"):
        _report(report_path="reports/work/../src/cli.py")

    with pytest.raises(AutomationBoundaryError, match="denied"):
        assert_paths_allowed(
            AutomationActor.CODEX,
            ("configs/risk.default.yaml",),
            load_write_allowlist(ALLOWLIST),
        )
    with pytest.raises(AutomationBoundaryError, match="denied"):
        assert_paths_allowed(
            AutomationActor.CODEX,
            ("configs/readiness.default.yaml",),
            load_write_allowlist(ALLOWLIST),
        )


def test_report_loader_rejects_credential_shaped_text(tmp_path: Path) -> None:
    payload = json.loads((FIXTURES / "work-noop-report.json").read_text(encoding="utf-8"))
    payload["summary"] = "Bearer abc.def.ghi"
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UnsafeRuntimeExport):
        load_report(path)


def test_trigger_is_structured_and_requested_writes_are_allowed() -> None:
    trigger = load_trigger(FIXTURES / "codex-trigger.json")

    assert trigger.operator_approval_required is True
    assert_paths_allowed(
        AutomationActor.CODEX,
        trigger.requested_write_paths,
        load_write_allowlist(ALLOWLIST),
    )


@pytest.mark.parametrize(
    ("actor", "skill", "report_path"),
    [
        (AutomationActor.WORK, SkillName.OPS_AUDIT, "reports/work/ops/a.md"),
        (AutomationActor.WORK, SkillName.PERFORMANCE_REVIEW, "reports/work/performance/a.md"),
        (AutomationActor.WORK, SkillName.DATA_QUALITY, "reports/work/model-health/a.md"),
        (AutomationActor.WORK, SkillName.MODEL_DRIFT, "reports/work/model-health/b.md"),
        (AutomationActor.WORK, SkillName.STRATEGY_RESEARCH, "reports/work/research/a.md"),
        (AutomationActor.CODEX, SkillName.INCIDENT_TRIAGE, "reports/codex/incidents/a.md"),
        (AutomationActor.CODEX, SkillName.CODE_AUDIT, "reports/codex/code-audit/a.md"),
        (AutomationActor.CODEX, SkillName.STRATEGY_RESEARCH, "reports/codex/research/a.md"),
        (AutomationActor.CODEX, SkillName.DEPENDENCY_REVIEW, "reports/codex/security/a.md"),
        (
            AutomationActor.CODEX,
            SkillName.DISASTER_RECOVERY,
            "reports/codex/disaster-recovery/a.md",
        ),
    ],
)
def test_every_skill_has_a_valid_manual_noop_or_blocked_envelope(
    actor: AutomationActor, skill: SkillName, report_path: str
) -> None:
    worktree = WorktreeProof(base_revision="1111111") if actor is AutomationActor.CODEX else None
    report = _report(actor=actor, skill=skill, report_path=report_path, worktree=worktree)

    assert report.outcome is AutomationOutcome.NO_ACTION


def test_repository_skill_and_schedule_catalog_is_complete() -> None:
    expected = {skill.value for skill in SkillName}
    actual = {path.parent.name for path in (ROOT / ".agents" / "skills").glob("*/SKILL.md")}
    catalog = yaml.safe_load(
        (ROOT / "automation" / "schedules" / "tasks.yaml").read_text(encoding="utf-8")
    )

    assert actual == expected
    assert catalog["registration_status"] == "not_registered"
    assert catalog["timezone"] == "Asia/Seoul"
    assert catalog["automatic_merge"] is False
    assert catalog["automatic_deploy"] is False
    assert catalog["real_orders_allowed"] is False
    assert len(catalog["tasks"]) == 10
    assert all((ROOT / task["prompt"]).is_file() for task in catalog["tasks"])


def test_json_schemas_are_closed_and_safety_is_false_only() -> None:
    report_schema = json.loads(
        (ROOT / "automation" / "schemas" / "report.schema.json").read_text(encoding="utf-8")
    )
    trigger_schema = json.loads(
        (ROOT / "automation" / "schemas" / "trigger.schema.json").read_text(encoding="utf-8")
    )

    assert report_schema["additionalProperties"] is False
    assert trigger_schema["additionalProperties"] is False
    assert all(
        rule == {"const": False} for rule in report_schema["$defs"]["safety"]["properties"].values()
    )

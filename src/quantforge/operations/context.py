"""Composition root for the read-oriented operations plane."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from quantforge import __version__
from quantforge.config import QuantForgeSettings
from quantforge.operations.audit import AuditLog
from quantforge.operations.auth import DashboardAuthenticator
from quantforge.operations.controls import (
    ControlAction,
    ControlJournal,
    ControlStatus,
    EmergencyControlService,
    LocalSafetyControlExecutor,
)
from quantforge.operations.exports import read_dashboard_snapshot
from quantforge.operations.incidents import IncidentStore
from quantforge.operations.models import DashboardSnapshot, OverviewView
from quantforge.risk import KillSwitch, KillSwitchMode
from quantforge.runtime import LiveSubmissionGuard


@dataclass(slots=True)
class OperationsContext:
    authenticator: DashboardAuthenticator
    audit_log: AuditLog
    incidents: IncidentStore
    control_journal: ControlJournal
    controls: EmergencyControlService
    kill_switch: KillSwitch
    base_snapshot: DashboardSnapshot

    def snapshot(self) -> DashboardSnapshot:
        overview = self.base_snapshot.overview.model_copy(
            update={"kill_switch_state": self.kill_switch.state.value}
        )
        return self.base_snapshot.model_copy(
            update={"overview": overview, "incidents": self.incidents.list_current()}
        )


def create_operations_context(
    settings: QuantForgeSettings,
    *,
    now_utc: datetime | None = None,
    state_root: Path | None = None,
    export_root: Path | None = None,
) -> OperationsContext:
    generated_at = now_utc or datetime.now(UTC)
    selected_state_root = state_root or settings.operations_state_root
    selected_export_root = export_root or settings.runtime_export_root
    audit_log = AuditLog(selected_state_root / "audit.jsonl")
    incidents = IncidentStore(selected_state_root / "incidents.jsonl")
    control_journal = ControlJournal(selected_state_root / "controls.jsonl")
    kill_switch = KillSwitch()
    activated = any(
        record.action is ControlAction.ACTIVATE_CANCEL_ONLY
        and record.status is ControlStatus.VERIFIED
        and record.effect_verified
        for record in control_journal.records
    )
    if activated:
        kill_switch.activate(
            KillSwitchMode.CANCEL_ONLY,
            reason="RECOVERED_FROM_VERIFIED_CONTROL_JOURNAL",
            occurred_at_utc=generated_at,
        )
    controls = EmergencyControlService(
        control_journal,
        audit_log,
        LocalSafetyControlExecutor(kill_switch, incidents),
    )
    snapshot_path = selected_export_root / "ops" / "dashboard.json"
    if snapshot_path.exists():
        snapshot = read_dashboard_snapshot(snapshot_path)
    else:
        gate = LiveSubmissionGuard.evaluate(settings)
        snapshot = DashboardSnapshot(
            generated_at_utc=generated_at,
            overview=OverviewView(
                trading_mode=settings.trading_mode.value,
                live_submission_allowed=gate.allowed,
                failed_live_gates=gate.failures,
                kill_switch_state=kill_switch.state.value,
                code_version=__version__,
            ),
        )
    return OperationsContext(
        authenticator=DashboardAuthenticator(
            settings.dashboard_access_token, settings.dashboard_csrf_secret
        ),
        audit_log=audit_log,
        incidents=incidents,
        control_journal=control_journal,
        controls=controls,
        kill_switch=kill_switch,
        base_snapshot=snapshot,
    )

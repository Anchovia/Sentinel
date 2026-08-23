from pathlib import Path

import pytest

from factories import BASE_TIME
from quantforge.operations import (
    CONFIRMATIONS,
    AuditIntegrityError,
    AuditLog,
    ControlAction,
    ControlJournal,
    ControlRequest,
    ControlStatus,
    EmergencyControlService,
    IncidentIntegrityError,
    IncidentSeverity,
    IncidentStore,
    IncidentView,
    LocalSafetyControlExecutor,
)
from quantforge.risk import KillSwitch

ACTOR = "a" * 16


def _incident() -> IncidentView:
    return IncidentView(
        incident_id="inc-0001",
        opened_at_utc=BASE_TIME,
        severity=IncidentSeverity.CRITICAL,
        category="BALANCE_MISMATCH",
        component="reconciliation",
        markets=("KRW-BTC",),
        summary="Exact paper balance differs; Bearer pretend",
        evidence=(("message", "Bearer pretend"),),
        requires_operator=True,
        code_version="0.1.0",
    )


def _request(action: ControlAction, target: str = "all") -> ControlRequest:
    return ControlRequest(
        action=action,
        target=target,
        reason="operator safety response",
        confirmation=CONFIRMATIONS[action],
    )


def test_incident_store_is_append_only_redacted_and_reopenable(tmp_path: Path) -> None:
    path = tmp_path / "incidents.jsonl"
    store = IncidentStore(path)
    event = store.open(_incident(), actor_ref=ACTOR)
    assert event.incident.evidence == (("message", "[REDACTED]"),)
    assert event.incident.summary.endswith("[REDACTED]")
    acknowledged = store.acknowledge("inc-0001", actor_ref=ACTOR, occurred_at_utc=BASE_TIME)
    assert acknowledged.incident.status.value == "ACKNOWLEDGED"

    restored = IncidentStore(path)
    assert restored.get("inc-0001") == acknowledged.incident
    with pytest.raises(IncidentIntegrityError):
        restored.acknowledge("inc-0001", actor_ref=ACTOR, occurred_at_utc=BASE_TIME)


def test_audit_chain_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)
    audit.append(
        occurred_at_utc=BASE_TIME,
        actor_ref=ACTOR,
        action="test",
        target="local",
        outcome="VERIFIED",
        request_fingerprint="b" * 64,
        idempotency_key="once",
    )
    assert AuditLog(path).events == audit.events
    path.write_bytes(path.read_bytes().replace(b'"outcome":"VERIFIED"', b'"outcome":"FAILED"'))
    with pytest.raises(AuditIntegrityError):
        AuditLog(path)


def test_confirmed_control_is_idempotent_verified_and_audited(tmp_path: Path) -> None:
    journal = ControlJournal(tmp_path / "controls.jsonl")
    audit = AuditLog(tmp_path / "audit.jsonl")
    incidents = IncidentStore(tmp_path / "incidents.jsonl")
    kill_switch = KillSwitch()
    service = EmergencyControlService(
        journal, audit, LocalSafetyControlExecutor(kill_switch, incidents)
    )
    request = _request(ControlAction.ACTIVATE_CANCEL_ONLY)

    first = service.submit(
        request, actor_ref=ACTOR, idempotency_key="control-once", occurred_at_utc=BASE_TIME
    )
    repeated = service.submit(
        request, actor_ref=ACTOR, idempotency_key="control-once", occurred_at_utc=BASE_TIME
    )
    assert first == repeated
    assert first.status is ControlStatus.VERIFIED
    assert first.effect_verified is True
    assert first.network_used is False
    assert kill_switch.active is True
    assert len(journal.records) == 2
    assert len(audit.events) == 2
    assert journal.path is not None
    assert audit.path is not None
    assert ControlJournal(journal.path).records == journal.records
    assert AuditLog(audit.path).events == audit.events

    with pytest.raises(ValueError, match="different request"):
        service.submit(
            _request(ControlAction.PAUSE_STRATEGY_REQUEST, "strategy-a"),
            actor_ref=ACTOR,
            idempotency_key="control-once",
            occurred_at_utc=BASE_TIME,
        )


def test_control_confirmation_missing_transport_and_interrupted_request_fail_closed(
    tmp_path: Path,
) -> None:
    journal = ControlJournal(tmp_path / "controls.jsonl")
    audit = AuditLog()
    service = EmergencyControlService(
        journal, audit, LocalSafetyControlExecutor(KillSwitch(), IncidentStore())
    )
    bad = _request(ControlAction.ACTIVATE_CANCEL_ONLY).model_copy(update={"confirmation": "yes"})
    with pytest.raises(ValueError, match="confirmation"):
        service.submit(bad, actor_ref=ACTOR, idempotency_key="bad", occurred_at_utc=BASE_TIME)

    cancel = _request(ControlAction.CANCEL_ALL_ORDERS_REQUEST)
    blocked = service.submit(
        cancel, actor_ref=ACTOR, idempotency_key="cancel", occurred_at_utc=BASE_TIME
    )
    assert blocked.status is ControlStatus.BLOCKED
    assert blocked.result_code == "ORDER_CANCELLATION_TRANSPORT_UNAVAILABLE"

    pause = _request(ControlAction.PAUSE_STRATEGY_REQUEST, "strategy-a")
    journal.append(
        request=pause,
        actor_ref=ACTOR,
        idempotency_key="interrupted",
        status=ControlStatus.REQUESTED,
        result_code="REQUEST_ACCEPTED",
        effect_verified=False,
        network_used=False,
        occurred_at_utc=BASE_TIME,
    )
    unknown = service.submit(
        pause, actor_ref=ACTOR, idempotency_key="interrupted", occurred_at_utc=BASE_TIME
    )
    assert unknown.status is ControlStatus.UNKNOWN
    assert unknown.effect_verified is False

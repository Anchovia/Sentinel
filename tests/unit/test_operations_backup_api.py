from pathlib import Path

import httpx
import pytest

from factories import BASE_TIME
from quantforge.api.app import create_app
from quantforge.config import QuantForgeSettings
from quantforge.operations import (
    CONFIRMATIONS,
    BackupError,
    ControlAction,
    IncidentSeverity,
    IncidentView,
    LocalBackupManager,
    create_operations_context,
)

ACCESS_TOKEN = "dashboard-test-access-token-00000001"
CSRF_SECRET = "dashboard-test-csrf-secret-000000001"
AUTH_HEADERS = {"Authorization": "Bearer " + ACCESS_TOKEN}


def _settings() -> QuantForgeSettings:
    return QuantForgeSettings(
        _env_file=None,
        dashboard_access_token=ACCESS_TOKEN,
        dashboard_csrf_secret=CSRF_SECRET,
    )


def test_checksums_backup_restore_and_tamper_detection(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "runtime_exports" / "ops"
    source.mkdir(parents=True)
    (source / "dashboard.json").write_text('{"mode":"paper"}\n', encoding="utf-8")
    manager = LocalBackupManager(workspace)
    backup = manager.create(
        (source,),
        workspace / "backups",
        source_revision="test-revision",
        created_at_utc=BASE_TIME,
    )
    manifest = manager.verify(backup)
    assert manifest.trading_mode == "paper"
    assert manifest.objectives_measured is False
    assert manifest.encrypted_by_external_storage is False

    restored = workspace / "restore-drill"
    manager.restore_drill(backup, restored)
    assert (restored / "RESTORE_PAPER_ONLY").is_file()
    assert (restored / "runtime_exports" / "ops" / "dashboard.json").is_file()

    payload = backup / "payload" / "runtime_exports" / "ops" / "dashboard.json"
    payload.write_text("tampered", encoding="utf-8")
    with pytest.raises(BackupError, match="checksum"):
        manager.verify(backup)


def test_backup_rejects_secret_files_and_nonempty_restore_target(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    forbidden = workspace / ".env"
    forbidden.write_text("not-a-real-secret", encoding="utf-8")
    manager = LocalBackupManager(workspace)
    with pytest.raises(BackupError, match="credential-shaped"):
        manager.create(
            (forbidden,),
            workspace / "backups",
            source_revision="test",
            created_at_utc=BASE_TIME,
        )

    disguised = workspace / "runtime.txt"
    disguised.write_text("Bearer " + "x" * 40, encoding="utf-8")
    with pytest.raises(BackupError, match="content"):
        manager.create(
            (disguised,),
            workspace / "backups",
            source_revision="test",
            created_at_utc=BASE_TIME,
        )


async def test_dashboard_api_is_fail_closed_without_authentication(tmp_path: Path) -> None:
    settings = QuantForgeSettings(_env_file=None)
    context = create_operations_context(
        settings, state_root=tmp_path / "state", export_root=tmp_path / "exports"
    )
    transport = httpx.ASGITransport(app=create_app(settings, context))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/dashboard")
    assert response.status_code == 503


async def test_authenticated_dashboard_control_and_metrics(tmp_path: Path) -> None:
    settings = _settings()
    context = create_operations_context(
        settings, state_root=tmp_path / "state", export_root=tmp_path / "exports"
    )
    context.incidents.open(
        IncidentView(
            incident_id="inc-api",
            opened_at_utc=BASE_TIME,
            severity=IncidentSeverity.HIGH,
            category="DATA_STALE",
            component="market-data",
            summary="Paper data is stale",
            code_version="0.1.0",
        ),
        actor_ref="0" * 16,
    )
    transport = httpx.ASGITransport(app=create_app(settings, context))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.get("/api/v1/dashboard")
        dashboard = await client.get("/api/v1/dashboard", headers=AUTH_HEADERS)
        page = await client.get("/dashboard", headers=AUTH_HEADERS)
        session = await client.get("/api/v1/session", headers=AUTH_HEADERS)
        proof = session.json()["csrf_token"]
        request = {
            "action": ControlAction.ACTIVATE_CANCEL_ONLY,
            "target": "all",
            "reason": "operator safety response",
            "confirmation": CONFIRMATIONS[ControlAction.ACTIVATE_CANCEL_ONLY],
        }
        no_csrf = await client.post(
            "/api/v1/control-requests",
            headers={**AUTH_HEADERS, "Idempotency-Key": "api-once"},
            json=request,
        )
        controlled = await client.post(
            "/api/v1/control-requests",
            headers={
                **AUTH_HEADERS,
                "Idempotency-Key": "api-once",
                "X-CSRF-Token": proof,
            },
            json=request,
        )
        repeated = await client.post(
            "/api/v1/control-requests",
            headers={
                **AUTH_HEADERS,
                "Idempotency-Key": "api-once",
                "X-CSRF-Token": proof,
            },
            json=request,
        )
        metrics = await client.get("/metrics/")

    assert unauthorized.status_code == 401
    assert dashboard.status_code == 200
    assert dashboard.json()["overview"]["trading_mode"] == "paper"
    assert dashboard.json()["incidents"][0]["incident_id"] == "inc-api"
    assert page.status_code == 200
    assert "읽기 전용" in page.text
    assert ACCESS_TOKEN not in page.text
    assert no_csrf.status_code == 403
    assert controlled.status_code == 200
    assert controlled.json()["status"] == "VERIFIED"
    assert controlled.json() == repeated.json()
    assert controlled.json()["network_used"] is False
    assert "quantforge_dashboard_unauthorized_total 2.0" in metrics.text
    assert 'quantforge_open_incidents{severity="HIGH"} 1.0' in metrics.text
    assert "quantforge_kill_switch_active 1.0" in metrics.text

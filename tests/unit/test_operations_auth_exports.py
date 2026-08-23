from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from factories import BASE_TIME
from quantforge.config import QuantForgeSettings
from quantforge.operations import (
    CsrfValidationFailed,
    DashboardAuthenticationFailed,
    DashboardAuthenticator,
    DashboardAuthUnavailable,
    DashboardSnapshot,
    OverviewView,
    UnsafeRuntimeExport,
    assert_runtime_export_safe,
    read_dashboard_snapshot,
    render_dashboard,
    write_dashboard_snapshot,
)

ACCESS_TOKEN = "dashboard-test-access-token-00000001"
CSRF_SECRET = "dashboard-test-csrf-secret-000000001"


def _snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        generated_at_utc=BASE_TIME,
        overview=OverviewView(
            trading_mode="paper",
            failed_live_gates=("trading_mode_is_not_live",),
            code_version="0.1.0",
        ),
    )


def test_dashboard_settings_require_a_complete_strong_pair() -> None:
    blank = QuantForgeSettings(
        _env_file=None,
        dashboard_access_token="",
        dashboard_csrf_secret="",
    )
    assert blank.dashboard_access_token is None
    assert blank.dashboard_csrf_secret is None

    with pytest.raises(ValidationError, match="configured as a pair"):
        QuantForgeSettings(_env_file=None, dashboard_access_token=ACCESS_TOKEN)
    with pytest.raises(ValidationError, match="at least 32"):
        QuantForgeSettings(
            _env_file=None,
            dashboard_access_token="too-short",
            dashboard_csrf_secret="also-too-short",
        )


def test_authentication_and_short_lived_csrf_proof() -> None:
    auth = DashboardAuthenticator(SecretStr(ACCESS_TOKEN), SecretStr(CSRF_SECRET))
    actor = auth.authenticate("Bearer " + ACCESS_TOKEN)
    proof = auth.issue_csrf(actor, now_utc=BASE_TIME)
    auth.verify_csrf(proof, actor, now_utc=BASE_TIME + timedelta(minutes=4))

    with pytest.raises(DashboardAuthenticationFailed):
        auth.authenticate("Bearer wrong")
    with pytest.raises(CsrfValidationFailed, match="expired"):
        auth.verify_csrf(proof, actor, now_utc=BASE_TIME + timedelta(minutes=6))
    with pytest.raises(CsrfValidationFailed):
        auth.verify_csrf(proof + "damage", actor, now_utc=BASE_TIME)


def test_unconfigured_authentication_fails_closed() -> None:
    auth = DashboardAuthenticator(None, None)
    with pytest.raises(DashboardAuthUnavailable):
        auth.authenticate(None)
    with pytest.raises(DashboardAuthUnavailable):
        auth.issue_csrf("0" * 16, now_utc=BASE_TIME)


def test_runtime_export_is_atomic_round_trip_and_secret_free(tmp_path: Path) -> None:
    snapshot = _snapshot()
    path = write_dashboard_snapshot(snapshot, tmp_path)
    assert read_dashboard_snapshot(path) == snapshot
    assert list(path.parent.glob("*.tmp")) == []
    assert "authorization" not in path.read_text(encoding="utf-8").lower()

    page = render_dashboard(snapshot)
    assert "QuantForge Operations" in page
    assert "읽기 전용" in page
    assert "test-access" not in page


@pytest.mark.parametrize(
    "unsafe",
    [
        {"authorization": "anything"},
        {"nested": {"secret_key": "anything"}},
        {"message": "Bearer pretend"},
        {"account_uuid": "full-account-reference"},
    ],
)
def test_runtime_export_rejects_sensitive_shapes(unsafe: object) -> None:
    with pytest.raises(UnsafeRuntimeExport):
        assert_runtime_export_safe(unsafe)

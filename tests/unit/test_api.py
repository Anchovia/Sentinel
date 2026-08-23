import httpx

from quantforge.api.app import create_app
from quantforge.config import QuantForgeSettings


async def test_health_endpoint() -> None:
    transport = httpx.ASGITransport(app=create_app(QuantForgeSettings(_env_file=None)))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_safety_endpoint_does_not_expose_credentials() -> None:
    settings = QuantForgeSettings(
        _env_file=None,
        upbit_access_key="test-access-key",
        upbit_secret_key="test-secret-key",
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/safety")
    body = response.json()

    assert response.status_code == 200
    assert body["trading_mode"] == "paper"
    assert body["live_submission_allowed"] is False
    assert body["credentials_configured"] is True
    assert "test-access-key" not in response.text
    assert "test-secret-key" not in response.text


async def test_metrics_expose_non_secret_safety_state() -> None:
    transport = httpx.ASGITransport(app=create_app(QuantForgeSettings(_env_file=None)))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics/")

    assert response.status_code == 200
    assert "quantforge_live_submission_allowed 0.0" in response.text
    assert 'quantforge_trading_mode_info{mode="paper"} 1.0' in response.text
    assert "quantforge_market_data_connected 0.0" in response.text
    assert "quantforge_market_data_messages_received_total 0.0" in response.text

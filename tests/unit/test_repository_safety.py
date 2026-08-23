from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "relative_path",
    [
        "configs/base.yaml",
        "configs/development.yaml",
        "configs/paper.yaml",
        "configs/backtest.yaml",
        "configs/live.example.yaml",
        "configs/risk.default.yaml",
        "configs/markets.default.yaml",
        "configs/logging.yaml",
        "docker-compose.yml",
        "docker-compose.paper.yml",
        "ops/prometheus/prometheus.yml",
        "ops/grafana/provisioning/datasources/prometheus.yaml",
        "ops/grafana/provisioning/dashboards/default.yaml",
    ],
)
def test_yaml_files_parse(relative_path: str) -> None:
    content = (ROOT / relative_path).read_text(encoding="utf-8")

    assert yaml.safe_load(content) is not None


def test_committed_configs_cannot_enable_live_submission() -> None:
    base = yaml.safe_load((ROOT / "configs/base.yaml").read_text(encoding="utf-8"))
    live_example = yaml.safe_load((ROOT / "configs/live.example.yaml").read_text(encoding="utf-8"))
    paper = yaml.safe_load((ROOT / "configs/paper.yaml").read_text(encoding="utf-8"))

    assert base["trading"]["mode"] == "paper"
    assert base["trading"]["allow_order_submission"] is False
    assert live_example["trading"]["mode"] == "paper"
    assert live_example["live_adapter"]["implemented"] is False
    assert live_example["live_adapter"]["enabled"] is False
    assert paper["execution"]["real_order_network_access"] is False


def test_foundation_risk_limits_block_live_trading() -> None:
    risk = yaml.safe_load((ROOT / "configs/risk.default.yaml").read_text(encoding="utf-8"))

    assert risk["enforcement"]["fail_closed"] is True
    assert risk["enforcement"]["live_limits_configured"] is False
    numeric_limits = [value for value in risk["limits"].values() if isinstance(value, int | float)]
    assert numeric_limits
    assert all(value == 0 for value in numeric_limits)


def test_env_example_has_no_nonempty_exchange_credentials() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    credential_lines = [line for line in lines if line.startswith("QF_UPBIT_")]

    assert credential_lines == ["QF_UPBIT_ACCESS_KEY=", "QF_UPBIT_SECRET_KEY="]


def test_all_container_images_are_digest_pinned() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    image_services = [service for service in compose["services"].values() if "image" in service]

    assert image_services
    assert all("@sha256:" in service["image"] for service in image_services)

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    from_lines = [line for line in dockerfile.splitlines() if line.startswith("FROM ")]
    assert from_lines
    assert all("@sha256:" in line for line in from_lines)


def test_ci_actions_are_commit_pinned() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in workflow
    assert "astral-sh/setup-uv@d0d8abe699bfb85fec6de9f7adb5ae17292296ff" in workflow

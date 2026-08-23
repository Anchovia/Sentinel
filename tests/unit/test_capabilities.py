from pathlib import Path

import pytest
import yaml

from quantforge.exchange import load_upbit_capabilities

ROOT = Path(__file__).parents[2]


def test_reviewed_capability_manifest_is_public_only() -> None:
    manifest = load_upbit_capabilities(ROOT / "docs" / "upbit_capability_manifest.yaml")
    assert manifest.exchange == "upbit"
    assert manifest.public_websocket.authentication == "none"
    assert manifest.public_websocket.format == "DEFAULT"
    assert manifest.public_rest.authentication == "none"
    assert manifest.public_rest.credentials_sent is False
    assert manifest.public_rest.order_capability is False
    assert manifest.private_websocket.enabled is False
    assert manifest.rest_api.enabled is False


def test_manifest_rejects_unreviewed_private_enablement(tmp_path: Path) -> None:
    source = yaml.safe_load(
        (ROOT / "docs" / "upbit_capability_manifest.yaml").read_text(encoding="utf-8")
    )
    source["private_websocket"]["enabled"] = True
    path = tmp_path / "capabilities.yaml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")
    with pytest.raises(ValueError):
        load_upbit_capabilities(path)


def test_manifest_root_must_be_mapping(tmp_path: Path) -> None:
    path = tmp_path / "capabilities.yaml"
    path.write_text("- invalid\n", encoding="utf-8")
    with pytest.raises(ValueError, match="root"):
        load_upbit_capabilities(path)

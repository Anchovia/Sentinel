"""Hash-verified local model registry with no automatic promotion path."""

import os
import re
import shutil
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field

from quantforge.models.contracts import ModelArtifactMetadata

SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ModelRegistryError(ValueError):
    """Raised before an invalid or mutable model artifact enters the registry."""


class RegisteredModelArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: UUID
    model_version: str
    artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    metadata_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ModelRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root

    def register(
        self, metadata: ModelArtifactMetadata, artifact_bytes: bytes
    ) -> RegisteredModelArtifact:
        if not artifact_bytes:
            raise ModelRegistryError("model artifact cannot be empty")
        if not SAFE_VERSION.fullmatch(metadata.model_version):
            raise ModelRegistryError("model version is not path-safe")
        artifact_hash = sha256(artifact_bytes).hexdigest()
        if artifact_hash != metadata.artifact_hash:
            raise ModelRegistryError("model artifact hash does not match metadata")
        destination = self._destination(metadata.model_id, metadata.model_version)
        if destination.exists():
            raise ModelRegistryError("model artifact version is immutable and already exists")
        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / f".staging-{uuid4().hex}"
        metadata_bytes = (
            orjson.dumps(
                metadata.model_dump(mode="json"),
                option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
            )
            + b"\n"
        )
        metadata_hash = sha256(metadata_bytes).hexdigest()
        manifest_values = {
            "model_id": str(metadata.model_id),
            "model_version": metadata.model_version,
            "artifact_hash": artifact_hash,
            "metadata_hash": metadata_hash,
        }
        manifest_hash = sha256(
            orjson.dumps(manifest_values, option=orjson.OPT_SORT_KEYS)
        ).hexdigest()
        registered = RegisteredModelArtifact(
            **manifest_values,
            manifest_hash=manifest_hash,
        )
        try:
            staging.mkdir()
            (staging / "artifact.bin").write_bytes(artifact_bytes)
            (staging / "metadata.json").write_bytes(metadata_bytes)
            (staging / "manifest.json").write_bytes(
                orjson.dumps(
                    registered.model_dump(mode="json"),
                    option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
                )
                + b"\n"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return registered

    def load(
        self, model_id: UUID, model_version: str
    ) -> tuple[ModelArtifactMetadata, bytes, RegisteredModelArtifact]:
        destination = self._destination(model_id, model_version)
        try:
            artifact_bytes = (destination / "artifact.bin").read_bytes()
            metadata_bytes = (destination / "metadata.json").read_bytes()
            manifest = RegisteredModelArtifact.model_validate_json(
                (destination / "manifest.json").read_bytes()
            )
            metadata = ModelArtifactMetadata.model_validate_json(metadata_bytes)
        except (OSError, ValueError) as exc:
            raise ModelRegistryError("model registry entry is missing or malformed") from exc
        if manifest.model_id != model_id or manifest.model_version != model_version:
            raise ModelRegistryError("model registry path and manifest disagree")
        if sha256(artifact_bytes).hexdigest() != manifest.artifact_hash:
            raise ModelRegistryError("model artifact checksum failed")
        if sha256(metadata_bytes).hexdigest() != manifest.metadata_hash:
            raise ModelRegistryError("model metadata checksum failed")
        manifest_values = manifest.model_dump(exclude={"manifest_hash"}, mode="json")
        expected_manifest_hash = sha256(
            orjson.dumps(manifest_values, option=orjson.OPT_SORT_KEYS)
        ).hexdigest()
        if manifest.manifest_hash != expected_manifest_hash:
            raise ModelRegistryError("model manifest checksum failed")
        if metadata.artifact_hash != manifest.artifact_hash:
            raise ModelRegistryError("metadata and artifact manifest disagree")
        return metadata, artifact_bytes, manifest

    def _destination(self, model_id: UUID, model_version: str) -> Path:
        if not SAFE_VERSION.fullmatch(model_version):
            raise ModelRegistryError("model version is not path-safe")
        return self.root / str(model_id) / model_version

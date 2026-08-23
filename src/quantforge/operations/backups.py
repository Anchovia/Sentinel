"""Checksummed, Secret-excluding local backup and paper-only restore-drill proof."""

import os
import re
import shutil
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator

FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
_CREDENTIAL_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?i)\bbearer\s+[A-Za-z0-9._~+\-/]{32,}=*"),
    re.compile(rb"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(rb"(?m)^QF_UPBIT_(?:ACCESS|SECRET)_KEY\s*=\s*[^\s#][^\r\n]*$"),
)


class BackupError(ValueError):
    """Raised when a backup or restore proof is unsafe or unverifiable."""


class BackupObject(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class BackupManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "operations-backup-1"
    backup_id: str = Field(pattern=r"^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$")
    created_at_utc: datetime
    trading_mode: str = "paper"
    source_revision: str = Field(min_length=1, max_length=80)
    rpo_target_minutes: int = Field(gt=0)
    rto_target_minutes: int = Field(gt=0)
    objectives_measured: bool = False
    encrypted_by_external_storage: bool = False
    objects: tuple[BackupObject, ...]
    aggregate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("created_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("backup timestamp must be UTC-aware")
        return value


class LocalBackupManager:
    """Copies only explicitly selected workspace files into an integrity manifest.

    Encryption and off-host replication are intentionally external concerns. A local
    artifact with ``encrypted_by_external_storage=false`` is never production-ready.
    """

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    def create(
        self,
        sources: tuple[Path, ...],
        backup_root: Path,
        *,
        source_revision: str,
        created_at_utc: datetime,
        rpo_target_minutes: int = 15,
        rto_target_minutes: int = 60,
    ) -> Path:
        self._require_utc(created_at_utc)
        if not sources:
            raise BackupError("at least one explicit backup source is required")
        if backup_root.is_symlink():
            raise BackupError("symbolic links are not valid backup roots")
        resolved_backup_root = backup_root.resolve()
        for source in sources:
            resolved_source = source.resolve()
            if resolved_source.is_dir() and (
                resolved_backup_root == resolved_source
                or resolved_backup_root.is_relative_to(resolved_source)
            ):
                raise BackupError("backup destination cannot be nested inside a source directory")
        backup_id = f"{created_at_utc:%Y%m%dT%H%M%SZ}-{uuid4().hex[:12]}"
        backup_root.mkdir(parents=True, exist_ok=True)
        destination = backup_root / backup_id
        temporary = backup_root / f".{backup_id}.tmp"
        if destination.exists() or temporary.exists():
            raise BackupError("backup destination already exists")
        payload_root = temporary / "payload"
        payload_root.mkdir(parents=True)
        objects: list[BackupObject] = []
        try:
            for source in sorted(sources, key=lambda item: str(item)):
                for file_path in self._source_files(source):
                    relative = file_path.relative_to(self.workspace_root)
                    self._validate_relative_path(relative)
                    self._validate_file_content(file_path)
                    target = payload_root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(file_path, target, follow_symlinks=False)
                    objects.append(
                        BackupObject(
                            relative_path=relative.as_posix(),
                            size_bytes=target.stat().st_size,
                            sha256=self._file_hash(target),
                        )
                    )
            canonical = tuple(sorted(objects, key=lambda item: item.relative_path))
            if len({item.relative_path for item in canonical}) != len(canonical):
                raise BackupError("overlapping backup sources produced duplicate objects")
            manifest = BackupManifest(
                backup_id=backup_id,
                created_at_utc=created_at_utc,
                source_revision=source_revision,
                rpo_target_minutes=rpo_target_minutes,
                rto_target_minutes=rto_target_minutes,
                objects=canonical,
                aggregate_sha256=self._aggregate(canonical),
            )
            (temporary / "manifest.json").write_bytes(
                orjson.dumps(
                    manifest.model_dump(mode="json"),
                    option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
                )
                + b"\n"
            )
            os.replace(temporary, destination)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return destination

    def verify(self, backup_dir: Path) -> BackupManifest:
        if backup_dir.is_symlink():
            raise BackupError("symbolic links are not valid backup directories")
        resolved = backup_dir.resolve()
        manifest_path = resolved / "manifest.json"
        try:
            manifest = BackupManifest.model_validate(orjson.loads(manifest_path.read_bytes()))
        except (OSError, orjson.JSONDecodeError, ValueError) as exc:
            raise BackupError("backup manifest could not be validated") from exc
        if resolved.name != manifest.backup_id:
            raise BackupError("backup directory and manifest identifiers differ")
        if tuple(sorted(manifest.objects, key=lambda item: item.relative_path)) != manifest.objects:
            raise BackupError("backup objects are not canonically ordered")
        seen: set[str] = set()
        for item in manifest.objects:
            relative = Path(item.relative_path)
            self._validate_relative_path(relative)
            if item.relative_path in seen:
                raise BackupError("backup manifest contains duplicate objects")
            seen.add(item.relative_path)
            file_path = resolved / "payload" / relative
            if not file_path.is_file() or file_path.is_symlink():
                raise BackupError(f"backup object is missing or unsafe: {item.relative_path}")
            if (
                file_path.stat().st_size != item.size_bytes
                or self._file_hash(file_path) != item.sha256
            ):
                raise BackupError(f"backup object checksum failed: {item.relative_path}")
        actual_files = {
            path.relative_to(resolved / "payload").as_posix()
            for path in (resolved / "payload").rglob("*")
            if path.is_file()
        }
        if actual_files != seen:
            raise BackupError("backup payload contains unmanifested or missing objects")
        if self._aggregate(manifest.objects) != manifest.aggregate_sha256:
            raise BackupError("backup aggregate checksum failed")
        if manifest.trading_mode != "paper":
            raise BackupError("restore drills require a paper-only backup")
        return manifest

    def restore_drill(self, backup_dir: Path, target: Path) -> BackupManifest:
        manifest = self.verify(backup_dir)
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise BackupError("restore drill target must be a real directory")
        if target.exists() and any(target.iterdir()):
            raise BackupError("restore drill target must be empty")
        target.mkdir(parents=True, exist_ok=True)
        source_payload = backup_dir.resolve() / "payload"
        for item in manifest.objects:
            relative = Path(item.relative_path)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_payload / relative, destination, follow_symlinks=False)
        (target / "RESTORE_PAPER_ONLY").write_text(
            "This isolated restore proof has no credentials or order capability.\n",
            encoding="utf-8",
        )
        return manifest

    def _source_files(self, source: Path) -> tuple[Path, ...]:
        resolved = source.resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise BackupError("backup source must remain inside the workspace") from exc
        if source.is_symlink() or resolved.is_symlink():
            raise BackupError("symbolic links are not valid backup sources")
        if resolved.is_file():
            return (resolved,)
        if not resolved.is_dir():
            raise BackupError("backup source does not exist")
        files = tuple(path for path in resolved.rglob("*") if path.is_file())
        if any(path.is_symlink() for path in files):
            raise BackupError("symbolic links are not valid backup objects")
        return files

    @staticmethod
    def _validate_relative_path(relative: Path) -> None:
        if relative.is_absolute() or ".." in relative.parts:
            raise BackupError("backup object path escapes its root")
        lowered = {part.lower() for part in relative.parts}
        if lowered & {".git", "secrets"}:
            raise BackupError("repository metadata and Secret directories are forbidden")
        if (
            relative.name.lower() in FORBIDDEN_NAMES
            or relative.suffix.lower() in FORBIDDEN_SUFFIXES
        ):
            raise BackupError("credential-shaped files are forbidden from backups")

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate_file_content(path: Path) -> None:
        tail = b""
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                window = tail + chunk
                if any(pattern.search(window) for pattern in _CREDENTIAL_PATTERNS):
                    raise BackupError("credential-shaped content is forbidden from backups")
                tail = window[-8192:]

    @staticmethod
    def _aggregate(objects: tuple[BackupObject, ...]) -> str:
        payload = [item.model_dump(mode="json") for item in objects]
        return sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()

    @staticmethod
    def _require_utc(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise BackupError("backup timestamp must be UTC-aware")

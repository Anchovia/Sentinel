"""Repository-path and dedicated-worktree enforcement for scheduled automation."""

from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

import yaml
from pydantic import BaseModel, ConfigDict, Field

from quantforge.automation.contracts import AutomationActor, AutomationOutcome, AutomationReport


class AutomationBoundaryError(ValueError):
    """Raised before automation could cross a repository safety boundary."""


class ActorWriteRules(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: tuple[str, ...] = Field(min_length=1)
    denied: tuple[str, ...] = Field(min_length=1)


class WriteAllowlist(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^automation-write-allowlist-1$")
    work: ActorWriteRules
    codex: ActorWriteRules


class GitWorktreeState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dedicated: bool
    branch: str | None
    git_directory: Path
    common_git_directory: Path


def load_write_allowlist(path: Path) -> WriteAllowlist:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return WriteAllowlist.model_validate(payload)


def _matches(path: str, pattern: str) -> bool:
    normalized = PurePosixPath(path).as_posix()
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return normalized == prefix or normalized.startswith(f"{prefix}/")
    return fnmatchcase(normalized, pattern)


def assert_writes_allowed(report: AutomationReport, allowlist: WriteAllowlist) -> None:
    assert_paths_allowed(report.actor, report.writes, allowlist)


def assert_paths_allowed(
    actor: AutomationActor, paths: tuple[str, ...], allowlist: WriteAllowlist
) -> None:
    rules = allowlist.work if actor is AutomationActor.WORK else allowlist.codex
    for write in paths:
        if any(_matches(write, pattern) for pattern in rules.denied):
            raise AutomationBoundaryError(f"write path is explicitly denied: {write}")
        if not any(_matches(write, pattern) for pattern in rules.allowed):
            raise AutomationBoundaryError(f"write path is outside the allowlist: {write}")


def inspect_git_worktree(workspace_root: Path) -> GitWorktreeState:
    root = workspace_root.resolve()
    marker = root / ".git"
    if marker.is_dir():
        head = marker / "HEAD"
        return GitWorktreeState(
            dedicated=False,
            branch=_read_branch(head),
            git_directory=marker.resolve(),
            common_git_directory=marker.resolve(),
        )
    if not marker.is_file():
        raise AutomationBoundaryError("workspace is not a Git checkout")
    declaration = marker.read_text(encoding="utf-8").strip()
    if not declaration.startswith("gitdir: "):
        raise AutomationBoundaryError("linked worktree marker is malformed")
    declared = Path(declaration.removeprefix("gitdir: "))
    git_directory = (
        (root / declared).resolve() if not declared.is_absolute() else declared.resolve()
    )
    if not git_directory.is_dir():
        raise AutomationBoundaryError("linked worktree Git directory does not exist")
    common_marker = git_directory / "commondir"
    if not common_marker.is_file():
        raise AutomationBoundaryError("linked worktree common directory is missing")
    common_declared = Path(common_marker.read_text(encoding="utf-8").strip())
    common_git_directory = (
        (git_directory / common_declared).resolve()
        if not common_declared.is_absolute()
        else common_declared.resolve()
    )
    if common_git_directory == git_directory:
        raise AutomationBoundaryError("checkout is not isolated from the primary Git directory")
    return GitWorktreeState(
        dedicated=True,
        branch=_read_branch(git_directory / "HEAD"),
        git_directory=git_directory,
        common_git_directory=common_git_directory,
    )


def _read_branch(head_path: Path) -> str | None:
    if not head_path.is_file():
        raise AutomationBoundaryError("Git HEAD is missing")
    head = head_path.read_text(encoding="utf-8").strip()
    prefix = "ref: refs/heads/"
    return head.removeprefix(prefix) if head.startswith(prefix) else None


def assert_report_boundary(
    report: AutomationReport,
    allowlist: WriteAllowlist,
    workspace_root: Path,
) -> GitWorktreeState | None:
    assert_writes_allowed(report, allowlist)
    for write in report.writes:
        _assert_no_symlink_escape(workspace_root, write)
    if report.actor is AutomationActor.WORK:
        return None
    state = inspect_git_worktree(workspace_root)
    if not state.dedicated:
        raise AutomationBoundaryError("Codex scheduled work must run in a dedicated worktree")
    if report.outcome is AutomationOutcome.CHANGE_CANDIDATE and state.branch in {None, "main"}:
        raise AutomationBoundaryError(
            "a Codex change candidate requires a non-main branch in the dedicated worktree"
        )
    return state


def _assert_no_symlink_escape(workspace_root: Path, relative_path: str) -> None:
    root = workspace_root.resolve()
    candidate = root / PurePosixPath(relative_path)
    current = root
    for part in PurePosixPath(relative_path).parts:
        current /= part
        if current.is_symlink():
            raise AutomationBoundaryError(f"write path contains a symlink: {relative_path}")
    if not candidate.resolve(strict=False).is_relative_to(root):
        raise AutomationBoundaryError(f"write path escapes the workspace: {relative_path}")

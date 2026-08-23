"""Fail-closed contracts for report-only Work and isolated Codex automation."""

from quantforge.automation.contracts import (
    AutomationActor,
    AutomationOutcome,
    AutomationReport,
    AutomationSeverity,
    AutomationTrigger,
    SkillName,
    load_report,
    load_trigger,
)
from quantforge.automation.guard import (
    AutomationBoundaryError,
    WriteAllowlist,
    assert_paths_allowed,
    assert_report_boundary,
    inspect_git_worktree,
    load_write_allowlist,
)

__all__ = [
    "AutomationActor",
    "AutomationBoundaryError",
    "AutomationOutcome",
    "AutomationReport",
    "AutomationSeverity",
    "AutomationTrigger",
    "SkillName",
    "WriteAllowlist",
    "assert_paths_allowed",
    "assert_report_boundary",
    "inspect_git_worktree",
    "load_report",
    "load_trigger",
    "load_write_allowlist",
]

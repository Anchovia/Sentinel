from datetime import UTC, datetime, timedelta
from pathlib import Path

import orjson
import pytest
from typer.testing import CliRunner

from quantforge.cli import app
from quantforge.runtime import (
    PAPER_RECOVERY_CONFIRMATION,
    PaperRecoveryAcknowledgement,
    PaperRecoveryIntegrityError,
    PaperRecoveryReviewError,
    RealtimePaperOrchestrator,
    RealtimePaperRecoveryCheckpoint,
    create_paper_recovery_acknowledgement,
    pending_paper_recovery_acknowledgement_path,
    read_paper_recovery_acknowledgement,
    read_realtime_paper_recovery_checkpoint,
    validate_paper_recovery_acknowledgement,
    write_paper_recovery_acknowledgement,
    write_realtime_paper_recovery_checkpoint,
)

runner = CliRunner()
REVIEW_TIME = datetime(2026, 8, 25, 0, 0, tzinfo=UTC)


def _clean_blocked_checkpoint(path: Path) -> RealtimePaperRecoveryCheckpoint:
    orchestrator = RealtimePaperOrchestrator(("KRW-BTC",), recovery_path=path)
    orchestrator.begin_recovery_session(started_at_utc=REVIEW_TIME - timedelta(seconds=2))
    orchestrator.close(closed_at_utc=REVIEW_TIME - timedelta(seconds=1))
    clean = read_realtime_paper_recovery_checkpoint(path)
    values = {
        name: getattr(clean, name) for name in type(clean).model_fields if name != "checkpoint_hash"
    }
    values["recovery_blocked"] = True
    blocked = RealtimePaperRecoveryCheckpoint.create(**values)
    write_realtime_paper_recovery_checkpoint(blocked, path)
    return blocked


def _acknowledgement(
    checkpoint: RealtimePaperRecoveryCheckpoint,
    *,
    created_at_utc: datetime = REVIEW_TIME,
) -> PaperRecoveryAcknowledgement:
    return create_paper_recovery_acknowledgement(
        checkpoint,
        reviewer_ref="0123456789abcdef",
        approval_reference="incident-review-42",
        reason="Reconciled paper state reviewed for isolated simulation restart.",
        confirmation=PAPER_RECOVERY_CONFIRMATION,
        created_at_utc=created_at_utc,
        valid_for=timedelta(hours=1),
    )


def test_acknowledgement_requires_clean_blocked_checkpoint_and_exact_phrase(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state/realtime-paper-recovery.json"
    blocked = _clean_blocked_checkpoint(path)

    with pytest.raises(PaperRecoveryReviewError, match="confirmation phrase"):
        create_paper_recovery_acknowledgement(
            blocked,
            reviewer_ref="0123456789abcdef",
            approval_reference="incident-review-42",
            reason="Reconciled paper state reviewed for isolated simulation restart.",
            confirmation="yes",
            created_at_utc=REVIEW_TIME,
        )

    unblocked_values = {
        name: getattr(blocked, name)
        for name in type(blocked).model_fields
        if name != "checkpoint_hash"
    }
    unblocked_values["recovery_blocked"] = False
    unblocked = RealtimePaperRecoveryCheckpoint.create(**unblocked_values)
    with pytest.raises(PaperRecoveryReviewError, match="is not blocked"):
        _acknowledgement(unblocked)


def test_acknowledgement_is_hash_bound_short_lived_and_tamper_evident(tmp_path: Path) -> None:
    path = tmp_path / "state/realtime-paper-recovery.json"
    blocked = _clean_blocked_checkpoint(path)
    acknowledgement = _acknowledgement(blocked)
    pending = pending_paper_recovery_acknowledgement_path(path, blocked.checkpoint_hash)

    write_paper_recovery_acknowledgement(acknowledgement, pending)
    assert read_paper_recovery_acknowledgement(pending) == acknowledgement
    with pytest.raises(PaperRecoveryReviewError, match="not currently valid"):
        validate_paper_recovery_acknowledgement(
            acknowledgement,
            blocked,
            consumed_at_utc=REVIEW_TIME + timedelta(hours=2),
        )

    payload = orjson.loads(pending.read_bytes())
    payload["reason"] = "Tampered recovery rationale."
    pending.write_bytes(orjson.dumps(payload))
    with pytest.raises(PaperRecoveryIntegrityError):
        read_paper_recovery_acknowledgement(pending)


def test_cli_inspects_and_creates_pending_approval_without_clearing_block(tmp_path: Path) -> None:
    path = tmp_path / "state/realtime-paper-recovery.json"
    blocked = _clean_blocked_checkpoint(path)

    status = runner.invoke(app, ["paper-recovery-status", "--checkpoint", str(path)])
    assert status.exit_code == 0
    status_payload = orjson.loads(status.stdout)
    assert status_payload["eligible_for_acknowledgement"] is True
    assert status_payload["block_cleared"] is False

    approval = runner.invoke(
        app,
        [
            "approve-paper-recovery",
            "--checkpoint",
            str(path),
            "--reviewer-ref",
            "0123456789abcdef",
            "--approval-reference",
            "incident-review-42",
            "--reason",
            "Reconciled paper state reviewed for isolated simulation restart.",
            "--confirmation",
            PAPER_RECOVERY_CONFIRMATION,
        ],
    )
    assert approval.exit_code == 0
    approval_payload = orjson.loads(approval.stdout)
    assert approval_payload["block_cleared"] is False
    assert approval_payload["next_runtime_start_must_revalidate"] is True
    pending = pending_paper_recovery_acknowledgement_path(path, blocked.checkpoint_hash)
    assert pending.exists()
    assert read_realtime_paper_recovery_checkpoint(path).recovery_blocked is True

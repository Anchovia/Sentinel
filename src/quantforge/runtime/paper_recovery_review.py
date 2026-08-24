"""One-use, hash-bound human review for a blocked paper recovery checkpoint."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import OrderStatus
from quantforge.operations.exports import assert_runtime_export_safe
from quantforge.portfolio import AccountingInvariantError, PortfolioLedger
from quantforge.runtime.paper_recovery import (
    PaperRecoveryIntegrityError,
    RealtimePaperRecoveryCheckpoint,
)

PAPER_RECOVERY_CONFIRMATION = "CONFIRM CLEAR PAPER RECOVERY BLOCK"
MAX_ACKNOWLEDGEMENT_LIFETIME = timedelta(hours=24)
_TERMINAL_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
        OrderStatus.PREVENTED,
    }
)


class PaperRecoveryReviewError(ValueError):
    """A paper recovery acknowledgement or its clearance evidence was unsafe."""


class PaperRecoveryClearanceEvidence(BaseModel):
    """Reproducible facts required before a blocked paper checkpoint may resume."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["paper-recovery-clearance-evidence-1"] = (
        "paper-recovery-clearance-evidence-1"
    )
    verified_at_utc: datetime
    checkpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    broker_order_count: Annotated[int, Field(ge=0)]
    broker_fill_count: Annotated[int, Field(ge=0)]
    non_terminal_order_count: Literal[0] = 0
    unknown_order_count: Literal[0] = 0
    verified_ledger_count: Annotated[int, Field(ge=1)]
    reservation_count: Literal[0] = 0
    locked_cash_krw: Decimal = Field(default=Decimal(0), ge=0)
    position_market_count: Annotated[int, Field(ge=0)] = 0
    clean_shutdown_verified: Literal[True] = True
    recovery_block_verified: Literal[True] = True
    paper_only: Literal[True] = True
    network_used: Literal[False] = False
    order_submission_available: Literal[False] = False

    @field_validator("verified_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("paper recovery review timestamps must be UTC-aware")
        return value


class PaperRecoveryAcknowledgement(BaseModel):
    """Short-lived human approval bound to one exact blocked checkpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["paper-recovery-acknowledgement-1"] = "paper-recovery-acknowledgement-1"
    acknowledgement_id: UUID
    created_at_utc: datetime
    valid_until_utc: datetime
    reviewer_ref: str = Field(pattern=r"^[a-f0-9]{16}$")
    approval_reference: str = Field(min_length=3, max_length=80)
    reason: str = Field(min_length=10, max_length=500)
    checkpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    markets: tuple[str, ...] = Field(min_length=1)
    clearance: PaperRecoveryClearanceEvidence
    human_reviewed: Literal[True] = True
    clears_only_recovery_block: Literal[True] = True
    paper_only: Literal[True] = True
    network_used: Literal[False] = False
    order_submission_available: Literal[False] = False
    runtime_settings_changed: Literal[False] = False
    risk_limits_changed: Literal[False] = False
    model_approval_changed: Literal[False] = False
    acknowledgement_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def create(cls, **values: object) -> "PaperRecoveryAcknowledgement":
        normalized_values = cast(dict[str, Any], values)
        normalized = cls.model_construct(
            **normalized_values,
            acknowledgement_hash="0" * 64,
        ).model_dump(mode="json", exclude={"acknowledgement_hash"})
        return cls(**values, acknowledgement_hash=_calculate_hash(normalized))

    @field_validator("created_at_utc", "valid_until_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("paper recovery acknowledgement timestamps must be UTC-aware")
        return value

    @field_validator("approval_reference", "reason")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("paper recovery review text must be trimmed printable text")
        return value

    @model_validator(mode="after")
    def validate_acknowledgement(self) -> "PaperRecoveryAcknowledgement":
        if not self.created_at_utc < self.valid_until_utc:
            raise ValueError("paper recovery acknowledgement expiry is invalid")
        if self.valid_until_utc - self.created_at_utc > MAX_ACKNOWLEDGEMENT_LIFETIME:
            raise ValueError("paper recovery acknowledgement exceeds its maximum lifetime")
        if self.clearance.checkpoint_hash != self.checkpoint_hash:
            raise ValueError("paper recovery clearance is bound to another checkpoint")
        if len(self.markets) != len(set(self.markets)) or any(
            not market.startswith("KRW-") for market in self.markets
        ):
            raise ValueError("paper recovery acknowledgement markets are invalid")
        normalized = self.model_dump(mode="json", exclude={"acknowledgement_hash"})
        if self.acknowledgement_hash != _calculate_hash(normalized):
            raise ValueError("paper recovery acknowledgement hash is invalid")
        return self


class PaperRecoveryAcknowledgementReceipt(BaseModel):
    """Immutable proof that one acknowledgement cleared one checkpoint once."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["paper-recovery-acknowledgement-receipt-1"] = (
        "paper-recovery-acknowledgement-receipt-1"
    )
    consumed_at_utc: datetime
    acknowledgement_id: UUID
    acknowledgement_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_ref: str = Field(pattern=r"^[a-f0-9]{16}$")
    approval_reference: str = Field(min_length=3, max_length=80)
    blocked_checkpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resumed_checkpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    clearance: PaperRecoveryClearanceEvidence
    result: Literal["OPERATOR_ACKNOWLEDGED"] = "OPERATOR_ACKNOWLEDGED"
    paper_only: Literal[True] = True
    network_used: Literal[False] = False
    order_submission_available: Literal[False] = False
    runtime_settings_changed: Literal[False] = False
    risk_limits_changed: Literal[False] = False
    model_approval_changed: Literal[False] = False
    receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def create(cls, **values: object) -> "PaperRecoveryAcknowledgementReceipt":
        normalized_values = cast(dict[str, Any], values)
        normalized = cls.model_construct(
            **normalized_values,
            receipt_hash="0" * 64,
        ).model_dump(mode="json", exclude={"receipt_hash"})
        return cls(**values, receipt_hash=_calculate_hash(normalized))

    @field_validator("consumed_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("paper recovery receipt timestamps must be UTC-aware")
        return value

    @model_validator(mode="after")
    def validate_receipt(self) -> "PaperRecoveryAcknowledgementReceipt":
        if self.clearance.checkpoint_hash != self.blocked_checkpoint_hash:
            raise ValueError("paper recovery receipt clearance is bound to another checkpoint")
        normalized = self.model_dump(mode="json", exclude={"receipt_hash"})
        if self.receipt_hash != _calculate_hash(normalized):
            raise ValueError("paper recovery receipt hash is invalid")
        return self


def validate_paper_recovery_clearance(
    checkpoint: RealtimePaperRecoveryCheckpoint,
    *,
    verified_at_utc: datetime,
) -> PaperRecoveryClearanceEvidence:
    """Prove the runtime stopped cleanly after canceling every uncertain paper order."""

    if verified_at_utc.tzinfo is None or verified_at_utc.utcoffset() != UTC.utcoffset(
        verified_at_utc
    ):
        raise PaperRecoveryReviewError("paper recovery verification time must be UTC-aware")
    if not checkpoint.clean_shutdown:
        raise PaperRecoveryReviewError("paper runtime must be cleanly stopped before review")
    if not checkpoint.recovery_blocked:
        raise PaperRecoveryReviewError("paper recovery checkpoint is not blocked")

    non_terminal = tuple(
        item.order
        for item in checkpoint.broker.orders
        if item.order.status not in _TERMINAL_STATUSES
    )
    unknown = tuple(
        order
        for order in non_terminal
        if order.status in {OrderStatus.UNKNOWN, OrderStatus.RECONCILING}
    )
    reservations = sum(len(ledger.reservations) for ledger in checkpoint.ledgers)
    locked_cash = sum((ledger.locked_cash for ledger in checkpoint.ledgers), start=Decimal(0))
    if non_terminal or unknown or reservations or locked_cash != 0:
        raise PaperRecoveryReviewError(
            "paper recovery still has uncertain orders or reserved balances"
        )

    try:
        restored_ledgers = tuple(PortfolioLedger.from_state(state) for state in checkpoint.ledgers)
    except (AccountingInvariantError, ValueError) as exc:
        raise PaperRecoveryReviewError("paper recovery ledger revalidation failed") from exc

    return PaperRecoveryClearanceEvidence(
        verified_at_utc=verified_at_utc,
        checkpoint_hash=checkpoint.checkpoint_hash,
        broker_order_count=len(checkpoint.broker.orders),
        broker_fill_count=len(checkpoint.broker.fills),
        verified_ledger_count=len(restored_ledgers),
        position_market_count=sum(ledger.position_quantity > 0 for ledger in restored_ledgers),
    )


def create_paper_recovery_acknowledgement(
    checkpoint: RealtimePaperRecoveryCheckpoint,
    *,
    reviewer_ref: str,
    approval_reference: str,
    reason: str,
    confirmation: str,
    created_at_utc: datetime,
    valid_for: timedelta = timedelta(hours=1),
) -> PaperRecoveryAcknowledgement:
    """Create approval evidence without changing runtime state or enabling an order path."""

    if confirmation != PAPER_RECOVERY_CONFIRMATION:
        raise PaperRecoveryReviewError("paper recovery confirmation phrase did not match")
    if valid_for <= timedelta(0) or valid_for > MAX_ACKNOWLEDGEMENT_LIFETIME:
        raise PaperRecoveryReviewError("paper recovery acknowledgement lifetime is invalid")
    clearance = validate_paper_recovery_clearance(
        checkpoint,
        verified_at_utc=created_at_utc,
    )
    return PaperRecoveryAcknowledgement.create(
        acknowledgement_id=uuid4(),
        created_at_utc=created_at_utc,
        valid_until_utc=created_at_utc + valid_for,
        reviewer_ref=reviewer_ref,
        approval_reference=approval_reference,
        reason=reason,
        checkpoint_hash=checkpoint.checkpoint_hash,
        policy_hash=checkpoint.policy_hash,
        markets=checkpoint.markets,
        clearance=clearance,
    )


def validate_paper_recovery_acknowledgement(
    acknowledgement: PaperRecoveryAcknowledgement,
    checkpoint: RealtimePaperRecoveryCheckpoint,
    *,
    consumed_at_utc: datetime,
) -> PaperRecoveryClearanceEvidence:
    """Revalidate a pending approval against the exact checkpoint at consumption time."""

    if not acknowledgement.created_at_utc <= consumed_at_utc <= acknowledgement.valid_until_utc:
        raise PaperRecoveryReviewError("paper recovery acknowledgement is not currently valid")
    if (
        acknowledgement.checkpoint_hash != checkpoint.checkpoint_hash
        or acknowledgement.policy_hash != checkpoint.policy_hash
        or acknowledgement.markets != checkpoint.markets
    ):
        raise PaperRecoveryReviewError("paper recovery acknowledgement binding does not match")
    current = validate_paper_recovery_clearance(
        checkpoint,
        verified_at_utc=consumed_at_utc,
    )
    if current.model_dump(exclude={"verified_at_utc"}) != acknowledgement.clearance.model_dump(
        exclude={"verified_at_utc"}
    ):
        raise PaperRecoveryReviewError("paper recovery clearance facts changed after review")
    return current


def pending_paper_recovery_acknowledgement_path(
    checkpoint_path: Path,
    checkpoint_hash: str,
) -> Path:
    return (
        checkpoint_path.parent / "recovery-acknowledgements" / "pending" / f"{checkpoint_hash}.json"
    )


def consumed_paper_recovery_receipt_path(
    checkpoint_path: Path,
    acknowledgement_id: UUID,
) -> Path:
    return (
        checkpoint_path.parent
        / "recovery-acknowledgements"
        / "consumed"
        / f"{acknowledgement_id}.json"
    )


def write_paper_recovery_acknowledgement(
    acknowledgement: PaperRecoveryAcknowledgement,
    path: Path,
) -> Path:
    return _write_hash_bound_json(
        acknowledgement,
        path,
        identity_field="acknowledgement_hash",
    )


def read_paper_recovery_acknowledgement(path: Path) -> PaperRecoveryAcknowledgement:
    return _read_hash_bound_json(path, PaperRecoveryAcknowledgement)


def write_paper_recovery_acknowledgement_receipt(
    receipt: PaperRecoveryAcknowledgementReceipt,
    path: Path,
) -> Path:
    return _write_hash_bound_json(receipt, path, identity_field="receipt_hash")


def read_paper_recovery_acknowledgement_receipt(
    path: Path,
) -> PaperRecoveryAcknowledgementReceipt:
    return _read_hash_bound_json(path, PaperRecoveryAcknowledgementReceipt)


def _write_hash_bound_json(
    value: BaseModel,
    path: Path,
    *,
    identity_field: str,
) -> Path:
    payload = value.model_dump(mode="json")
    assert_runtime_export_safe(payload)
    if path.exists():
        if _existing_review_file_matches(path, payload, identity_field=identity_field):
            return path
        raise PaperRecoveryIntegrityError("paper recovery review file already exists")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    encoded = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    try:
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if _existing_review_file_matches(path, payload, identity_field=identity_field):
                return path
            raise PaperRecoveryIntegrityError("paper recovery review file already exists") from None
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _existing_review_file_matches(
    path: Path,
    expected: dict[str, object],
    *,
    identity_field: str,
) -> bool:
    try:
        existing = orjson.loads(path.read_bytes())
        assert_runtime_export_safe(existing)
        if not isinstance(existing, dict):
            raise ValueError("paper recovery review payload must be an object")
    except (OSError, orjson.JSONDecodeError, ValueError) as exc:
        raise PaperRecoveryIntegrityError("paper recovery review file is unreadable") from exc
    return existing.get(identity_field) == expected[identity_field] and existing == expected


def _read_hash_bound_json[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        payload = orjson.loads(path.read_bytes())
        assert_runtime_export_safe(payload)
        return model.model_validate(payload)
    except (OSError, orjson.JSONDecodeError, ValueError) as exc:
        raise PaperRecoveryIntegrityError(
            "paper recovery review file could not be safely loaded"
        ) from exc


def _calculate_hash(values: dict[str, object]) -> str:
    return sha256(
        orjson.dumps(
            values,
            default=str,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
        )
    ).hexdigest()

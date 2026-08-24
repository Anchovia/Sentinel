"""Hash-bound paper execution checkpoints with fail-closed restart semantics."""

import os
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.domain import OrderStatus
from quantforge.execution.paper import PaperBrokerState
from quantforge.operations.exports import assert_runtime_export_safe
from quantforge.portfolio.ledger import LedgerRecordType, PortfolioLedgerState


class PaperRecoveryIntegrityError(ValueError):
    """A paper checkpoint was corrupt, incompatible, or unsafe to resume."""


class PaperRecoveryStatus(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NEW = "NEW"
    VERIFIED_CLEAN = "VERIFIED_CLEAN"
    EMPTY_UNCLEAN_RECOVERED = "EMPTY_UNCLEAN_RECOVERED"
    UNCLEAN_RECONCILED = "UNCLEAN_RECONCILED"
    OPERATOR_ACKNOWLEDGED = "OPERATOR_ACKNOWLEDGED"


class RealtimePaperRecoveryCheckpoint(BaseModel):
    """Complete durable economic state; transient orderbook state is intentionally excluded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["realtime-paper-recovery-1"] = "realtime-paper-recovery-1"
    generated_at_utc: datetime
    clean_shutdown: bool
    recovery_blocked: bool = False
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    markets: tuple[str, ...] = Field(min_length=1)
    broker: PaperBrokerState
    ledgers: tuple[PortfolioLedgerState, ...]
    latest_marks: tuple[tuple[str, Decimal], ...] = ()
    peak_equities: tuple[tuple[str, Decimal], ...]
    processed_events: Annotated[int, Field(ge=0)] = 0
    feature_ready_frames: Annotated[int, Field(ge=0)] = 0
    inference_frames: Annotated[int, Field(ge=0)] = 0
    strategy_trade_proposals: Annotated[int, Field(ge=0)] = 0
    risk_approvals: Annotated[int, Field(ge=0)] = 0
    risk_rejections: Annotated[int, Field(ge=0)] = 0
    submission_rejections: Annotated[int, Field(ge=0)] = 0
    paper_orders: Annotated[int, Field(ge=0)] = 0
    paper_fills: Annotated[int, Field(ge=0)] = 0
    turnover_krw: Decimal = Field(ge=0)
    first_event_at_utc: datetime | None = None
    last_event_at_utc: datetime | None = None
    last_event_id: UUID | None = None
    order_times: tuple[datetime, ...] = ()
    market_order_times: tuple[tuple[str, tuple[datetime, ...]], ...] = ()
    decision_state: str = Field(min_length=1)
    decision_reason: str = Field(min_length=1)
    latest_strategy_id: str | None = None
    latest_reason_codes: tuple[str, ...] = ()
    checkpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def create(cls, **values: object) -> "RealtimePaperRecoveryCheckpoint":
        normalized_values = cast(dict[str, Any], values)
        normalized = cls.model_construct(**normalized_values, checkpoint_hash="0" * 64).model_dump(
            mode="json", exclude={"checkpoint_hash"}
        )
        return cls(**values, checkpoint_hash=cls._calculate_hash(normalized))

    @field_validator(
        "generated_at_utc",
        "first_event_at_utc",
        "last_event_at_utc",
        mode="after",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError("paper recovery timestamps must be UTC-aware")
        return value

    @field_validator("order_times")
    @classmethod
    def validate_order_times(cls, values: tuple[datetime, ...]) -> tuple[datetime, ...]:
        if any(
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value) for value in values
        ):
            raise ValueError("paper recovery order times must be UTC-aware")
        if values != tuple(sorted(values)):
            raise ValueError("paper recovery order times must be sorted")
        return values

    @model_validator(mode="after")
    def validate_checkpoint(self) -> "RealtimePaperRecoveryCheckpoint":
        normalized = self.model_dump(mode="json", exclude={"checkpoint_hash"})
        if self.checkpoint_hash != self._calculate_hash(normalized):
            raise ValueError("paper recovery checkpoint hash is invalid")
        if len(self.markets) != len(set(self.markets)) or any(
            not market.startswith("KRW-") for market in self.markets
        ):
            raise ValueError("paper recovery markets are invalid")
        ledger_markets = tuple(ledger.market for ledger in self.ledgers)
        if ledger_markets != self.markets:
            raise ValueError("paper recovery ledgers do not match the market universe")
        self._validate_market_pairs("latest marks", self.latest_marks, require_all=False)
        self._validate_market_pairs("peak equities", self.peak_equities, require_all=True)
        market_time_names = tuple(name for name, _ in self.market_order_times)
        if market_time_names != self.markets:
            raise ValueError("paper recovery market order windows do not match the universe")
        for _, values in self.market_order_times:
            self.validate_order_times(values)
        if (self.first_event_at_utc is None) != (self.last_event_at_utc is None):
            raise ValueError("paper recovery event time bounds are incomplete")
        if self.first_event_at_utc is not None and (
            self.last_event_at_utc < self.first_event_at_utc  # type: ignore[operator]
            or self.last_event_id is None
        ):
            raise ValueError("paper recovery event cursor is invalid")
        if self.first_event_at_utc is None and self.last_event_id is not None:
            raise ValueError("paper recovery event identity has no time bounds")
        if self.paper_orders != len(self.broker.orders) or self.paper_fills != len(
            self.broker.fills
        ):
            raise ValueError("paper recovery counters do not reconcile with broker state")
        if self.turnover_krw != sum(
            (fill.notional for fill in self.broker.fills), start=Decimal(0)
        ):
            raise ValueError("paper recovery turnover does not reconcile")
        for ledger in self.ledgers:
            broker_fill_ids = {
                fill.fill_id for fill in self.broker.fills if fill.market == ledger.market
            }
            ledger_fill_ids = {
                record.fill_id
                for record in ledger.records
                if record.record_type is LedgerRecordType.FILL and record.fill_id is not None
            }
            if broker_fill_ids != ledger_fill_ids:
                raise ValueError("paper broker fills do not reconcile with portfolio ledger")
        if self.clean_shutdown:
            active = {
                OrderStatus.SUBMITTED,
                OrderStatus.ACKNOWLEDGED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.CANCEL_PENDING,
            }
            if any(item.order.status in active for item in self.broker.orders) or any(
                ledger.reservations for ledger in self.ledgers
            ):
                raise ValueError("clean paper checkpoint cannot contain open orders or locks")
        return self

    def _validate_market_pairs(
        self,
        label: str,
        values: tuple[tuple[str, Decimal], ...],
        *,
        require_all: bool,
    ) -> None:
        names = tuple(name for name, _ in values)
        expected = (
            self.markets
            if require_all
            else tuple(market for market in self.markets if market in set(names))
        )
        if names != expected or any(value <= 0 for _, value in values):
            raise ValueError(f"paper recovery {label} are invalid")

    @staticmethod
    def _calculate_hash(values: dict[str, object]) -> str:
        return sha256(
            orjson.dumps(
                values,
                default=str,
                option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
            )
        ).hexdigest()


def write_realtime_paper_recovery_checkpoint(
    checkpoint: RealtimePaperRecoveryCheckpoint,
    path: Path,
) -> Path:
    """Atomically persist one already verified, Secret-free recovery checkpoint."""

    payload = checkpoint.model_dump(mode="json")
    assert_runtime_export_safe(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    encoded = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    try:
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def read_realtime_paper_recovery_checkpoint(
    path: Path,
) -> RealtimePaperRecoveryCheckpoint:
    try:
        payload = orjson.loads(path.read_bytes())
        assert_runtime_export_safe(payload)
        return RealtimePaperRecoveryCheckpoint.model_validate(payload)
    except (OSError, orjson.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, PaperRecoveryIntegrityError):
            raise
        raise PaperRecoveryIntegrityError(
            "paper recovery checkpoint could not be safely loaded"
        ) from exc

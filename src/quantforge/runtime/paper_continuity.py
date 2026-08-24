"""Durable paper-runtime session continuity without claiming exchange completeness."""

import os
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantforge.operations.exports import assert_runtime_export_safe

ZERO_HASH = "0" * 64
SIX_HOURS = timedelta(hours=6)
TWELVE_HOURS = timedelta(hours=12)


class PaperContinuityIntegrity(StrEnum):
    NEW = "NEW"
    VERIFIED = "VERIFIED"
    DEGRADED = "DEGRADED"


class PaperSessionState(StrEnum):
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class PaperSessionOutcome(StrEnum):
    NO_PRIOR_SESSION = "NO_PRIOR_SESSION"
    CLEAN_STOP = "CLEAN_STOP"
    FAILED_STOP = "FAILED_STOP"
    UNEXPECTED_INTERRUPTION = "UNEXPECTED_INTERRUPTION"
    UNKNOWN = "UNKNOWN"


class PaperRuntimeGapKind(StrEnum):
    NONE = "NONE"
    STARTUP = "STARTUP"
    WEBSOCKET_DISCONNECTED = "WEBSOCKET_DISCONNECTED"
    DATA_STALE = "DATA_STALE"


class PaperSessionEventType(StrEnum):
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_STOPPED = "SESSION_STOPPED"
    SESSION_FAILED = "SESSION_FAILED"
    UNEXPECTED_INTERRUPTION = "UNEXPECTED_INTERRUPTION"
    GAP_STARTED = "GAP_STARTED"
    GAP_ENDED = "GAP_ENDED"
    RECONNECT_OBSERVED = "RECONNECT_OBSERVED"


class PaperContinuityError(ValueError):
    """Durable continuity evidence was corrupt or internally contradictory."""


class PaperRuntimeSessionEvent(BaseModel):
    """One immutable hash-chain event in the local paper session ledger."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["paper-runtime-session-event-1"] = "paper-runtime-session-event-1"
    sequence: Annotated[int, Field(ge=1)]
    recorded_at_utc: datetime
    run_id: UUID
    event_type: PaperSessionEventType
    related_run_id: UUID | None = None
    gap_kind: PaperRuntimeGapKind = PaperRuntimeGapKind.NONE
    duration_seconds: float | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, min_length=1, max_length=100)
    failure_type: str | None = Field(default=None, min_length=1, max_length=100)
    reconnect_delta: Annotated[int, Field(ge=0)] = 0
    previous_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    paper_only: Literal[True] = True
    authentication_used: Literal[False] = False
    order_submission_available: Literal[False] = False
    live_submission_allowed: Literal[False] = False

    @classmethod
    def create(cls, **values: object) -> "PaperRuntimeSessionEvent":
        normalized_values = cast(dict[str, Any], values)
        normalized = cls.model_construct(
            **normalized_values,
            record_hash=ZERO_HASH,
        ).model_dump(mode="json", exclude={"record_hash"})
        return cls(**values, record_hash=_calculate_hash(normalized))

    @field_validator("recorded_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        _require_utc(value)
        return value

    @model_validator(mode="after")
    def validate_event(self) -> "PaperRuntimeSessionEvent":
        normalized = self.model_dump(mode="json", exclude={"record_hash"})
        if self.record_hash != _calculate_hash(normalized):
            raise ValueError("paper continuity event hash is invalid")
        if self.event_type in {
            PaperSessionEventType.GAP_STARTED,
            PaperSessionEventType.GAP_ENDED,
        } and self.gap_kind not in {
            PaperRuntimeGapKind.WEBSOCKET_DISCONNECTED,
            PaperRuntimeGapKind.DATA_STALE,
        }:
            raise ValueError("paper continuity gap event has no measurable gap kind")
        if self.event_type is PaperSessionEventType.GAP_ENDED and self.duration_seconds is None:
            raise ValueError("paper continuity gap end requires a duration")
        if self.event_type is PaperSessionEventType.UNEXPECTED_INTERRUPTION and (
            self.related_run_id is None or self.duration_seconds is None
        ):
            raise ValueError("unexpected paper interruption requires prior run and downtime")
        if self.event_type is PaperSessionEventType.RECONNECT_OBSERVED:
            if self.reconnect_delta < 1:
                raise ValueError("paper reconnect event requires a positive delta")
        elif self.reconnect_delta:
            raise ValueError("only paper reconnect events may carry a reconnect delta")
        return self


class PaperRuntimeContinuityLease(BaseModel):
    """Atomically refreshed last-known state used to detect a missing terminal record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["paper-runtime-continuity-lease-1"] = "paper-runtime-continuity-lease-1"
    run_id: UUID
    started_at_utc: datetime
    updated_at_utc: datetime
    state: PaperSessionState
    websocket_connected: bool
    last_event_at_utc: datetime | None = None
    reconnect_count: Annotated[int, Field(ge=0)] = 0
    websocket_gap_count: Annotated[int, Field(ge=0)] = 0
    stale_data_gap_count: Annotated[int, Field(ge=0)] = 0
    current_gap_kind: PaperRuntimeGapKind = PaperRuntimeGapKind.STARTUP
    current_gap_started_at_utc: datetime | None = None
    longest_gap_seconds: float = Field(default=0, ge=0)
    shutdown_reason: str | None = Field(default=None, min_length=1, max_length=100)
    failure_type: str | None = Field(default=None, min_length=1, max_length=100)
    lease_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def create(cls, **values: object) -> "PaperRuntimeContinuityLease":
        normalized_values = cast(dict[str, Any], values)
        normalized = cls.model_construct(
            **normalized_values,
            lease_hash=ZERO_HASH,
        ).model_dump(mode="json", exclude={"lease_hash"})
        return cls(**values, lease_hash=_calculate_hash(normalized))

    @field_validator(
        "started_at_utc",
        "updated_at_utc",
        "last_event_at_utc",
        "current_gap_started_at_utc",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            _require_utc(value)
        return value

    @model_validator(mode="after")
    def validate_lease(self) -> "PaperRuntimeContinuityLease":
        normalized = self.model_dump(mode="json", exclude={"lease_hash"})
        if self.lease_hash != _calculate_hash(normalized):
            raise ValueError("paper continuity lease hash is invalid")
        if self.updated_at_utc < self.started_at_utc:
            raise ValueError("paper continuity lease update precedes its start")
        measured_gap = self.current_gap_kind in {
            PaperRuntimeGapKind.WEBSOCKET_DISCONNECTED,
            PaperRuntimeGapKind.DATA_STALE,
        }
        if measured_gap != (self.current_gap_started_at_utc is not None):
            raise ValueError("paper continuity current gap bounds are invalid")
        if self.state is PaperSessionState.ACTIVE and (
            self.shutdown_reason is not None or self.failure_type is not None
        ):
            raise ValueError("active paper continuity lease cannot be terminal")
        if self.state is not PaperSessionState.ACTIVE and not self.shutdown_reason:
            raise ValueError("terminal paper continuity lease requires a reason")
        return self


class PaperRuntimeContinuitySnapshot(BaseModel):
    """Small Work/monitor view of process-level continuity and observed feed gaps."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["paper-runtime-continuity-1"] = "paper-runtime-continuity-1"
    generated_at_utc: datetime
    measurement_started_at_utc: datetime
    current_run_id: UUID
    current_session_state: PaperSessionState
    current_session_started_at_utc: datetime
    current_session_uptime_seconds: float = Field(ge=0)
    integrity: PaperContinuityIntegrity
    history_event_count: Annotated[int, Field(ge=0)]
    session_count: Annotated[int, Field(ge=1)]
    clean_stop_count: Annotated[int, Field(ge=0)]
    failed_stop_count: Annotated[int, Field(ge=0)]
    unexpected_interruption_count: Annotated[int, Field(ge=0)]
    previous_session_outcome: PaperSessionOutcome
    last_shutdown_at_utc: datetime | None = None
    last_shutdown_reason: str | None = None
    websocket_connected: bool
    last_event_at_utc: datetime | None = None
    event_fresh: bool
    reconnect_count: Annotated[int, Field(ge=0)]
    websocket_gap_count: Annotated[int, Field(ge=0)]
    stale_data_gap_count: Annotated[int, Field(ge=0)]
    current_gap_kind: PaperRuntimeGapKind
    current_gap_duration_seconds: float = Field(ge=0)
    longest_current_session_gap_seconds: float = Field(ge=0)
    six_hour_baseline_ready: bool
    twelve_hour_baseline_ready: bool
    six_hour_limitations: tuple[str, ...]
    twelve_hour_limitations: tuple[str, ...]
    exchange_gap_completeness_claimed: Literal[False] = False
    paper_only: Literal[True] = True
    authentication_used: Literal[False] = False
    order_submission_available: Literal[False] = False
    live_submission_allowed: Literal[False] = False

    @field_validator(
        "generated_at_utc",
        "measurement_started_at_utc",
        "current_session_started_at_utc",
        "last_shutdown_at_utc",
        "last_event_at_utc",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            _require_utc(value)
        return value

    @model_validator(mode="after")
    def validate_readiness(self) -> "PaperRuntimeContinuitySnapshot":
        if self.measurement_started_at_utc > self.generated_at_utc:
            raise ValueError("paper continuity measurement starts in the future")
        if self.six_hour_baseline_ready != (not self.six_hour_limitations):
            raise ValueError("paper six-hour readiness contradicts its limitations")
        if self.twelve_hour_baseline_ready != (not self.twelve_hour_limitations):
            raise ValueError("paper twelve-hour readiness contradicts its limitations")
        return self


class PaperRuntimeContinuityTracker:
    """Single-process writer for durable session, interruption, and observed-gap evidence."""

    def __init__(
        self,
        state_root: Path,
        *,
        run_id: UUID,
        started_at_utc: datetime,
        stale_after_seconds: float,
    ) -> None:
        _require_utc(started_at_utc)
        if stale_after_seconds <= 0:
            raise ValueError("paper continuity stale threshold must be positive")
        self.state_root = state_root
        self.ledger_path = state_root / "paper-runtime-session-ledger.jsonl"
        self.lease_path = state_root / "paper-runtime-continuity-lease.json"
        self.run_id = run_id
        self.started_at_utc = started_at_utc
        self.stale_after_seconds = stale_after_seconds
        self._events: list[PaperRuntimeSessionEvent] = []
        self._lease: PaperRuntimeContinuityLease | None = None
        self._integrity = PaperContinuityIntegrity.NEW
        self._write_enabled = True
        self._previous_outcome = PaperSessionOutcome.NO_PRIOR_SESSION
        self._last_shutdown_at_utc: datetime | None = None
        self._last_shutdown_reason: str | None = None
        self._started = False

    def start(self) -> PaperRuntimeContinuitySnapshot:
        if self._started:
            raise PaperContinuityError("paper continuity session already started")
        self._load_history()
        prior_lease = self._load_prior_lease()
        unclosed = self._latest_unclosed_run()
        if prior_lease is not None and unclosed is not None and unclosed != prior_lease.run_id:
            self._record_unexpected_without_lease(
                unclosed,
                reason="terminal_record_missing_without_matching_lease",
            )
        elif prior_lease is not None:
            self._classify_prior_lease(prior_lease)
        elif unclosed is not None:
            self._record_unexpected_without_lease(
                unclosed,
                reason="terminal_record_missing_without_lease",
            )
        self._append_event(
            recorded_at_utc=self.started_at_utc,
            event_type=PaperSessionEventType.SESSION_STARTED,
            reason="paper_runtime_started",
        )
        self._lease = PaperRuntimeContinuityLease.create(
            run_id=self.run_id,
            started_at_utc=self.started_at_utc,
            updated_at_utc=self.started_at_utc,
            state=PaperSessionState.ACTIVE,
            websocket_connected=False,
        )
        self._write_lease()
        self._started = True
        return self.snapshot(generated_at_utc=self.started_at_utc)

    def observe(
        self,
        *,
        observed_at_utc: datetime,
        websocket_connected: bool,
        last_event_at_utc: datetime | None,
        reconnect_count: int,
    ) -> PaperRuntimeContinuitySnapshot:
        lease = self._require_active()
        _require_utc(observed_at_utc)
        if last_event_at_utc is not None:
            _require_utc(last_event_at_utc)
        if observed_at_utc < lease.updated_at_utc or reconnect_count < lease.reconnect_count:
            raise PaperContinuityError("paper continuity observation regressed")

        new_gap = self._classify_gap(
            observed_at_utc,
            websocket_connected=websocket_connected,
            last_event_at_utc=last_event_at_utc,
        )
        websocket_gaps = lease.websocket_gap_count
        stale_gaps = lease.stale_data_gap_count
        longest_gap = lease.longest_gap_seconds
        gap_started = lease.current_gap_started_at_utc
        if new_gap != lease.current_gap_kind:
            if lease.current_gap_kind in {
                PaperRuntimeGapKind.WEBSOCKET_DISCONNECTED,
                PaperRuntimeGapKind.DATA_STALE,
            }:
                if gap_started is None:
                    raise PaperContinuityError("paper continuity active gap has no start")
                duration = max(0.0, (observed_at_utc - gap_started).total_seconds())
                longest_gap = max(longest_gap, duration)
                self._append_event(
                    recorded_at_utc=observed_at_utc,
                    event_type=PaperSessionEventType.GAP_ENDED,
                    gap_kind=lease.current_gap_kind,
                    duration_seconds=duration,
                    reason="observed_state_transition",
                )
            gap_started = None
            if new_gap in {
                PaperRuntimeGapKind.WEBSOCKET_DISCONNECTED,
                PaperRuntimeGapKind.DATA_STALE,
            }:
                gap_started = observed_at_utc
                websocket_gaps += int(new_gap is PaperRuntimeGapKind.WEBSOCKET_DISCONNECTED)
                stale_gaps += int(new_gap is PaperRuntimeGapKind.DATA_STALE)
                self._append_event(
                    recorded_at_utc=observed_at_utc,
                    event_type=PaperSessionEventType.GAP_STARTED,
                    gap_kind=new_gap,
                    reason="heartbeat_observation",
                )

        reconnect_delta = reconnect_count - lease.reconnect_count
        if reconnect_delta:
            self._append_event(
                recorded_at_utc=observed_at_utc,
                event_type=PaperSessionEventType.RECONNECT_OBSERVED,
                reconnect_delta=reconnect_delta,
                reason="public_websocket_reconnect_counter_increased",
            )
        self._lease = PaperRuntimeContinuityLease.create(
            run_id=self.run_id,
            started_at_utc=lease.started_at_utc,
            updated_at_utc=observed_at_utc,
            state=PaperSessionState.ACTIVE,
            websocket_connected=websocket_connected,
            last_event_at_utc=last_event_at_utc,
            reconnect_count=reconnect_count,
            websocket_gap_count=websocket_gaps,
            stale_data_gap_count=stale_gaps,
            current_gap_kind=new_gap,
            current_gap_started_at_utc=gap_started,
            longest_gap_seconds=longest_gap,
        )
        self._write_lease()
        return self.snapshot(generated_at_utc=observed_at_utc)

    def stop(
        self,
        *,
        stopped_at_utc: datetime,
        failed: bool,
        shutdown_reason: str,
        failure_type: str | None,
        last_event_at_utc: datetime | None,
        reconnect_count: int,
    ) -> PaperRuntimeContinuitySnapshot:
        lease = self._require_active()
        _require_utc(stopped_at_utc)
        if stopped_at_utc < lease.updated_at_utc:
            raise PaperContinuityError("paper continuity stop precedes its last heartbeat")
        longest_gap = lease.longest_gap_seconds
        if lease.current_gap_kind in {
            PaperRuntimeGapKind.WEBSOCKET_DISCONNECTED,
            PaperRuntimeGapKind.DATA_STALE,
        }:
            if lease.current_gap_started_at_utc is None:
                raise PaperContinuityError("paper continuity stop found an unbounded gap")
            duration = max(
                0.0,
                (stopped_at_utc - lease.current_gap_started_at_utc).total_seconds(),
            )
            longest_gap = max(longest_gap, duration)
            self._append_event(
                recorded_at_utc=stopped_at_utc,
                event_type=PaperSessionEventType.GAP_ENDED,
                gap_kind=lease.current_gap_kind,
                duration_seconds=duration,
                reason="paper_runtime_stopped",
            )
        terminal_event = (
            PaperSessionEventType.SESSION_FAILED
            if failed
            else PaperSessionEventType.SESSION_STOPPED
        )
        self._append_event(
            recorded_at_utc=stopped_at_utc,
            event_type=terminal_event,
            reason=shutdown_reason,
            failure_type=failure_type,
        )
        self._lease = PaperRuntimeContinuityLease.create(
            run_id=self.run_id,
            started_at_utc=lease.started_at_utc,
            updated_at_utc=stopped_at_utc,
            state=PaperSessionState.FAILED if failed else PaperSessionState.STOPPED,
            websocket_connected=False,
            last_event_at_utc=last_event_at_utc,
            reconnect_count=reconnect_count,
            websocket_gap_count=lease.websocket_gap_count,
            stale_data_gap_count=lease.stale_data_gap_count,
            current_gap_kind=PaperRuntimeGapKind.NONE,
            longest_gap_seconds=longest_gap,
            shutdown_reason=shutdown_reason,
            failure_type=failure_type,
        )
        self._write_lease()
        self._last_shutdown_at_utc = stopped_at_utc
        self._last_shutdown_reason = shutdown_reason
        return self.snapshot(generated_at_utc=stopped_at_utc)

    def snapshot(self, *, generated_at_utc: datetime) -> PaperRuntimeContinuitySnapshot:
        lease = self._require_started()
        _require_utc(generated_at_utc)
        uptime = max(0.0, (generated_at_utc - lease.started_at_utc).total_seconds())
        current_gap_duration = (
            max(0.0, (generated_at_utc - lease.current_gap_started_at_utc).total_seconds())
            if lease.current_gap_started_at_utc is not None
            else 0.0
        )
        event_fresh = (
            lease.last_event_at_utc is not None
            and (generated_at_utc - lease.last_event_at_utc).total_seconds()
            <= self.stale_after_seconds
        )
        six_limitations = self._baseline_limitations(
            lease,
            uptime_seconds=uptime,
            horizon=SIX_HOURS,
            websocket_connected=lease.websocket_connected,
            event_fresh=event_fresh,
        )
        twelve_limitations = self._baseline_limitations(
            lease,
            uptime_seconds=uptime,
            horizon=TWELVE_HOURS,
            websocket_connected=lease.websocket_connected,
            event_fresh=event_fresh,
        )
        measurement_start = min(
            (
                event.recorded_at_utc
                for event in self._events
                if event.event_type is PaperSessionEventType.SESSION_STARTED
            ),
            default=lease.started_at_utc,
        )
        return PaperRuntimeContinuitySnapshot(
            generated_at_utc=generated_at_utc,
            measurement_started_at_utc=measurement_start,
            current_run_id=self.run_id,
            current_session_state=lease.state,
            current_session_started_at_utc=lease.started_at_utc,
            current_session_uptime_seconds=uptime,
            integrity=self._integrity,
            history_event_count=len(self._events),
            session_count=max(
                1,
                sum(
                    event.event_type is PaperSessionEventType.SESSION_STARTED
                    for event in self._events
                ),
            ),
            clean_stop_count=sum(
                event.event_type is PaperSessionEventType.SESSION_STOPPED for event in self._events
            ),
            failed_stop_count=sum(
                event.event_type is PaperSessionEventType.SESSION_FAILED for event in self._events
            ),
            unexpected_interruption_count=sum(
                event.event_type is PaperSessionEventType.UNEXPECTED_INTERRUPTION
                for event in self._events
            ),
            previous_session_outcome=self._previous_outcome,
            last_shutdown_at_utc=self._last_shutdown_at_utc,
            last_shutdown_reason=self._last_shutdown_reason,
            websocket_connected=lease.websocket_connected,
            last_event_at_utc=lease.last_event_at_utc,
            event_fresh=event_fresh,
            reconnect_count=lease.reconnect_count,
            websocket_gap_count=lease.websocket_gap_count,
            stale_data_gap_count=lease.stale_data_gap_count,
            current_gap_kind=lease.current_gap_kind,
            current_gap_duration_seconds=current_gap_duration,
            longest_current_session_gap_seconds=max(
                lease.longest_gap_seconds,
                current_gap_duration,
            ),
            six_hour_baseline_ready=not six_limitations,
            twelve_hour_baseline_ready=not twelve_limitations,
            six_hour_limitations=six_limitations,
            twelve_hour_limitations=twelve_limitations,
        )

    def _load_history(self) -> None:
        if not self.ledger_path.exists():
            self._integrity = PaperContinuityIntegrity.NEW
            return
        try:
            previous = ZERO_HASH
            for expected_sequence, line in enumerate(self.ledger_path.read_bytes().splitlines(), 1):
                if not line:
                    continue
                payload = orjson.loads(line)
                assert_runtime_export_safe(payload)
                event = PaperRuntimeSessionEvent.model_validate(payload)
                if event.sequence != expected_sequence or event.previous_hash != previous:
                    raise PaperContinuityError("paper continuity ledger chain is invalid")
                self._events.append(event)
                previous = event.record_hash
            self._integrity = PaperContinuityIntegrity.VERIFIED
            self._restore_last_shutdown()
        except (OSError, orjson.JSONDecodeError, ValueError) as exc:
            self._events.clear()
            self._integrity = PaperContinuityIntegrity.DEGRADED
            self._write_enabled = False
            if isinstance(exc, PaperContinuityError):
                return

    def _load_prior_lease(self) -> PaperRuntimeContinuityLease | None:
        if not self.lease_path.exists():
            return None
        try:
            payload = orjson.loads(self.lease_path.read_bytes())
            assert_runtime_export_safe(payload)
            return PaperRuntimeContinuityLease.model_validate(payload)
        except (OSError, orjson.JSONDecodeError, ValueError):
            self._integrity = PaperContinuityIntegrity.DEGRADED
            self._write_enabled = False
            self._previous_outcome = PaperSessionOutcome.UNKNOWN
            return None

    def _classify_prior_lease(self, prior: PaperRuntimeContinuityLease) -> None:
        if prior.run_id == self.run_id:
            self._integrity = PaperContinuityIntegrity.DEGRADED
            self._write_enabled = False
            self._previous_outcome = PaperSessionOutcome.UNKNOWN
            return
        ledger_terminal_state = self._ledger_terminal_state(prior.run_id)
        if prior.state is PaperSessionState.ACTIVE:
            if self._latest_unclosed_run() != prior.run_id:
                self._degrade_contradictory_prior_lease()
                return
        elif ledger_terminal_state is not prior.state:
            self._degrade_contradictory_prior_lease()
            return
        self._last_shutdown_at_utc = prior.updated_at_utc
        self._last_shutdown_reason = prior.shutdown_reason
        if prior.state is PaperSessionState.STOPPED:
            self._previous_outcome = PaperSessionOutcome.CLEAN_STOP
        elif prior.state is PaperSessionState.FAILED:
            self._previous_outcome = PaperSessionOutcome.FAILED_STOP
        else:
            self._previous_outcome = PaperSessionOutcome.UNEXPECTED_INTERRUPTION
            self._last_shutdown_reason = "terminal_record_missing"
            downtime = max(0.0, (self.started_at_utc - prior.updated_at_utc).total_seconds())
            self._append_event(
                recorded_at_utc=self.started_at_utc,
                event_type=PaperSessionEventType.UNEXPECTED_INTERRUPTION,
                related_run_id=prior.run_id,
                duration_seconds=downtime,
                reason="terminal_record_missing",
            )

    def _record_unexpected_without_lease(self, run_id: UUID, *, reason: str) -> None:
        self._previous_outcome = PaperSessionOutcome.UNEXPECTED_INTERRUPTION
        self._last_shutdown_at_utc = self.started_at_utc
        self._last_shutdown_reason = reason
        self._append_event(
            recorded_at_utc=self.started_at_utc,
            event_type=PaperSessionEventType.UNEXPECTED_INTERRUPTION,
            related_run_id=run_id,
            duration_seconds=0.0,
            reason=reason,
        )

    def _ledger_terminal_state(self, run_id: UUID) -> PaperSessionState | None:
        for event in reversed(self._events):
            if event.run_id != run_id:
                continue
            if event.event_type is PaperSessionEventType.SESSION_STOPPED:
                return PaperSessionState.STOPPED
            if event.event_type is PaperSessionEventType.SESSION_FAILED:
                return PaperSessionState.FAILED
            if event.event_type is PaperSessionEventType.SESSION_STARTED:
                return None
        return None

    def _degrade_contradictory_prior_lease(self) -> None:
        self._integrity = PaperContinuityIntegrity.DEGRADED
        self._write_enabled = False
        self._previous_outcome = PaperSessionOutcome.UNKNOWN
        self._last_shutdown_reason = "lease_ledger_state_mismatch"

    def _latest_unclosed_run(self) -> UUID | None:
        opened: dict[UUID, bool] = {}
        for event in self._events:
            if event.event_type is PaperSessionEventType.SESSION_STARTED:
                opened[event.run_id] = True
            elif event.event_type in {
                PaperSessionEventType.SESSION_STOPPED,
                PaperSessionEventType.SESSION_FAILED,
            }:
                opened[event.run_id] = False
            elif (
                event.event_type is PaperSessionEventType.UNEXPECTED_INTERRUPTION
                and event.related_run_id is not None
            ):
                opened[event.related_run_id] = False
        return next((run_id for run_id, active in reversed(tuple(opened.items())) if active), None)

    def _restore_last_shutdown(self) -> None:
        for event in reversed(self._events):
            if event.event_type in {
                PaperSessionEventType.SESSION_STOPPED,
                PaperSessionEventType.SESSION_FAILED,
                PaperSessionEventType.UNEXPECTED_INTERRUPTION,
            }:
                self._last_shutdown_at_utc = event.recorded_at_utc
                self._last_shutdown_reason = event.reason
                return

    def _classify_gap(
        self,
        observed_at_utc: datetime,
        *,
        websocket_connected: bool,
        last_event_at_utc: datetime | None,
    ) -> PaperRuntimeGapKind:
        if last_event_at_utc is None:
            if (observed_at_utc - self.started_at_utc).total_seconds() > self.stale_after_seconds:
                return PaperRuntimeGapKind.DATA_STALE
            return PaperRuntimeGapKind.STARTUP
        if not websocket_connected:
            return PaperRuntimeGapKind.WEBSOCKET_DISCONNECTED
        if (observed_at_utc - last_event_at_utc).total_seconds() > self.stale_after_seconds:
            return PaperRuntimeGapKind.DATA_STALE
        return PaperRuntimeGapKind.NONE

    def _baseline_limitations(
        self,
        lease: PaperRuntimeContinuityLease,
        *,
        uptime_seconds: float,
        horizon: timedelta,
        websocket_connected: bool,
        event_fresh: bool,
    ) -> tuple[str, ...]:
        limitations: list[str] = []
        if self._integrity is PaperContinuityIntegrity.DEGRADED:
            limitations.append("CONTINUITY_INTEGRITY_DEGRADED")
        if lease.state is not PaperSessionState.ACTIVE:
            limitations.append("RUNTIME_NOT_ACTIVE")
        if uptime_seconds < horizon.total_seconds():
            limitations.append("HORIZON_NOT_REACHED")
        if not websocket_connected:
            limitations.append("WEBSOCKET_NOT_CONNECTED")
        if not event_fresh:
            limitations.append("LATEST_EVENT_NOT_FRESH")
        if lease.websocket_gap_count:
            limitations.append("WEBSOCKET_GAP_OBSERVED")
        if lease.stale_data_gap_count:
            limitations.append("STALE_DATA_GAP_OBSERVED")
        if lease.reconnect_count:
            limitations.append("RECONNECT_OBSERVED")
        return tuple(limitations)

    def _append_event(
        self,
        *,
        recorded_at_utc: datetime,
        event_type: PaperSessionEventType,
        related_run_id: UUID | None = None,
        gap_kind: PaperRuntimeGapKind = PaperRuntimeGapKind.NONE,
        duration_seconds: float | None = None,
        reason: str | None = None,
        failure_type: str | None = None,
        reconnect_delta: int = 0,
    ) -> None:
        if not self._write_enabled:
            return
        previous = self._events[-1].record_hash if self._events else ZERO_HASH
        event = PaperRuntimeSessionEvent.create(
            sequence=len(self._events) + 1,
            recorded_at_utc=recorded_at_utc,
            run_id=self.run_id,
            event_type=event_type,
            related_run_id=related_run_id,
            gap_kind=gap_kind,
            duration_seconds=duration_seconds,
            reason=reason,
            failure_type=failure_type,
            reconnect_delta=reconnect_delta,
            previous_hash=previous,
        )
        payload = event.model_dump(mode="json")
        assert_runtime_export_safe(payload)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS) + b"\n"
        with self.ledger_path.open("ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        self._events.append(event)
        if self._integrity is PaperContinuityIntegrity.NEW and len(self._events) > 1:
            self._integrity = PaperContinuityIntegrity.VERIFIED

    def _write_lease(self) -> None:
        if not self._write_enabled or self._lease is None:
            return
        _write_atomic_model(self._lease, self.lease_path)

    def _require_started(self) -> PaperRuntimeContinuityLease:
        if self._lease is None:
            raise PaperContinuityError("paper continuity session has not started")
        return self._lease

    def _require_active(self) -> PaperRuntimeContinuityLease:
        lease = self._require_started()
        if not self._started or lease.state is not PaperSessionState.ACTIVE:
            raise PaperContinuityError("paper continuity session is not active")
        return lease


def write_paper_runtime_continuity_snapshot(
    snapshot: PaperRuntimeContinuitySnapshot,
    output_root: Path,
) -> Path:
    destination = output_root / "ops" / "paper-continuity.json"
    return _write_atomic_model(snapshot, destination)


def read_paper_runtime_continuity_snapshot(path: Path) -> PaperRuntimeContinuitySnapshot:
    try:
        payload = orjson.loads(path.read_bytes())
        assert_runtime_export_safe(payload)
        return PaperRuntimeContinuitySnapshot.model_validate(payload)
    except (OSError, orjson.JSONDecodeError, ValueError) as exc:
        raise PaperContinuityError("paper continuity snapshot could not be loaded") from exc


def read_paper_runtime_session_ledger(path: Path) -> tuple[PaperRuntimeSessionEvent, ...]:
    events: list[PaperRuntimeSessionEvent] = []
    previous = ZERO_HASH
    try:
        for expected, line in enumerate(path.read_bytes().splitlines(), 1):
            if not line:
                continue
            payload = orjson.loads(line)
            assert_runtime_export_safe(payload)
            event = PaperRuntimeSessionEvent.model_validate(payload)
            if event.sequence != expected or event.previous_hash != previous:
                raise PaperContinuityError("paper continuity ledger chain is invalid")
            events.append(event)
            previous = event.record_hash
    except (OSError, orjson.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, PaperContinuityError):
            raise
        raise PaperContinuityError("paper continuity ledger could not be loaded") from exc
    return tuple(events)


def _write_atomic_model(value: BaseModel, path: Path) -> Path:
    payload = value.model_dump(mode="json")
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


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("paper continuity timestamps must be UTC-aware")


def _calculate_hash(values: dict[str, object]) -> str:
    return sha256(
        orjson.dumps(
            values,
            default=str,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
        )
    ).hexdigest()

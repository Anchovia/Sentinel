from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import orjson
import pytest

from factories import BASE_TIME, make_orderbook_event, make_trade_event
from quantforge.features import FeatureSnapshot
from quantforge.models import AlphaPrediction, DecisionAction, ModelReleaseStatus
from quantforge.runtime.paper_recovery import (
    PaperRecoveryStatus,
    read_realtime_paper_recovery_checkpoint,
    write_realtime_paper_recovery_checkpoint,
)
from quantforge.runtime.paper_recovery_review import (
    PAPER_RECOVERY_CONFIRMATION,
    consumed_paper_recovery_receipt_path,
    create_paper_recovery_acknowledgement,
    pending_paper_recovery_acknowledgement_path,
    read_paper_recovery_acknowledgement_receipt,
    write_paper_recovery_acknowledgement,
)
from quantforge.runtime.realtime_decision import (
    RealtimeAlphaModel,
    RealtimeModelApproval,
    RealtimePaperBlocked,
    RealtimePaperDecisionPolicy,
    RealtimePaperDecisionState,
    RealtimePaperOrchestrator,
    read_realtime_paper_decision_snapshot,
    write_realtime_paper_decision_snapshot,
)
from quantforge.runtime.realtime_pipeline import RealtimeFeatureFrame, RealtimePaperPipeline
from quantforge.strategies import (
    OrderPreference,
    StrategyAction,
    StrategyDecision,
    StrategyInput,
    StrategyRouteConfig,
    StrategyStatus,
)


class _ApprovedAlpha(RealtimeAlphaModel):
    model_version = "approved-test-alpha-1"
    artifact_hash = sha256(b"approved-test-alpha-1").hexdigest()

    def predict(
        self,
        frame: RealtimeFeatureFrame,
        features: FeatureSnapshot,
        *,
        predicted_at_utc,
        estimated_round_trip_cost_bps: Decimal,
    ) -> AlphaPrediction:
        gross = estimated_round_trip_cost_bps + Decimal("18")
        return AlphaPrediction(
            prediction_id=frame.frame_id,
            market=frame.market,
            predicted_at_utc=predicted_at_utc,
            valid_until_utc=predicted_at_utc + timedelta(seconds=5),
            horizon_seconds=5,
            p_down=0.05,
            p_neutral=0.05,
            p_up=0.9,
            expected_gross_return_bps=gross,
            estimated_round_trip_cost_bps=estimated_round_trip_cost_bps,
            expected_net_return_bps=Decimal("18"),
            prediction_interval_bps=(Decimal("5"), Decimal("25")),
            uncertainty=0.1,
            confidence=0.9,
            action=DecisionAction.TRADE,
            feature_snapshot_hash=features.snapshot_hash,
            model_version=self.model_version,
            artifact_hash=self.artifact_hash,
        )


class _FixedProposal:
    strategy_id = "approved-test-strategy"
    strategy_version = "1.0.0"

    def evaluate(self, inputs: StrategyInput) -> StrategyDecision:
        return StrategyDecision(
            decision_id=inputs.alpha.prediction_id,
            action=StrategyAction.TRADE,
            market=inputs.market.market,
            side="bid",
            target_notional=Decimal("10000"),
            order_preference=OrderPreference.BEST,
            expected_horizon_seconds=5,
            expected_gross_edge_bps=inputs.alpha.expected_gross_return_bps,
            expected_cost_bps=inputs.alpha.estimated_round_trip_cost_bps,
            expected_net_edge_bps=inputs.alpha.expected_net_return_bps,
            confidence=inputs.alpha.confidence,
            uncertainty=inputs.alpha.uncertainty,
            decided_at_utc=inputs.decision_at_utc,
            valid_until_utc=inputs.alpha.valid_until_utc,
            invalidation_conditions=("NEW_MARKET_EVENT",),
            exit_plan="fixture-only deterministic paper exit",
            reason_codes=("APPROVED_TEST_PROPOSAL",),
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
        )


def _approval(model: _ApprovedAlpha | None = None) -> RealtimeModelApproval:
    selected = model or _ApprovedAlpha()
    return RealtimeModelApproval(
        approval_reference="human-reviewed-test-fixture",
        approved_by="test-operator",
        approved_at_utc=BASE_TIME - timedelta(minutes=20),
        valid_until_utc=BASE_TIME + timedelta(days=1),
        model_created_at_utc=BASE_TIME - timedelta(minutes=30),
        market_scope=("KRW-BTC",),
        model_version=selected.model_version,
        artifact_hash=selected.artifact_hash,
    )


def _approved_policy() -> RealtimePaperDecisionPolicy:
    base = RealtimePaperDecisionPolicy.conservative_default()
    return base.model_copy(
        update={
            "paper_order_simulation_enabled": True,
            "routes": (
                StrategyRouteConfig(
                    strategy_id=_FixedProposal.strategy_id,
                    status=StrategyStatus.ACTIVE,
                    priority=100,
                    correlation_group="approved-test",
                    capacity_notional=Decimal("20000"),
                    cooldown_seconds=30,
                    max_strategy_loss=Decimal("10000"),
                ),
            ),
        }
    )


def _events():  # type: ignore[no-untyped-def]
    return (
        make_orderbook_event(
            sequence=1,
            received_offset_ms=0,
            asks=(("100.05", 1000),),
            bids=(("99.95", 1000),),
        ),
        make_trade_event(sequence=2, exchange_offset_ms=10, received_offset_ms=10),
        make_trade_event(
            sequence=3,
            exchange_offset_ms=20,
            received_offset_ms=20,
            price=101,
        ),
        make_orderbook_event(
            sequence=4,
            received_offset_ms=120,
            asks=(("100.05", 1000),),
            bids=(("99.95", 1000),),
        ),
    )


def test_unapproved_runtime_runs_neutral_inference_and_never_proposes_order() -> None:
    features = RealtimePaperPipeline(("KRW-BTC",))
    orchestrator = RealtimePaperOrchestrator(("KRW-BTC",))
    for event in _events():
        orchestrator.process(event, features.process(event))

    snapshot = orchestrator.snapshot(generated_at_utc=_events()[-1].received_at_utc)

    assert snapshot.inference_frames > 0
    assert snapshot.decision_state is RealtimePaperDecisionState.HOLD
    assert snapshot.decision_reason == "NO_APPROVED_ALPHA_MODEL"
    assert snapshot.model_release_status is ModelReleaseStatus.EXPERIMENTAL
    assert snapshot.model_approval_valid is False
    assert snapshot.paper_order_simulation_enabled is False
    assert snapshot.strategy_trade_proposals == 0
    assert snapshot.risk_approvals == 0
    assert snapshot.paper_orders == 0
    assert snapshot.paper_fills == 0
    assert snapshot.real_order_submission_available is False
    assert snapshot.live_submission_allowed is False


def test_approved_fixture_must_cross_strategy_risk_broker_and_ledger() -> None:
    model = _ApprovedAlpha()
    features = RealtimePaperPipeline(("KRW-BTC",))
    orchestrator = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        policy=_approved_policy(),
        alpha_model=model,
        approval=_approval(model),
        strategies=(_FixedProposal(),),
    )
    events = _events()
    for event in events:
        orchestrator.process(event, features.process(event))

    snapshot = orchestrator.snapshot(generated_at_utc=events[-1].received_at_utc)

    assert snapshot.model_approval_valid is True
    assert snapshot.strategy_trade_proposals == 1
    assert snapshot.risk_approvals == 1
    assert snapshot.risk_rejections == 0
    assert snapshot.paper_orders == 1
    assert snapshot.paper_fills == 1
    assert snapshot.decision_state is RealtimePaperDecisionState.PAPER_FILL
    assert snapshot.portfolios[0].position_quantity > 0
    assert snapshot.portfolios[0].cash_balance < snapshot.portfolios[0].initial_cash
    assert snapshot.ledger_records >= 7
    assert snapshot.real_order_submission_available is False


def test_model_and_human_approval_must_match_exactly() -> None:
    model = _ApprovedAlpha()
    approval = _approval(model).model_copy(update={"artifact_hash": "f" * 64})

    with pytest.raises(RealtimePaperBlocked, match="does not match"):
        RealtimePaperOrchestrator(
            ("KRW-BTC",),
            alpha_model=model,
            approval=approval,
        )


def test_approved_model_still_requires_separate_paper_order_gate() -> None:
    model = _ApprovedAlpha()
    disabled = _approved_policy().model_copy(update={"paper_order_simulation_enabled": False})
    features = RealtimePaperPipeline(("KRW-BTC",))
    orchestrator = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        policy=disabled,
        alpha_model=model,
        approval=_approval(model),
        strategies=(_FixedProposal(),),
    )
    for event in _events()[:3]:
        orchestrator.process(event, features.process(event))

    snapshot = orchestrator.snapshot(generated_at_utc=_events()[2].received_at_utc)

    assert snapshot.model_approval_valid is True
    assert snapshot.paper_order_simulation_enabled is False
    assert snapshot.risk_rejections == 0
    assert snapshot.decision_reason == "PAPER_ORDER_SIMULATION_DISABLED"
    assert snapshot.paper_orders == 0
    assert snapshot.paper_fills == 0


def test_decision_snapshot_is_atomic_and_secret_free(tmp_path: Path) -> None:
    features = RealtimePaperPipeline(("KRW-BTC",))
    orchestrator = RealtimePaperOrchestrator(("KRW-BTC",))
    for event in _events()[:3]:
        orchestrator.process(event, features.process(event))
    snapshot = orchestrator.snapshot(generated_at_utc=_events()[2].received_at_utc)

    path = write_realtime_paper_decision_snapshot(snapshot, tmp_path)

    assert read_realtime_paper_decision_snapshot(path) == snapshot
    payload = orjson.loads(path.read_bytes())
    assert payload["authentication_used"] is False
    assert payload["real_order_submission_available"] is False
    assert "approved_by" not in path.read_text(encoding="utf-8")
    assert list(path.parent.glob("*.tmp")) == []


def test_clean_checkpoint_restores_exact_paper_position_and_counters(tmp_path: Path) -> None:
    checkpoint = tmp_path / "state/realtime-paper-recovery.json"
    model = _ApprovedAlpha()
    features = RealtimePaperPipeline(("KRW-BTC",))
    orchestrator = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        policy=_approved_policy(),
        alpha_model=model,
        approval=_approval(model),
        strategies=(_FixedProposal(),),
        recovery_path=checkpoint,
    )
    orchestrator.begin_recovery_session(started_at_utc=BASE_TIME - timedelta(seconds=1))
    events = _events()
    for event in events:
        orchestrator.process(event, features.process(event))
    before = orchestrator.snapshot(generated_at_utc=events[-1].received_at_utc)
    orchestrator.close(closed_at_utc=events[-1].received_at_utc + timedelta(seconds=1))

    restored = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        policy=_approved_policy(),
        alpha_model=model,
        approval=_approval(model),
        strategies=(_FixedProposal(),),
        recovery_path=checkpoint,
    )
    restored.begin_recovery_session(
        started_at_utc=events[-1].received_at_utc + timedelta(seconds=2)
    )
    after = restored.snapshot(generated_at_utc=events[-1].received_at_utc + timedelta(seconds=2))

    assert after.recovery_status is PaperRecoveryStatus.VERIFIED_CLEAN
    assert after.recovery_blocked is False
    assert after.paper_order_simulation_enabled is True
    assert after.paper_orders == before.paper_orders == 1
    assert after.paper_fills == before.paper_fills == 1
    assert after.turnover_krw == before.turnover_krw
    assert after.portfolios[0].cash_balance == before.portfolios[0].cash_balance
    assert after.portfolios[0].position_quantity == before.portfolios[0].position_quantity
    restored.close(closed_at_utc=events[-1].received_at_utc + timedelta(seconds=3))


def test_unclean_checkpoint_cancels_open_order_releases_cash_and_blocks_gate(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "state/realtime-paper-recovery.json"
    model = _ApprovedAlpha()
    features = RealtimePaperPipeline(("KRW-BTC",))
    interrupted = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        policy=_approved_policy(),
        alpha_model=model,
        approval=_approval(model),
        strategies=(_FixedProposal(),),
        recovery_path=checkpoint,
    )
    interrupted.begin_recovery_session(started_at_utc=BASE_TIME - timedelta(seconds=1))
    events = _events()
    for event in events[:3]:
        interrupted.process(event, features.process(event))
    interrupted_snapshot = interrupted.snapshot(generated_at_utc=events[2].received_at_utc)
    assert interrupted_snapshot.paper_orders == 1
    assert interrupted_snapshot.paper_fills == 0
    assert interrupted_snapshot.portfolios[0].locked_cash > 0

    recovered = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        policy=_approved_policy(),
        alpha_model=model,
        approval=_approval(model),
        strategies=(_FixedProposal(),),
        recovery_path=checkpoint,
    )
    recovered.begin_recovery_session(
        started_at_utc=events[2].received_at_utc + timedelta(seconds=1)
    )
    snapshot = recovered.snapshot(generated_at_utc=events[2].received_at_utc + timedelta(seconds=1))

    assert snapshot.recovery_status is PaperRecoveryStatus.UNCLEAN_RECONCILED
    assert snapshot.recovery_blocked is True
    assert snapshot.paper_order_simulation_enabled is False
    assert snapshot.decision_reason == "PAPER_RECOVERY_BLOCKED"
    assert snapshot.paper_orders == 1
    assert snapshot.paper_fills == 0
    assert snapshot.portfolios[0].locked_cash == 0
    assert snapshot.portfolios[0].available_cash == snapshot.portfolios[0].cash_balance
    recovered.close(closed_at_utc=events[2].received_at_utc + timedelta(seconds=2))


def test_clean_blocked_checkpoint_requires_one_use_review_before_gate_resumes(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "state/realtime-paper-recovery.json"
    model = _ApprovedAlpha()
    features = RealtimePaperPipeline(("KRW-BTC",))
    interrupted = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        policy=_approved_policy(),
        alpha_model=model,
        approval=_approval(model),
        strategies=(_FixedProposal(),),
        recovery_path=checkpoint,
    )
    interrupted.begin_recovery_session(started_at_utc=BASE_TIME - timedelta(seconds=1))
    events = _events()
    for event in events[:3]:
        interrupted.process(event, features.process(event))

    reconciled = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        policy=_approved_policy(),
        alpha_model=model,
        approval=_approval(model),
        strategies=(_FixedProposal(),),
        recovery_path=checkpoint,
    )
    reconciled.begin_recovery_session(
        started_at_utc=events[2].received_at_utc + timedelta(seconds=1)
    )
    reconciled.close(closed_at_utc=events[2].received_at_utc + timedelta(seconds=2))

    blocked = read_realtime_paper_recovery_checkpoint(checkpoint)
    acknowledgement = create_paper_recovery_acknowledgement(
        blocked,
        reviewer_ref="0123456789abcdef",
        approval_reference="incident-review-42",
        reason="Reconciled paper state reviewed for isolated simulation restart.",
        confirmation=PAPER_RECOVERY_CONFIRMATION,
        created_at_utc=events[2].received_at_utc + timedelta(seconds=3),
    )
    pending = pending_paper_recovery_acknowledgement_path(
        checkpoint,
        blocked.checkpoint_hash,
    )
    write_paper_recovery_acknowledgement(acknowledgement, pending)

    resumed = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        policy=_approved_policy(),
        alpha_model=model,
        approval=_approval(model),
        strategies=(_FixedProposal(),),
        recovery_path=checkpoint,
    )
    resumed.begin_recovery_session(started_at_utc=events[2].received_at_utc + timedelta(seconds=4))
    snapshot = resumed.snapshot(generated_at_utc=events[2].received_at_utc + timedelta(seconds=4))

    assert snapshot.recovery_status is PaperRecoveryStatus.OPERATOR_ACKNOWLEDGED
    assert snapshot.recovery_blocked is False
    assert snapshot.paper_order_simulation_enabled is True
    assert snapshot.decision_reason == "PAPER_RECOVERY_OPERATOR_ACKNOWLEDGED"
    assert not pending.exists()
    receipt_path = consumed_paper_recovery_receipt_path(
        checkpoint,
        acknowledgement.acknowledgement_id,
    )
    receipt = read_paper_recovery_acknowledgement_receipt(receipt_path)
    assert receipt.blocked_checkpoint_hash == blocked.checkpoint_hash
    assert receipt.acknowledgement_hash == acknowledgement.acknowledgement_hash
    assert receipt.result == "OPERATOR_ACKNOWLEDGED"
    resumed.close(closed_at_utc=events[2].received_at_utc + timedelta(seconds=5))

    write_realtime_paper_recovery_checkpoint(blocked, checkpoint)
    write_paper_recovery_acknowledgement(acknowledgement, pending)
    replayed = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        policy=_approved_policy(),
        alpha_model=model,
        approval=_approval(model),
        strategies=(_FixedProposal(),),
        recovery_path=checkpoint,
    )
    replayed.begin_recovery_session(started_at_utc=events[2].received_at_utc + timedelta(seconds=6))
    replayed_snapshot = replayed.snapshot(
        generated_at_utc=events[2].received_at_utc + timedelta(seconds=6)
    )
    assert replayed_snapshot.recovery_status is PaperRecoveryStatus.UNCLEAN_RECONCILED
    assert replayed_snapshot.recovery_blocked is True
    assert replayed_snapshot.paper_order_simulation_enabled is False
    assert replayed_snapshot.decision_reason.startswith("PAPER_RECOVERY_ACKNOWLEDGEMENT_REJECTED_")


def test_empty_unapproved_unclean_checkpoint_recovers_without_permanent_block(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "state/realtime-paper-recovery.json"
    interrupted = RealtimePaperOrchestrator(("KRW-BTC",), recovery_path=checkpoint)
    interrupted.begin_recovery_session(started_at_utc=BASE_TIME)

    recovered = RealtimePaperOrchestrator(("KRW-BTC",), recovery_path=checkpoint)
    recovered.begin_recovery_session(started_at_utc=BASE_TIME + timedelta(seconds=1))
    snapshot = recovered.snapshot(generated_at_utc=BASE_TIME + timedelta(seconds=1))

    assert snapshot.recovery_status is PaperRecoveryStatus.EMPTY_UNCLEAN_RECOVERED
    assert snapshot.recovery_blocked is False
    assert snapshot.paper_order_simulation_enabled is False
    assert snapshot.paper_orders == 0
    assert snapshot.paper_fills == 0
    recovered.close(closed_at_utc=BASE_TIME + timedelta(seconds=2))


def test_tampered_recovery_checkpoint_fails_closed(tmp_path: Path) -> None:
    checkpoint = tmp_path / "state/realtime-paper-recovery.json"
    orchestrator = RealtimePaperOrchestrator(
        ("KRW-BTC",),
        recovery_path=checkpoint,
    )
    orchestrator.begin_recovery_session(started_at_utc=BASE_TIME)
    orchestrator.close(closed_at_utc=BASE_TIME + timedelta(seconds=1))
    payload = orjson.loads(checkpoint.read_bytes())
    payload["turnover_krw"] = "1"
    checkpoint.write_bytes(orjson.dumps(payload))

    with pytest.raises(RealtimePaperBlocked, match="restore failed"):
        RealtimePaperOrchestrator(("KRW-BTC",), recovery_path=checkpoint)

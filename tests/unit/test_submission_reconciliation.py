from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from factories import BASE_TIME
from quantforge.config import QuantForgeSettings, TradingMode
from quantforge.domain import (
    ExchangeOrderRequest,
    ExchangeOrderType,
    OrderChance,
    OrderStatus,
    OrderTestResult,
    RemoteOrderSnapshot,
    RemoteOrderState,
    RiskDecision,
    RiskDecisionType,
)
from quantforge.exchange import (
    DisabledPrivateOrderPort,
    FakePrivateOrderPort,
    MockOnlyOrderTestAdapter,
    PrivateExchangeDisabled,
    PrivateTransportTimeout,
)
from quantforge.execution import (
    BalanceObservation,
    DisabledLiveOrderAdapter,
    ExecutionReconciler,
    JournalSource,
    LiveExecutionUnavailable,
    OrderIdentifierFactory,
    OrderJournal,
    ReconciliationIssueType,
    SubmissionCoordinator,
    SubmissionOutcome,
)
from quantforge.runtime import LiveSubmissionBlocked


def _risk() -> RiskDecision:
    return RiskDecision(
        decision_id=UUID(int=101),
        intent_id=UUID(int=100),
        decision=RiskDecisionType.ALLOW,
        approved_notional="10000",
        reason_codes=("TEST_APPROVED",),
        risk_snapshot_id=UUID(int=102),
        policy_version="phase6-test",
        decided_at=BASE_TIME,
    )


def _request() -> ExchangeOrderRequest:
    risk = _risk()
    return ExchangeOrderRequest(
        intent_id=risk.intent_id,
        risk_decision_id=risk.decision_id,
        market="KRW-BTC",
        side="bid",
        order_type=ExchangeOrderType.LIMIT,
        volume="100",
        price="100",
        identifier=OrderIdentifierFactory().create(
            intent_id=risk.intent_id, risk_decision_id=risk.decision_id
        ),
        requested_at_utc=BASE_TIME,
        expires_at_utc=BASE_TIME + timedelta(seconds=30),
    )


def _chance() -> OrderChance:
    return OrderChance(
        market="KRW-BTC",
        bid_types=(ExchangeOrderType.LIMIT,),
        ask_types=(ExchangeOrderType.LIMIT,),
        min_bid_notional="5000",
        min_ask_notional="5000",
        max_total_notional="1000000",
        tick_size="1",
        reference_price="100",
        quote_available="100000",
        quote_locked="0",
        base_available="1000",
        base_locked="0",
        bid_fee_rate="0.0005",
        ask_fee_rate="0.0005",
        observed_at_utc=BASE_TIME,
        source_hash="b" * 64,
    )


def _remote(state: RemoteOrderState = RemoteOrderState.WAIT) -> RemoteOrderSnapshot:
    request = _request()
    remaining = Decimal(0) if state is RemoteOrderState.DONE else Decimal(100)
    executed = Decimal(100) if state is RemoteOrderState.DONE else Decimal(0)
    return RemoteOrderSnapshot(
        exchange_order_id=UUID(int=200),
        identifier=request.identifier,
        market=request.market,
        side=request.side,
        order_type=request.order_type,
        state=state,
        original_volume="100",
        remaining_volume=remaining,
        executed_volume=executed,
        price="100",
        paid_fee="0",
        locked="10000",
        observed_at_utc=BASE_TIME,
    )


@pytest.mark.asyncio
async def test_successful_submission_is_idempotent() -> None:
    request = _request()
    port = FakePrivateOrderPort()
    port.create_outcomes[request.identifier] = _remote()
    coordinator = SubmissionCoordinator(port=port, journal=OrderJournal())
    first = await coordinator.submit(request, _risk(), _chance(), at_utc=BASE_TIME)
    second = await coordinator.submit(request, _risk(), _chance(), at_utc=BASE_TIME)
    assert first.outcome is SubmissionOutcome.ACKNOWLEDGED
    assert second.outcome is SubmissionOutcome.IDEMPOTENT
    assert port.create_calls == [request.identifier]


@pytest.mark.asyncio
async def test_timeout_reconciles_by_identifier_without_create_retry() -> None:
    request = _request()
    port = FakePrivateOrderPort()
    port.create_outcomes[request.identifier] = PrivateTransportTimeout("synthetic timeout")
    port.lookup_outcomes[request.identifier] = _remote()
    coordinator = SubmissionCoordinator(port=port, journal=OrderJournal())
    result = await coordinator.submit(request, _risk(), _chance(), at_utc=BASE_TIME)
    assert result.outcome is SubmissionOutcome.ACKNOWLEDGED
    assert result.reconciled
    assert port.create_calls == [request.identifier]
    assert port.lookup_calls == [request.identifier]


@pytest.mark.asyncio
async def test_unresolved_timeout_remains_unknown_and_never_retries_create() -> None:
    request = _request()
    port = FakePrivateOrderPort()
    port.create_outcomes[request.identifier] = PrivateTransportTimeout("synthetic timeout")
    port.lookup_outcomes[request.identifier] = None
    journal = OrderJournal()
    coordinator = SubmissionCoordinator(port=port, journal=journal)
    first = await coordinator.submit(request, _risk(), _chance(), at_utc=BASE_TIME)
    second = await coordinator.submit(
        request, _risk(), _chance(), at_utc=BASE_TIME + timedelta(seconds=1)
    )
    assert first.outcome is SubmissionOutcome.UNKNOWN
    assert second.outcome is SubmissionOutcome.UNKNOWN
    assert journal.current(request.identifier).status is OrderStatus.UNKNOWN
    assert port.create_calls == [request.identifier]
    assert port.lookup_calls == [request.identifier, request.identifier]


@pytest.mark.asyncio
async def test_recovery_from_submission_pending_only_reconciles_identifier() -> None:
    request = _request()
    journal = OrderJournal()
    coordinator = SubmissionCoordinator(port=FakePrivateOrderPort(), journal=journal)
    assert coordinator.prepare(request, _risk(), _chance(), at_utc=BASE_TIME).allowed
    journal.transition(
        request.identifier,
        OrderStatus.SUBMISSION_PENDING,
        occurred_at_utc=BASE_TIME,
        source=JournalSource.REST,
    )
    port = FakePrivateOrderPort()
    port.lookup_outcomes[request.identifier] = _remote()
    recovered = SubmissionCoordinator(port=port, journal=journal)
    result = await recovered.submit(
        request, _risk(), _chance(), at_utc=BASE_TIME + timedelta(seconds=1)
    )
    assert result.outcome is SubmissionOutcome.ACKNOWLEDGED
    assert port.create_calls == []
    assert port.lookup_calls == [request.identifier]


@pytest.mark.asyncio
async def test_private_and_order_test_ports_are_disabled_or_mock_only() -> None:
    request = _request()
    with pytest.raises(PrivateExchangeDisabled):
        await DisabledPrivateOrderPort().test_order(request)
    port = FakePrivateOrderPort()
    port.test_outcomes[request.identifier] = OrderTestResult(
        identifier=request.identifier,
        accepted=True,
        checked_at_utc=BASE_TIME,
        reason_codes=("FAKE_DRY_RUN_ACCEPTED",),
    )
    result = await MockOnlyOrderTestAdapter(port).validate(request)
    assert result.dry_run
    assert port.create_calls == []


def test_reconciliation_blocks_balance_mismatch() -> None:
    request = _request()
    port = FakePrivateOrderPort()
    port.create_outcomes[request.identifier] = _remote()
    journal = OrderJournal()

    async def submit() -> None:
        await SubmissionCoordinator(port=port, journal=journal).submit(
            request, _risk(), _chance(), at_utc=BASE_TIME
        )

    import asyncio

    asyncio.run(submit())
    report = ExecutionReconciler().reconcile(
        journal=journal,
        remote_orders=(_remote(),),
        local_balances=(BalanceObservation(currency="KRW", available="90000", locked="10000"),),
        remote_balances=(BalanceObservation(currency="KRW", available="89999", locked="10000"),),
        reconciled_at_utc=BASE_TIME,
    )
    assert not report.safe_to_resume
    assert report.issues[0].issue_type is ReconciliationIssueType.BALANCE_MISMATCH


def _all_live_settings() -> QuantForgeSettings:
    return QuantForgeSettings(
        _env_file=None,
        trading_mode=TradingMode.LIVE,
        allow_order_submission=True,
        live_release_manifest_valid=True,
        risk_policy_approved=True,
        model_release_approved=True,
        operator_unlock_present=True,
    )


@pytest.mark.asyncio
async def test_live_adapter_is_disabled_even_after_all_six_gates() -> None:
    adapter = DisabledLiveOrderAdapter()
    assert not adapter.network_capability
    with pytest.raises(LiveExecutionUnavailable):
        await adapter.submit(_request(), _risk(), _all_live_settings())
    with pytest.raises(LiveSubmissionBlocked):
        await adapter.submit(_request(), _risk(), QuantForgeSettings(_env_file=None))


def test_phase6_private_execution_has_no_network_client() -> None:
    root = Path(__file__).parents[2] / "src" / "quantforge"
    paths = (
        root / "exchange" / "private.py",
        root / "exchange" / "auth.py",
        root / "execution" / "coordinator.py",
        root / "execution" / "live.py",
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for forbidden in (
        "import httpx",
        "import requests",
        "import websockets",
        "import socket",
    ):
        assert forbidden not in source

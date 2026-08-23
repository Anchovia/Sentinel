from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from factories import BASE_TIME
from quantforge.domain import (
    ExchangeOrderRequest,
    ExchangeOrderType,
    ExchangeTimeInForce,
    OrderChance,
    OrderStatus,
    RiskDecision,
    RiskDecisionType,
    SelfMatchPrevention,
)
from quantforge.execution import (
    ExchangeOrderPolicy,
    JournalSource,
    OrderIdentifierFactory,
    OrderJournal,
    OrderJournalIntegrityError,
)


def make_risk(*, approved_notional: str = "10000") -> RiskDecision:
    return RiskDecision(
        decision_id=UUID(int=11),
        intent_id=UUID(int=10),
        decision=RiskDecisionType.ALLOW,
        approved_notional=approved_notional,
        reason_codes=("TEST_APPROVED",),
        risk_snapshot_id=UUID(int=12),
        policy_version="phase6-test",
        decided_at=BASE_TIME,
    )


def make_request(*, identifier: str | None = None) -> ExchangeOrderRequest:
    risk = make_risk()
    return ExchangeOrderRequest(
        intent_id=risk.intent_id,
        risk_decision_id=risk.decision_id,
        market="KRW-BTC",
        side="bid",
        order_type=ExchangeOrderType.LIMIT,
        volume="100",
        price="100",
        identifier=identifier
        or OrderIdentifierFactory().create(
            intent_id=risk.intent_id, risk_decision_id=risk.decision_id
        ),
        requested_at_utc=BASE_TIME,
        expires_at_utc=BASE_TIME + timedelta(seconds=30),
    )


def make_chance(**updates: object) -> OrderChance:
    values: dict[str, object] = {
        "market": "KRW-BTC",
        "bid_types": (ExchangeOrderType.LIMIT, ExchangeOrderType.PRICE),
        "ask_types": (ExchangeOrderType.LIMIT, ExchangeOrderType.MARKET),
        "min_bid_notional": "5000",
        "min_ask_notional": "5000",
        "max_total_notional": "1000000",
        "tick_size": "1",
        "reference_price": "100",
        "quote_available": "100000",
        "quote_locked": "0",
        "base_available": "1000",
        "base_locked": "0",
        "bid_fee_rate": "0.0005",
        "ask_fee_rate": "0.0005",
        "observed_at_utc": BASE_TIME,
        "source_hash": "a" * 64,
    }
    values.update(updates)
    return OrderChance(**values)


def test_order_shape_identifier_and_preflight_are_strict() -> None:
    request = make_request()
    assert len(request.identifier) <= 64
    assert request.ordered_body[:2] == (("market", "KRW-BTC"), ("side", "bid"))
    result = ExchangeOrderPolicy().evaluate(
        request, make_risk(), make_chance(), checked_at_utc=BASE_TIME
    )
    assert result.allowed
    assert result.approved_notional == Decimal(10000)

    with pytest.raises(ValidationError, match="post_only and SMP"):
        ExchangeOrderRequest(
            **request.model_dump(exclude={"time_in_force", "smp_type"}),
            time_in_force=ExchangeTimeInForce.POST_ONLY,
            smp_type=SelfMatchPrevention.REDUCE,
        )


def test_preflight_rejects_stale_chance_tick_risk_and_balance() -> None:
    request = make_request().model_copy(update={"price": Decimal("100.5")})
    result = ExchangeOrderPolicy(max_chance_age_seconds=1).evaluate(
        request,
        make_risk(approved_notional="9000"),
        make_chance(quote_available="100"),
        checked_at_utc=BASE_TIME + timedelta(seconds=2),
    )
    assert not result.allowed
    assert {
        "STALE_ORDER_CHANCE",
        "INVALID_TICK_SIZE",
        "RISK_NOTIONAL_EXCEEDED",
        "INSUFFICIENT_QUOTE_BALANCE",
    }.issubset(result.reason_codes)


def _advance_to_submission_pending(journal: OrderJournal, request: ExchangeOrderRequest) -> None:
    journal.register(request, occurred_at_utc=BASE_TIME)
    journal.transition(
        request.identifier,
        OrderStatus.RISK_APPROVED,
        occurred_at_utc=BASE_TIME,
        source=JournalSource.RISK,
    )
    journal.transition(
        request.identifier,
        OrderStatus.PREFLIGHT_PENDING,
        occurred_at_utc=BASE_TIME,
        source=JournalSource.PREFLIGHT,
    )
    journal.transition(
        request.identifier,
        OrderStatus.PREFLIGHT_OK,
        occurred_at_utc=BASE_TIME,
        source=JournalSource.PREFLIGHT,
    )
    journal.transition(
        request.identifier,
        OrderStatus.SUBMISSION_PENDING,
        occurred_at_utc=BASE_TIME,
        source=JournalSource.REST,
    )


def test_order_journal_persists_identity_state_and_hash_chain(tmp_path: Path) -> None:
    path = tmp_path / "orders.jsonl"
    request = make_request()
    journal = OrderJournal(path)
    _advance_to_submission_pending(journal, request)
    journal.transition(
        request.identifier,
        OrderStatus.UNKNOWN,
        occurred_at_utc=BASE_TIME + timedelta(seconds=1),
        source=JournalSource.REST,
    )
    reopened = OrderJournal(path)
    reopened.verify()
    assert reopened.current(request.identifier).status is OrderStatus.UNKNOWN
    assert reopened.register(request, occurred_at_utc=BASE_TIME).status is OrderStatus.UNKNOWN

    other = request.model_copy(update={"intent_id": UUID(int=999)})
    with pytest.raises(OrderJournalIntegrityError, match="already been used"):
        reopened.register(other, occurred_at_utc=BASE_TIME)


def test_order_journal_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "orders.jsonl"
    journal = OrderJournal(path)
    journal.register(make_request(), occurred_at_utc=BASE_TIME)
    path.write_bytes(path.read_bytes().replace(b"KRW-BTC", b"KRW-ETH"))
    with pytest.raises(OrderJournalIntegrityError, match="event hash"):
        OrderJournal(path)

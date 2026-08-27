from datetime import timedelta
from pathlib import Path

import orjson
import pytest

from factories import BASE_TIME, make_orderbook_event, make_trade_event
from quantforge.research.scalping import (
    ScalpingBacktestEngine,
    ScalpingResearchDecision,
    ScalpingRule,
    blocked_experiment_ledger,
    create_blocked_scalping_report,
    evaluate_scalping_data_sufficiency,
    load_scalping_experiment_plan,
    write_scalping_research_bundle,
)
from quantforge.storage import (
    ParquetRawEventWriter,
    RawEventMarketInventory,
    RawEventResearchInventory,
    scan_raw_event_research_inventory,
)

ROOT = Path(__file__).parents[2]
PLAN_PATH = ROOT / "research" / "experiments" / "2026-08-24-scalping-challenger-v1.json"


def _inventory(*, eligible_markets: int) -> RawEventResearchInventory:
    markets = tuple(
        RawEventMarketInventory(
            market=f"KRW-T{index}",
            trade_events=20_000,
            orderbook_events=20_000,
            first_received_at_utc=BASE_TIME,
            last_received_at_utc=BASE_TIME + timedelta(hours=24),
        )
        for index in range(eligible_markets)
    )
    return RawEventResearchInventory(
        dataset_hash="a" * 64,
        maximum_exchange_timestamp_utc=BASE_TIME + timedelta(hours=24),
        selected_file_count=2,
        selected_event_count=40_000 * eligible_markets,
        markets=markets,
    )


def _entry_and_exit_events():  # type: ignore[no-untyped-def]
    events = [
        make_orderbook_event(
            sequence=1,
            received_offset_ms=0,
            asks=(("100.01", "1000"),),
            bids=(("99.99", "1000"),),
        )
    ]
    for sequence in range(2, 11):
        events.append(
            make_trade_event(
                sequence=sequence,
                exchange_offset_ms=(sequence - 1) * 100,
                received_offset_ms=(sequence - 1) * 100,
                price=101 if sequence == 10 else 100,
                ask_bid="BID",
            )
        )
    events.extend(
        (
            make_orderbook_event(
                sequence=11,
                received_offset_ms=1_100,
                asks=(("100.2", "1000"),),
                bids=(("100.1", "1000"),),
            ),
            make_trade_event(
                sequence=12,
                exchange_offset_ms=1_400,
                received_offset_ms=1_400,
                price=102,
                ask_bid="BID",
            ),
            make_orderbook_event(
                sequence=13,
                received_offset_ms=1_600,
                asks=(("102.1", "1000"),),
                bids=(("102", "1000"),),
            ),
            make_orderbook_event(
                sequence=14,
                received_offset_ms=4_000,
                asks=(("102.1", "1000"),),
                bids=(("102", "1000"),),
            ),
        )
    )
    return events


def test_plan_is_closed_preregistered_trial_space() -> None:
    plan = load_scalping_experiment_plan(PLAN_PATH)

    assert plan.validation.planned_trial_count == 18
    assert plan.dataset_selection.final_holdout_access is False
    assert plan.decision_rules.automatic_promotion is False
    assert plan.safety.real_orders_executed is False
    assert plan.dataset_selection.maximum_received_at_utc is None
    assert len(plan.digest) == 64


def test_plan_rejects_receive_cutoff_after_registration() -> None:
    payload = orjson.loads(PLAN_PATH.read_bytes())
    payload["dataset_selection"]["maximum_received_at_utc"] = "2099-01-01T00:00:00Z"

    with pytest.raises(ValueError, match="receive cutoff cannot follow"):
        type(load_scalping_experiment_plan(PLAN_PATH)).model_validate(payload)


def test_data_sufficiency_requires_three_full_markets() -> None:
    plan = load_scalping_experiment_plan(PLAN_PATH)

    blocked = evaluate_scalping_data_sufficiency(plan, _inventory(eligible_markets=2))
    ready = evaluate_scalping_data_sufficiency(plan, _inventory(eligible_markets=3))

    assert blocked.meets_requirements is False
    assert blocked.reasons == ("INSUFFICIENT_ELIGIBLE_MARKETS",)
    assert ready.meets_requirements is True
    assert len(ready.eligible_markets) == 3


def test_inventory_scan_is_content_addressed_and_honors_cutoff(tmp_path: Path) -> None:
    writer = ParquetRawEventWriter(tmp_path, max_rows=10)
    writer.append(
        make_orderbook_event(
            sequence=1,
            received_offset_ms=0,
            asks=(("100.01", 1),),
            bids=(("99.99", 1),),
        )
    )
    writer.append(make_trade_event(sequence=2, exchange_offset_ms=100, received_offset_ms=100))
    writer.append(make_trade_event(sequence=3, exchange_offset_ms=200, received_offset_ms=200))
    writer.close()

    cutoff = BASE_TIME + timedelta(milliseconds=150)
    first = scan_raw_event_research_inventory(tmp_path, maximum_exchange_timestamp_utc=cutoff)
    second = scan_raw_event_research_inventory(tmp_path, maximum_exchange_timestamp_utc=cutoff)

    assert first == second
    assert first.manifest_set_sha256 is not None
    assert len(first.manifest_set_sha256) == 64
    assert first.selected_event_count == 2
    assert first.markets[0].trade_events == 1
    assert first.markets[0].orderbook_events == 1


def test_inventory_scan_excludes_late_arrival_before_duplicate_checks(tmp_path: Path) -> None:
    writer = ParquetRawEventWriter(tmp_path, max_rows=10)
    writer.append(make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=100))
    writer.append(make_trade_event(sequence=2, exchange_offset_ms=50, received_offset_ms=300))
    writer.close()

    exchange_cutoff = BASE_TIME + timedelta(milliseconds=150)
    receive_cutoff = BASE_TIME + timedelta(milliseconds=200)
    inventory = scan_raw_event_research_inventory(
        tmp_path,
        maximum_exchange_timestamp_utc=exchange_cutoff,
        maximum_received_at_utc=receive_cutoff,
    )

    assert inventory.maximum_exchange_timestamp_utc == exchange_cutoff
    assert inventory.maximum_received_at_utc == receive_cutoff
    assert inventory.selected_event_count == 1
    assert inventory.markets[0].trade_events == 1


def test_blocked_result_and_ledger_retain_no_trial_outcome(tmp_path: Path) -> None:
    plan = load_scalping_experiment_plan(PLAN_PATH)
    inventory = _inventory(eligible_markets=1)
    sufficiency = evaluate_scalping_data_sufficiency(plan, inventory)
    generated = plan.registered_at_utc + timedelta(minutes=1)

    report = create_blocked_scalping_report(
        plan,
        inventory,
        sufficiency,
        source_revision="1" * 40,
        generated_at_utc=generated,
    )
    ledger = blocked_experiment_ledger(
        plan,
        inventory,
        sufficiency,
        source_revision="1" * 40,
        generated_at_utc=generated,
    )
    paths = write_scalping_research_bundle(report, ledger, tmp_path)

    assert report.decision is ScalpingResearchDecision.BLOCKED
    assert report.trial_results == ()
    assert report.final_holdout_used is False
    assert len(ledger.records) == 2
    assert all(path.is_file() for path in paths)
    assert paths[0].relative_to(tmp_path).parts[:3] == ("2026", "08", "24")
    payload = orjson.loads(paths[1].read_bytes())
    assert payload["safety"]["real_orders_executed"] is False


def test_trade_continuation_runs_entry_and_exit_through_conservative_broker() -> None:
    plan = load_scalping_experiment_plan(PLAN_PATH)
    events = _entry_and_exit_events()

    first = ScalpingBacktestEngine(
        plan,
        market="KRW-BTC",
        rule=ScalpingRule.TRADE_CONTINUATION,
        cost_scenario="base",
        fold_id="test-1",
        code_version="test-revision",
    ).run(events)
    second = ScalpingBacktestEngine(
        plan,
        market="KRW-BTC",
        rule=ScalpingRule.TRADE_CONTINUATION,
        cost_scenario="base",
        fold_id="test-1",
        code_version="test-revision",
    ).run(events)

    assert first == second
    assert first.closed_trade_count == 1
    assert first.open_position_at_end is False
    assert first.net_pnl > 0
    assert first.fees > 0
    assert first.slippage_cost > 0
    assert first.adverse_selection_cost > 0
    assert first.order_network_used is False
    assert first.real_orders_executed is False


def test_neutral_baseline_has_no_orders_or_fills() -> None:
    plan = load_scalping_experiment_plan(PLAN_PATH)
    result = ScalpingBacktestEngine(
        plan,
        market="KRW-BTC",
        rule=ScalpingRule.ALWAYS_NEUTRAL,
        cost_scenario="stress",
        fold_id="test-neutral",
        code_version="test-revision",
    ).run(_entry_and_exit_events())

    assert result.signal_count == 0
    assert result.order_count == 0
    assert result.fill_count == 0
    assert result.net_pnl == 0

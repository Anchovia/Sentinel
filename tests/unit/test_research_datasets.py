from datetime import timedelta
from itertools import pairwise
from pathlib import Path

import pytest

from factories import BASE_TIME
from quantforge.features import FeatureSnapshot
from quantforge.research import (
    AlphaClass,
    AlphaLabelSpec,
    FinalHoldoutVault,
    SplitRole,
    build_feature_dataset,
    build_forward_labels,
    chronological_four_way_split,
)


def _snapshots(count: int = 50) -> list[FeatureSnapshot]:
    snapshots: list[FeatureSnapshot] = []
    for index in range(count):
        event_time = BASE_TIME + timedelta(seconds=index)
        price = 100 + (index % 7) - (index % 3)
        snapshots.append(
            FeatureSnapshot(
                feature_set="phase4-fixture",
                feature_version="1",
                market="KRW-BTC",
                event_time_utc=event_time,
                available_at_utc=event_time + timedelta(milliseconds=10),
                computed_at_utc=event_time + timedelta(milliseconds=10),
                values={
                    "x": float((index % 5) - 2),
                    "volatility": float(index % 4),
                    "mid_price": float(price),
                },
                input_hash=f"{index + 1:064x}",
            )
        )
    return snapshots


def _labeled():  # type: ignore[no-untyped-def]
    dataset = build_feature_dataset(
        _snapshots(),
        required_features=("volatility", "x"),
        reference_feature="mid_price",
        code_version="phase4-test",
        created_at_utc=BASE_TIME + timedelta(minutes=2),
    )
    labels = build_forward_labels(
        dataset,
        AlphaLabelSpec(
            version="alpha-1s-v1",
            horizon_seconds=1,
            reference_feature="mid_price",
            estimated_round_trip_cost_bps="5",
            safety_margin_bps="2",
        ),
    )
    return dataset, labels


def test_feature_dataset_and_forward_labels_are_deterministic_and_causal() -> None:
    first_dataset, first_labels = _labeled()
    second_dataset, second_labels = _labeled()

    assert first_dataset.dataset_hash == second_dataset.dataset_hash
    assert first_labels.dataset_hash == second_labels.dataset_hash
    assert len(first_labels.examples) == len(first_dataset.rows) - 1
    assert {example.alpha_class for example in first_labels.examples} == {
        AlphaClass.DOWN,
        AlphaClass.NEUTRAL,
        AlphaClass.UP,
    }
    assert all(
        example.label_available_at_utc >= example.label_end_utc
        and example.label_end_utc > example.event_time_utc
        for example in first_labels.examples
    )


def test_dataset_rejects_missing_feature_or_mixed_lineage() -> None:
    snapshots = _snapshots(5)
    snapshots[0] = snapshots[0].model_copy(
        update={"values": {"x": None, "volatility": 1.0, "mid_price": 100.0}}
    )
    with pytest.raises(ValueError, match="missing required"):
        build_feature_dataset(
            snapshots,
            required_features=("x",),
            reference_feature="mid_price",
            code_version="phase4-test",
            created_at_utc=BASE_TIME,
        )

    mixed = _snapshots(5)
    mixed[-1] = mixed[-1].model_copy(update={"feature_version": "2"})
    with pytest.raises(ValueError, match="share lineage"):
        build_feature_dataset(
            mixed,
            required_features=("x",),
            reference_feature="mid_price",
            code_version="phase4-test",
            created_at_utc=BASE_TIME,
        )


def test_chronological_split_purges_boundaries_and_seals_holdout() -> None:
    _, labeled = _labeled()
    split = chronological_four_way_split(
        labeled,
        purge_seconds=0,
        embargo_seconds=1,
    )

    assert split.train.role is SplitRole.TRAIN
    assert split.final_holdout.role is SplitRole.FINAL_HOLDOUT
    partitions = (split.train, split.validation, split.test, split.final_holdout)
    for left, right in pairwise(partitions):
        assert left.examples[-1].label_end_utc < right.examples[0].event_time_utc

    vault = FinalHoldoutVault(split.final_holdout)
    assert vault.is_sealed
    examples = vault.open_once(
        approved_review_id="manual-final-review-1",
        accessed_at_utc=BASE_TIME + timedelta(days=1),
    )
    assert examples == split.final_holdout.examples
    assert not vault.is_sealed
    with pytest.raises(PermissionError, match="already accessed"):
        vault.open_once(
            approved_review_id="manual-final-review-2",
            accessed_at_utc=BASE_TIME + timedelta(days=1, seconds=1),
        )


def test_split_rejects_invalid_ratios_and_excessive_embargo() -> None:
    _, labeled = _labeled()
    with pytest.raises(ValueError, match="sum to one"):
        chronological_four_way_split(labeled, train_fraction=0.6)
    with pytest.raises(ValueError, match="emptied"):
        chronological_four_way_split(labeled, embargo_seconds=1_000)


def test_no_research_fixture_writes_final_holdout_to_disk(tmp_path: Path) -> None:
    _, labeled = _labeled()
    split = chronological_four_way_split(labeled)
    assert split.final_holdout.examples
    assert list(tmp_path.iterdir()) == []

"""``analysis/protocols/barnes/strategy.py`` — direct / serial / random (#633)."""

from __future__ import annotations

import numpy as np
import pytest

from zebtrack.analysis.protocols.barnes.contract import (
    BarnesParams,
    SearchStrategy,
    StrategySource,
)
from zebtrack.analysis.protocols.barnes.strategy import (
    StrategyFeatures,
    circular_step,
    classify_strategy,
    count_center_crossings,
    resolve_strategy,
    strategy_features,
)

PARAMS = BarnesParams(n_holes=20)


@pytest.mark.parametrize(
    ("a", "b", "step"), [(0, 1, 1), (1, 0, 1), (9, -9, 2), (10, -9, 1), (5, -5, 10), (3, 3, 0)]
)
def test_circular_step_goes_the_short_way(a, b, step):
    assert circular_step(a, b, 20) == step


@pytest.mark.parametrize(("a", "b", "step"), [(9, -8, 1), (-8, 9, 1), (8, -8, 2), (9, 0, 9)])
def test_circular_step_wraps_round_an_eighteen_hole_table(a, b, step):
    assert circular_step(a, b, 18) == step


def test_center_crossings_count_only_entries_from_outside():
    assert count_center_crossings(np.array([True, True, False, False, True, False, True])) == 2
    assert count_center_crossings(np.array([False, True])) == 1
    assert count_center_crossings(np.array([True])) == 0
    assert count_center_crossings(np.array([], dtype=bool)) == 0


def test_features_measure_adjacent_transitions():
    features = strategy_features(
        [5, 4, 2, -3, -4], errors_before_target=4, center_crossings=1, params=PARAMS
    )

    assert features == StrategyFeatures(
        errors_before_target=4,
        center_crossings=1,
        adjacent_transition_fraction=0.75,
        n_transitions=4,
    )
    assert features.as_dict() == {
        "errors_before_target": 4,
        "center_crossings": 1,
        "adjacent_transition_fraction": 0.75,
        "n_transitions": 4,
    }
    assert list(features.as_dict()) == [
        "errors_before_target",
        "center_crossings",
        "adjacent_transition_fraction",
        "n_transitions",
    ]


def test_the_adjacent_step_is_a_parameter():
    params = BarnesParams(n_holes=20, strategy_adjacent_max_step=1)

    features = strategy_features(
        [5, 4, 2], errors_before_target=2, center_crossings=0, params=params
    )

    assert features.adjacent_transition_fraction == 0.5


@pytest.mark.parametrize("offsets", [[], [3]])
def test_no_transition_has_no_fraction(offsets):
    features = strategy_features(offsets, errors_before_target=0, center_crossings=0, params=PARAMS)

    assert features.n_transitions == 0
    assert features.adjacent_transition_fraction is None


def _f(errors=0, crossings=0, fraction=None, transitions=0) -> StrategyFeatures:
    return StrategyFeatures(errors, crossings, fraction, transitions)


@pytest.mark.parametrize(
    ("features", "found", "expected"),
    [
        (_f(errors=3, fraction=1.0, transitions=3), True, SearchStrategy.DIRECT),
        (_f(errors=0), True, SearchStrategy.DIRECT),
        (_f(errors=4, fraction=1.0, transitions=4), True, SearchStrategy.SERIAL),
        (_f(errors=0, crossings=1, fraction=1.0, transitions=1), True, SearchStrategy.SERIAL),
        (_f(errors=0, fraction=1.0, transitions=1), False, SearchStrategy.SERIAL),
        (_f(errors=4, fraction=2 / 3, transitions=3), True, SearchStrategy.SERIAL),
        (_f(errors=4, fraction=0.5, transitions=4), True, SearchStrategy.RANDOM),
        (_f(errors=4, crossings=2, fraction=1.0, transitions=4), True, SearchStrategy.RANDOM),
        (_f(errors=1, crossings=1), True, SearchStrategy.RANDOM),
        (_f(errors=1), False, SearchStrategy.RANDOM),
    ],
)
def test_classifier_thresholds(features, found, expected):
    assert classify_strategy(features, found_target=found, n_visits=1, params=PARAMS) is expected


def test_thresholds_are_read_from_the_params():
    params = BarnesParams(
        n_holes=20,
        strategy_direct_max_errors=1,
        strategy_serial_min_adjacent_fraction=0.5,
        strategy_serial_max_center_crossings=3,
    )

    assert (
        classify_strategy(_f(errors=2), found_target=True, n_visits=3, params=params)
        is SearchStrategy.RANDOM
    )
    assert (
        classify_strategy(
            _f(errors=2, crossings=3, fraction=0.5, transitions=2),
            found_target=True,
            n_visits=3,
            params=params,
        )
        is SearchStrategy.SERIAL
    )


def test_no_visit_has_no_strategy():
    assert classify_strategy(_f(), found_target=False, n_visits=0, params=PARAMS) is None


def test_manual_override_wins_and_is_marked():
    assert resolve_strategy(SearchStrategy.DIRECT, None) == (
        SearchStrategy.DIRECT,
        StrategySource.AUTO,
    )
    assert resolve_strategy(SearchStrategy.DIRECT, SearchStrategy.RANDOM) == (
        SearchStrategy.RANDOM,
        StrategySource.MANUAL,
    )
    assert resolve_strategy(None, SearchStrategy.SERIAL) == (
        SearchStrategy.SERIAL,
        StrategySource.MANUAL,
    )
    assert resolve_strategy(None, None) == (None, None)

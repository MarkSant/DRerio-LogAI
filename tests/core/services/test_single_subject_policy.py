"""``single_subject_policy``: one rule for "one animal per aquarium?" (#649)."""

from __future__ import annotations

import pytest

from zebtrack.core.services.single_subject_policy import (
    count_means_single,
    resolve_project_single_subject,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, True),
        ("1", True),
        (0, True),
        (2, False),
        ("3", False),
        (None, None),
        ("", None),
        ("abc", None),
        (True, None),
    ],
)
def test_count_means_single(value, expected):
    assert count_means_single(value) is expected


def _decide(project_data):
    decision = resolve_project_single_subject(project_data)
    return None if decision is None else (decision.single, decision.source)


def test_nothing_in_the_project_says():
    assert resolve_project_single_subject(None) is None
    assert resolve_project_single_subject({}) is None
    assert resolve_project_single_subject({"calibration": {"num_aquariums": 2}}) is None


def test_calibration_count_beats_the_tracking_flag():
    data = {
        "tracking": {"use_single_subject_tracker": False},
        "calibration": {"animals_per_aquarium": 1},
    }
    assert _decide(data) == (True, "calibration.animals_per_aquarium")

    data = {
        "tracking": {"use_single_subject_tracker": True},
        "calibration": {"animals_per_aquarium": 2},
    }
    assert _decide(data) == (False, "calibration.animals_per_aquarium")


def test_the_tracking_flag_decides_only_without_a_count():
    assert _decide({"tracking": {"use_single_subject_tracker": True}}) == (
        True,
        "tracking.use_single_subject_tracker",
    )


def test_legacy_explicit_flags_come_first():
    data = {"single_animal_per_aquarium": False, "calibration": {"animals_per_aquarium": 1}}
    assert _decide(data) == (False, "single_animal_per_aquarium")
    data = {"use_single_subject_tracker": True, "animals_per_aquarium": 4}
    assert _decide(data) == (True, "use_single_subject_tracker")


def test_count_order_top_level_then_calibration_then_lists():
    assert _decide({"animals_per_aquarium": 2, "calibration": {"animals_per_aquarium": 1}}) == (
        False,
        "animals_per_aquarium",
    )
    assert _decide({"calibration": {"animals_per_aquarium_list": [1, 1, 2]}}) == (
        False,
        "calibration.animals_per_aquarium_list",
    )
    assert _decide({"_wizard_metadata": {"animals_per_aquarium_list": [1, 1]}}) == (
        True,
        "_wizard_metadata.animals_per_aquarium_list",
    )
    assert _decide({"video_processing": {"animals_per_aquarium": 1}}) == (
        True,
        "video_processing.animals_per_aquarium",
    )


def test_unreadable_count_falls_through_to_the_next_source():
    data = {
        "animals_per_aquarium": "many",
        "calibration": {"animals_per_aquarium": 1},
        "tracking": {"use_single_subject_tracker": False},
    }
    assert _decide(data) == (True, "calibration.animals_per_aquarium")

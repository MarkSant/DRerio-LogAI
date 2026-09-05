"""``resolve_sharp_turn_threshold`` — one threshold for the table and the plot.

The defect this closes
----------------------
``sharp_turn_threshold_deg_s`` is configurable in ``config.yaml``, in both
ad-hoc dialogs and per project — and it never reached the number.

``AnalysisService.run_full_analysis`` did not accept the parameter at all and
called ``b_analyzer.calculate_sharp_turns(90.0)`` with a literal
("# Assuming 90 as default"). The configured value travelled a second route
instead — ``run_full_analysis_as_dto`` -> ``AnalysisResult`` ->
``ReporterContext.sharp_turn_threshold`` -> ``VisualizationGenerator``, which
recomputes the turns for the trajectory PLOT.

So a single ``.docx`` could show a metrics table computed at 90 deg/s beside a
figure computed at the DTO default of 45, and no production caller passed the
parameter, so that mismatch was the normal case rather than an edge one.

The precedence order is the point
---------------------------------
``params`` (project > session) comes BEFORE ``settings_obj``. Reversing them
would reopen the leak ``project_settings_snapshot`` exists to close: the shared
``Settings`` carries whatever the last ad-hoc dialog wrote into it, so a project
analysed after a single-video run would inherit that run's threshold.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from zebtrack.analysis.analysis_service import (
    DEFAULT_SHARP_TURN_THRESHOLD_DEG_S,
    resolve_sharp_turn_threshold,
)

if TYPE_CHECKING:
    from zebtrack.settings import Settings


def _settings(value: object) -> Settings:
    """A stand-in carrying only the one field the resolver reads.

    The resolver reaches the value through ``getattr`` chains precisely so a
    partially-built or foreign settings object degrades instead of raising, and
    building a real ``Settings`` here would need the whole ``config.yaml``
    schema to exercise one attribute. The cast keeps the production signature
    honest — callers must still pass a real ``Settings``.
    """
    return cast(
        "Settings",
        SimpleNamespace(video_processing=SimpleNamespace(sharp_turn_threshold_deg_s=value)),
    )


def test_resolved_params_win_over_settings() -> None:
    """The project's value beats the shared object's. This is the leak guard."""
    params = {"analysis": {"sharp_turn_threshold": 25.0}}

    assert resolve_sharp_turn_threshold(params, _settings(200.0)) == 25.0


def test_settings_used_when_params_carry_nothing() -> None:
    assert resolve_sharp_turn_threshold({}, _settings(120.0)) == 120.0
    assert resolve_sharp_turn_threshold({"analysis": {}}, _settings(120.0)) == 120.0


def test_default_when_neither_source_has_a_value() -> None:
    assert resolve_sharp_turn_threshold(None, None) == DEFAULT_SHARP_TURN_THRESHOLD_DEG_S
    assert resolve_sharp_turn_threshold({}, _settings(None)) == DEFAULT_SHARP_TURN_THRESHOLD_DEG_S


def test_default_matches_the_shipped_configuration() -> None:
    """The fallback and ``config.yaml`` must not drift apart again.

    Before this module there were four numbers for one setting: 200.0 in the
    ``Settings`` schema, 90.0 in ``config.yaml``, 45.0 as the DTO default and
    90.0 hardcoded in the computation.
    """
    from tests.helpers.prerecorded_pipeline import load_pristine_settings

    shipped = load_pristine_settings().video_processing.sharp_turn_threshold_deg_s
    assert shipped == DEFAULT_SHARP_TURN_THRESHOLD_DEG_S


@pytest.mark.parametrize("bad", ["", "abrupto", None, [], {}])
def test_a_corrupt_override_degrades_to_the_next_level(bad: object) -> None:
    """A hand-edited ``project_config.json`` must not stop a report.

    ``Settings`` validates its own fields, but ``project_data`` is plain JSON on
    disk and nothing checks it on the way in. Raising here would abort the
    analysis after the tracking has already run.
    """
    params = {"analysis": {"sharp_turn_threshold": bad}}

    assert resolve_sharp_turn_threshold(params, _settings(150.0)) == 150.0


def test_a_corrupt_setting_degrades_to_the_default() -> None:
    assert (
        resolve_sharp_turn_threshold({}, _settings("noventa")) == DEFAULT_SHARP_TURN_THRESHOLD_DEG_S
    )


def test_integer_and_string_numbers_are_accepted() -> None:
    """``project_config.json`` round-trips numbers as whatever JSON produced."""
    assert resolve_sharp_turn_threshold({"analysis": {"sharp_turn_threshold": 30}}, None) == 30.0
    assert resolve_sharp_turn_threshold({"analysis": {"sharp_turn_threshold": "30"}}, None) == 30.0


def test_zero_is_honoured_rather_than_treated_as_absent() -> None:
    """0.0 means "every direction change counts", not "unset".

    A truthiness check here would silently promote a deliberate 0 to the
    default — the shape of bug this repo has hit before with ROI thresholds.
    """
    assert resolve_sharp_turn_threshold({"analysis": {"sharp_turn_threshold": 0.0}}, None) == 0.0

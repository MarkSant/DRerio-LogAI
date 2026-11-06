"""Tests for the ready-made analysis windows (``core/conditions/presets.py``).

The Barnes preset is the acceptance spec of v8: the fixture under
``tests/fixtures/conditions/`` is what the evaluator, the artifact and the E2E
tests are written against. The preset must reproduce it exactly when called with
the fixture's numbers — any drift would make the button in the UI produce a spec
nobody tested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from zebtrack.core.conditions import (
    ConditionEvaluator,
    Delay,
    External,
    ExternalEvent,
    FirstOf,
    FrameObservation,
    Persist,
    WindowSpec,
    spec_hash,
)
from zebtrack.core.conditions.presets import (
    LEGACY_TRIGGER_START_CODE,
    LEGACY_TRIGGER_STOP_CODE,
    barnes_maze_preset,
    external_trigger_preset,
)

BARNES_FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "conditions" / "barnes_window.json"
)


def _fixture() -> WindowSpec:
    return WindowSpec.model_validate(json.loads(BARNES_FIXTURE.read_text(encoding="utf-8")))


class TestBarnesMazePreset:
    def test_fixture_numbers_reproduce_the_acceptance_fixture(self) -> None:
        preset = barnes_maze_preset(k_frames=3, absent_s=2.0, max_s=240.0)

        assert preset == _fixture()
        assert spec_hash(preset) == spec_hash(_fixture())

    def test_serialized_preset_is_the_fixture_json(self) -> None:
        dumped = barnes_maze_preset(k_frames=3, absent_s=2.0, max_s=240.0).model_dump(
            mode="json", by_alias=True
        )

        assert dumped == _fixture().model_dump(mode="json", by_alias=True)
        assert dumped["start"]["level"]["children"][0]["target"] == {
            "class": "start_box",
            "role": None,
        }

    def test_production_defaults_are_documented_values(self) -> None:
        preset = barnes_maze_preset()

        assert isinstance(preset.start, Persist)
        assert preset.start.hold.frames == 5
        assert isinstance(preset.stop, FirstOf)
        absent = preset.stop.children[1]
        ceiling = preset.stop.children[2]
        assert isinstance(absent, Persist)
        assert absent.hold.seconds == 3.0
        assert isinstance(ceiling, Delay)
        assert ceiling.after == "start"
        assert ceiling.seconds == 240.0

    def test_parameters_reach_the_spec(self) -> None:
        preset = barnes_maze_preset(k_frames=7, absent_s=1.5, max_s=120.0)

        assert isinstance(preset.start, Persist)
        assert preset.start.hold.frames == 7
        assert isinstance(preset.stop, FirstOf)
        absent = preset.stop.children[1]
        ceiling = preset.stop.children[2]
        assert isinstance(absent, Persist) and absent.hold.seconds == 1.5
        assert isinstance(ceiling, Delay) and ceiling.seconds == 120.0

    def test_keeps_window_policies_at_their_defaults(self) -> None:
        preset = barnes_maze_preset()

        assert preset.on_start_not_met == "whole_recording"
        assert preset.on_stop == "mark"

    @pytest.mark.parametrize("max_s", [0.0, -1.0])
    def test_non_positive_ceiling_is_rejected(self, max_s: float) -> None:
        with pytest.raises(ValueError, match="max_s"):
            barnes_maze_preset(max_s=max_s)

    def test_invalid_hold_is_rejected_by_the_model(self) -> None:
        with pytest.raises(ValidationError):
            barnes_maze_preset(k_frames=0)
        with pytest.raises(ValidationError):
            barnes_maze_preset(absent_s=0.0)

    def test_preset_starts_on_release_and_stops_on_escape(self) -> None:
        """The preset is evaluable end to end: release at frame 2, escape at frame 10."""
        evaluator = ConditionEvaluator(
            barnes_maze_preset(k_frames=3, absent_s=2.0), role_names={"subject": {"rat"}}
        )
        events = []
        for frame in range(30):
            t_s = frame * 0.5
            if frame < 2:
                classes = {"start_box": (0.9,), "experimenter": (0.9,), "rat": (0.9,)}
            elif frame < 10:
                classes = {"rat": (0.9,)}
            else:
                classes = {}
            events.extend(evaluator.step(FrameObservation(frame=frame, t_s=t_s, classes=classes)))
        events.extend(evaluator.finish())

        by_kind = {event.kind: event for event in events}
        assert by_kind["start"].frame == 2
        assert by_kind["stop"].frame == 10


class TestExternalTriggerPreset:
    def test_legacy_codes_open_and_close_the_window(self) -> None:
        preset = external_trigger_preset()

        assert preset.start == External(source="arduino", code=1)
        assert preset.stop == External(source="arduino", code=0)
        assert LEGACY_TRIGGER_START_CODE == 1
        assert LEGACY_TRIGGER_STOP_CODE == 0

    def test_stop_code_ends_the_session_like_the_legacy_mode(self) -> None:
        assert external_trigger_preset().on_stop == "end_session"

    def test_custom_codes(self) -> None:
        preset = external_trigger_preset(start_code=7, stop_code=8)

        assert preset.start == External(source="arduino", code=7)
        assert preset.stop == External(source="arduino", code=8)

    def test_arduino_codes_drive_the_evaluator(self) -> None:
        evaluator = ConditionEvaluator(external_trigger_preset(), role_names={})
        events = []
        for frame in range(6):
            external: tuple[ExternalEvent, ...] = ()
            if frame == 1:
                external = (ExternalEvent(source="arduino", code=1, t_s=0.1),)
            if frame == 4:
                external = (ExternalEvent(source="arduino", code=0, t_s=0.4),)
            events.extend(
                evaluator.step(FrameObservation(frame=frame, t_s=frame * 0.1, external=external))
            )

        assert [(event.kind, event.frame) for event in events] == [("start", 1), ("stop", 4)]

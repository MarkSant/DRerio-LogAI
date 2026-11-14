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
    RoiEdge,
    WindowSpec,
    evaluate_window,
    spec_hash,
)
from zebtrack.core.conditions.presets import (
    BARNES_BURROW_ROI,
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
        """The fixture predates the burrow line (#650): it is the preset without it."""
        preset = barnes_maze_preset(k_frames=3, absent_s=2.0, max_s=240.0, burrow_roi=None)

        assert preset == _fixture()
        assert spec_hash(preset) == spec_hash(_fixture())

    def test_serialized_preset_is_the_fixture_json(self) -> None:
        dumped = barnes_maze_preset(
            k_frames=3, absent_s=2.0, max_s=240.0, burrow_roi=None
        ).model_dump(mode="json", by_alias=True)

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
        ceiling = preset.stop.children[3]
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
        ceiling = preset.stop.children[3]
        assert isinstance(absent, Persist) and absent.hold.seconds == 1.5
        assert isinstance(ceiling, Delay) and ceiling.seconds == 120.0

    def test_stop_includes_the_burrow_entry_by_default(self) -> None:
        """#650: the rat is often visible until the last frame; the burrow ends the trial."""
        preset = barnes_maze_preset()

        assert BARNES_BURROW_ROI == "toca"
        assert isinstance(preset.stop, FirstOf)
        assert preset.stop.children[2] == RoiEdge(roi="toca", edge="enter")

    def test_burrow_roi_name_reaches_the_spec(self) -> None:
        preset = barnes_maze_preset(burrow_roi="Escape box")

        assert isinstance(preset.stop, FirstOf)
        assert preset.stop.children[2] == RoiEdge(roi="Escape box", edge="enter")

    def test_without_burrow_the_stop_has_three_lines(self) -> None:
        preset = barnes_maze_preset(burrow_roi=None)

        assert isinstance(preset.stop, FirstOf)
        assert len(preset.stop.children) == 3
        assert not any(isinstance(child, RoiEdge) for child in preset.stop.children)

    @pytest.mark.parametrize("name", ["", "   "])
    def test_blank_burrow_name_is_rejected(self, name: str) -> None:
        with pytest.raises(ValueError, match="burrow_roi"):
            barnes_maze_preset(burrow_roi=name)

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


def _barnes_trial(*, rat_visible_to_the_end: bool) -> list[FrameObservation]:
    """Release at frame 2, the rat walks, enters ``toca`` at frame 12.

    With ``rat_visible_to_the_end`` the rat stays detected inside the burrow ROI
    until the last frame — the real ``Exemp_1``/``Exemp_2`` recordings, where the
    video stops on the protocol's abort before the rat ever disappears.
    """
    observations = []
    for frame in range(40):
        t_s = frame * 0.5
        if frame < 2:
            classes = {"start_box": (0.9,), "experimenter": (0.9,), "rat": (0.9,)}
        elif frame < 16 or rat_visible_to_the_end:
            classes = {"rat": (0.9,)}
        else:
            classes = {}
        in_burrow = 12 <= frame and (frame < 16 or rat_visible_to_the_end)
        observations.append(
            FrameObservation(
                frame=frame,
                t_s=t_s,
                classes=classes,
                subject_rois=frozenset({"toca"}) if in_burrow else frozenset(),
            )
        )
    return observations


ROLES = {"subject": {"rat"}}


class TestBarnesBurrowStop:
    def test_burrow_entry_ends_a_trial_the_rat_never_leaves(self) -> None:
        result = evaluate_window(
            barnes_maze_preset(k_frames=3, absent_s=2.0),
            _barnes_trial(rat_visible_to_the_end=True),
            role_names=ROLES,
        )

        assert result.stop is not None
        assert (result.stop.frame, result.stop.reason) == (12, "roi_edge")
        assert result.stop.t_s == pytest.approx(6.0)
        assert result.censored is False
        assert result.status == "complete"

    def test_without_the_burrow_the_same_trial_is_censored_at_the_end(self) -> None:
        """The pre-#650 behaviour on the real videos: STOP at the last frame."""
        result = evaluate_window(
            barnes_maze_preset(k_frames=3, absent_s=2.0, burrow_roi=None),
            _barnes_trial(rat_visible_to_the_end=True),
            role_names=ROLES,
        )

        assert result.stop is not None
        assert (result.stop.frame, result.stop.reason) == (39, "end_of_stream")
        assert result.censored is True

    def test_burrow_entry_comes_before_the_absence_it_precedes(self) -> None:
        """The rat enters at 12 and vanishes at 16: the entry is the earlier instant."""
        result = evaluate_window(
            barnes_maze_preset(k_frames=3, absent_s=2.0),
            _barnes_trial(rat_visible_to_the_end=False),
            role_names=ROLES,
        )

        assert result.stop is not None
        assert (result.stop.frame, result.stop.reason) == (12, "roi_edge")

    def test_a_roi_the_project_lacks_never_fires(self) -> None:
        """A missing ``toca`` degrades to the other stop lines (the editor warns)."""
        result = evaluate_window(
            barnes_maze_preset(k_frames=3, absent_s=2.0, burrow_roi="Escape"),
            _barnes_trial(rat_visible_to_the_end=False),
            role_names=ROLES,
        )

        assert result.stop is not None
        assert (result.stop.frame, result.stop.reason) == (16, "persist")


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

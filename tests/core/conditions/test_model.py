"""Tests for the analysis-window condition AST (ADR-011, ``core/conditions/model.py``).

The AST is a persistence contract: a spec written into a project today must load,
hash and evaluate identically in every later version. These tests pin the JSON
shape of every node, the validators that keep a START condition evaluable, and
the canonical hash the analysis cache keys on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from zebtrack.core.conditions import (
    AllOf,
    AllOfLevel,
    AnyOfLevel,
    ClassPresence,
    ClassTarget,
    Delay,
    EndOfStream,
    External,
    FirstOf,
    FrameReached,
    Hold,
    Not,
    Persist,
    RoiEdge,
    RoiInside,
    Sequence,
    TimeReached,
    WindowSpec,
    iter_nodes,
    spec_hash,
)

BARNES_FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "conditions" / "barnes_window.json"
)


def _rat_present() -> ClassPresence:
    return ClassPresence(target=ClassTarget.of_class("rat"))


def _barnes_spec(k: int = 3, absent_s: float = 2.0, ceiling_s: float = 240.0) -> WindowSpec:
    return WindowSpec(
        start=Persist(
            level=AllOfLevel(
                children=(
                    ClassPresence(target=ClassTarget.of_class("start_box"), present=False),
                    ClassPresence(target=ClassTarget.of_class("experimenter"), present=False),
                    ClassPresence(target=ClassTarget.of_class("rat"), present=True),
                )
            ),
            hold=Hold(frames=k),
        ),
        stop=FirstOf(
            children=(
                EndOfStream(),
                Persist(
                    level=ClassPresence(target=ClassTarget.of_class("rat"), present=False),
                    hold=Hold(seconds=absent_s),
                ),
                Delay(after="start", seconds=ceiling_s),
            )
        ),
    )


def _error_types(exc: ValidationError) -> set[str]:
    return {str(err["type"]) for err in exc.errors()}


# ---------------------------------------------------------------------------
# JSON round trip
# ---------------------------------------------------------------------------

_EVERY_TRIGGER = (
    Persist(level=_rat_present(), hold=Hold(seconds=1.5), max_gap_s=0.5),
    Persist(level=Not(child=RoiInside(roi="arena", state="inside")), hold=Hold(frames=4)),
    RoiEdge(roi="escape_box", edge="enter"),
    RoiEdge(roi="escape_box", edge="exit"),
    TimeReached(clock="video", at_s=12.5),
    TimeReached(clock="wall", at_s=3.0),
    FrameReached(frame=42),
    Delay(after=FrameReached(frame=10), seconds=2.0),
    External(source="arduino", code=3),
    External(source="manual", code=None),
    FirstOf(children=(FrameReached(frame=1), External(source="manual", code=None))),
    AllOf(children=(FrameReached(frame=1), TimeReached(clock="video", at_s=0.0))),
    Sequence(
        children=(RoiEdge(roi="a", edge="enter"), RoiEdge(roi="b", edge="enter")),
        within_s=10.0,
    ),
    Sequence(children=(FrameReached(frame=3),), within_s=None),
)

_EVERY_LEVEL = (
    ClassPresence(target=ClassTarget.of_class("rat")),
    ClassPresence(
        target=ClassTarget.of_role("context"), present=False, min_count=2, min_confidence=0.4
    ),
    ClassPresence(target=ClassTarget.of_role("subject")),
    RoiInside(roi="center", state="outside"),
    Not(child=RoiInside(roi="center", state="inside")),
    AllOfLevel(children=(_rat_present(), RoiInside(roi="c", state="inside"))),
    AnyOfLevel(children=(_rat_present(), RoiInside(roi="c", state="inside"))),
)


class TestRoundTrip:
    @pytest.mark.parametrize("trigger", _EVERY_TRIGGER, ids=lambda t: t.kind)
    def test_every_trigger_survives_json_as_start(self, trigger: Any) -> None:
        spec = WindowSpec(start=trigger)
        again = WindowSpec.model_validate_json(spec.model_dump_json())
        assert again == spec
        assert spec_hash(again) == spec_hash(spec)

    @pytest.mark.parametrize("level", _EVERY_LEVEL, ids=lambda lv: lv.kind)
    def test_every_level_survives_json_inside_persist(self, level: Any) -> None:
        spec = WindowSpec(stop=Persist(level=level, hold=Hold(frames=1)))
        again = WindowSpec.model_validate_json(spec.model_dump_json())
        assert again == spec

    def test_stop_only_nodes_survive_json(self) -> None:
        spec = WindowSpec(
            stop=FirstOf(children=(EndOfStream(), Delay(after="start", seconds=240.0))),
            on_start_not_met="empty",
            on_stop="end_session",
        )
        again = WindowSpec.model_validate_json(spec.model_dump_json())
        assert again == spec
        assert again.on_stop == "end_session"
        assert again.on_start_not_met == "empty"

    def test_kind_tokens_are_the_persisted_english_contract(self) -> None:
        kinds = {node.kind for node in (*_EVERY_TRIGGER, *_EVERY_LEVEL, EndOfStream())}
        assert kinds == {
            "persist",
            "roi_edge",
            "time_reached",
            "frame_reached",
            "delay",
            "external",
            "first_of",
            "all_of",
            "sequence",
            "class_presence",
            "roi_inside",
            "not",
            "all_of_level",
            "any_of_level",
            "end_of_stream",
        }

    def test_class_target_serializes_under_the_class_key(self) -> None:
        dumped = json.loads(ClassTarget.of_class("rat").model_dump_json())
        assert dumped == {"class": "rat", "role": None}
        role = json.loads(ClassTarget.of_role("subject").model_dump_json())
        assert role == {"class": None, "role": "subject"}

    def test_defaults_mean_whole_recording(self) -> None:
        spec = WindowSpec()
        assert spec.version == 1
        assert spec.start is None
        assert spec.stop is None
        assert spec.on_start_not_met == "whole_recording"
        assert spec.on_stop == "mark"

    def test_barnes_fixture_is_the_documented_spec(self) -> None:
        loaded = WindowSpec.model_validate_json(BARNES_FIXTURE.read_text(encoding="utf-8"))
        assert loaded == _barnes_spec()
        assert isinstance(loaded.start, Persist)
        assert loaded.start.hold.frames == 3
        assert isinstance(loaded.stop, FirstOf)
        delay = loaded.stop.children[2]
        assert isinstance(delay, Delay)
        assert delay.after == "start"
        assert delay.seconds == 240.0

    def test_nodes_are_immutable(self) -> None:
        node = FrameReached(frame=3)
        with pytest.raises(ValidationError):
            node.frame = 4


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class TestValidators:
    def test_delay_after_start_is_rejected_inside_start(self) -> None:
        with pytest.raises(ValidationError) as exc:
            WindowSpec(start=Delay(after="start", seconds=5.0))
        assert "start_refers_to_itself" in _error_types(exc.value)

    def test_delay_after_start_nested_deep_inside_start_is_rejected(self) -> None:
        nested = FirstOf(
            children=(
                FrameReached(frame=10),
                Sequence(children=(FrameReached(frame=1), Delay(after="start", seconds=1.0))),
            )
        )
        with pytest.raises(ValidationError) as exc:
            WindowSpec(start=nested)
        assert "start_refers_to_itself" in _error_types(exc.value)

    def test_end_of_stream_is_rejected_inside_start(self) -> None:
        with pytest.raises(ValidationError) as exc:
            WindowSpec(start=FirstOf(children=(FrameReached(frame=10), EndOfStream())))
        assert "start_uses_end_of_stream" in _error_types(exc.value)

    def test_end_of_stream_behind_a_delay_is_rejected_inside_start(self) -> None:
        with pytest.raises(ValidationError) as exc:
            WindowSpec(start=Delay(after=EndOfStream(), seconds=1.0))
        assert "start_uses_end_of_stream" in _error_types(exc.value)

    def test_the_same_nodes_are_legal_inside_stop(self) -> None:
        spec = WindowSpec(
            start=Delay(after=FrameReached(frame=2), seconds=1.0),
            stop=FirstOf(children=(EndOfStream(), Delay(after="start", seconds=5.0))),
        )
        assert isinstance(spec.stop, FirstOf)

    def test_rejected_start_from_json_names_the_problem(self) -> None:
        raw = '{"start": {"kind": "end_of_stream"}}'
        with pytest.raises(ValidationError) as exc:
            WindowSpec.model_validate_json(raw)
        assert "start_uses_end_of_stream" in _error_types(exc.value)
        assert "EndOfStream" in str(exc.value)

    @pytest.mark.parametrize(
        "payload",
        [{}, {"seconds": 1.0, "frames": 2}],
        ids=["neither", "both"],
    )
    def test_hold_needs_exactly_one_field(self, payload: dict[str, Any]) -> None:
        with pytest.raises(ValidationError) as exc:
            Hold.model_validate(payload)
        assert "hold_needs_exactly_one" in _error_types(exc.value)

    @pytest.mark.parametrize(
        "payload",
        [{"seconds": 0.0}, {"seconds": -1.0}, {"frames": 0}, {"frames": -3}],
    )
    def test_hold_must_be_positive(self, payload: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Hold.model_validate(payload)

    def test_hold_accepts_one_positive_field(self) -> None:
        assert Hold(seconds=0.5).frames is None
        assert Hold(frames=1).seconds is None

    @pytest.mark.parametrize(
        ("model", "field"),
        [
            (AllOfLevel, "children"),
            (AnyOfLevel, "children"),
            (FirstOf, "children"),
            (AllOf, "children"),
            (Sequence, "children"),
        ],
    )
    def test_children_cannot_be_empty(self, model: Any, field: str) -> None:
        with pytest.raises(ValidationError) as exc:
            model.model_validate({field: []})
        assert "too_short" in _error_types(exc.value)

    def test_class_target_needs_exactly_one_of_class_or_role(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ClassTarget.model_validate({"class": "rat", "role": "subject"})
        assert "class_target_needs_exactly_one" in _error_types(exc.value)
        with pytest.raises(ValidationError) as exc:
            ClassTarget.model_validate({})
        assert "class_target_needs_exactly_one" in _error_types(exc.value)

    def test_class_target_role_is_a_closed_vocabulary(self) -> None:
        with pytest.raises(ValidationError):
            ClassTarget.model_validate({"role": "arena"})

    def test_class_name_is_normalized_like_the_detector_does(self) -> None:
        target = ClassTarget.model_validate({"class": "  Start-Box "})
        assert target.class_name == "start_box"
        assert ClassTarget.of_class("Open Field").class_name == "open_field"

    def test_class_name_normalization_matches_class_aliases(self) -> None:
        from zebtrack.core.detection.class_aliases import normalize_class_name

        for raw in ("Rat", " start box ", "EXPERIMENTER", "open-field  arena"):
            assert ClassTarget.of_class(raw).class_name == normalize_class_name(raw)

    def test_blank_class_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClassTarget.model_validate({"class": "   "})

    def test_unknown_kind_and_extra_keys_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WindowSpec.model_validate({"start": {"kind": "teleport"}})
        with pytest.raises(ValidationError):
            WindowSpec.model_validate({"start": {"kind": "frame_reached", "frame": 1, "x": 2}})
        with pytest.raises(ValidationError):
            WindowSpec.model_validate({"version": 2})

    @pytest.mark.parametrize(
        "payload",
        [
            {"kind": "class_presence", "target": {"class": "rat"}, "min_count": 0},
            {"kind": "class_presence", "target": {"class": "rat"}, "min_confidence": 1.5},
            {"kind": "frame_reached", "frame": -1},
            {"kind": "time_reached", "clock": "video", "at_s": -0.1},
            {"kind": "time_reached", "clock": "video", "at_s": float("nan")},
            {"kind": "delay", "after": "start", "seconds": -1.0},
            {
                "kind": "sequence",
                "children": [{"kind": "frame_reached", "frame": 1}],
                "within_s": 0,
            },
            {
                "kind": "persist",
                "level": {"kind": "roi_inside", "roi": "a", "state": "inside"},
                "hold": {"frames": 1},
                "max_gap_s": 0.0,
            },
            {"kind": "roi_edge", "roi": "", "edge": "enter"},
            {"kind": "external", "source": "keyboard", "code": 1},
        ],
    )
    def test_out_of_range_fields_are_rejected(self, payload: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            WindowSpec.model_validate({"stop": payload})


# ---------------------------------------------------------------------------
# Hash and traversal
# ---------------------------------------------------------------------------


class TestSpecHash:
    def test_hash_has_the_documented_prefix_and_length(self) -> None:
        digest = spec_hash(_barnes_spec())
        assert digest.startswith("sha256:")
        assert len(digest) == len("sha256:") + 64

    def test_hash_is_stable_under_key_reordering(self) -> None:
        raw = json.loads(BARNES_FIXTURE.read_text(encoding="utf-8"))
        reordered = json.dumps(_reverse_keys(raw))
        assert reordered != json.dumps(raw)
        assert spec_hash(WindowSpec.model_validate_json(reordered)) == spec_hash(_barnes_spec())

    def test_hash_ignores_whether_defaults_were_spelled_out(self) -> None:
        explicit = WindowSpec.model_validate(
            {"version": 1, "start": None, "stop": None, "on_stop": "mark"}
        )
        assert spec_hash(explicit) == spec_hash(WindowSpec())

    def test_hash_changes_when_the_spec_changes(self) -> None:
        base = spec_hash(_barnes_spec())
        assert spec_hash(_barnes_spec(k=4)) != base
        assert spec_hash(_barnes_spec(absent_s=2.5)) != base
        assert spec_hash(_barnes_spec(ceiling_s=60.0)) != base
        assert spec_hash(WindowSpec(on_stop="end_session")) != spec_hash(WindowSpec())

    def test_hash_is_the_sha256_of_sorted_compact_json(self) -> None:
        import hashlib

        spec = WindowSpec(start=FrameReached(frame=5))
        canonical = json.dumps(
            spec.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":")
        )
        expected = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert spec_hash(spec) == expected


def _reverse_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _reverse_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reverse_keys(item) for item in value]
    return value


class TestIterNodes:
    def test_walks_every_node_depth_first(self) -> None:
        spec = _barnes_spec()
        assert spec.stop is not None
        kinds = [node.kind for node in iter_nodes(spec.stop)]
        assert kinds == [
            "first_of",
            "end_of_stream",
            "persist",
            "class_presence",
            "delay",
        ]

    def test_descends_into_delay_triggers_and_level_children(self) -> None:
        tree = Delay(
            after=Persist(
                level=Not(
                    child=AnyOfLevel(children=(_rat_present(), RoiInside(roi="a", state="inside")))
                ),
                hold=Hold(frames=2),
            ),
            seconds=1.0,
        )
        kinds = [node.kind for node in iter_nodes(tree)]
        assert kinds == ["delay", "persist", "not", "any_of_level", "class_presence", "roi_inside"]

    def test_finds_external_arduino_in_a_spec(self) -> None:
        spec = WindowSpec(
            start=Sequence(children=(FrameReached(frame=1), External(source="arduino", code=2)))
        )
        assert spec.start is not None
        externals = [n for n in iter_nodes(spec.start) if isinstance(n, External)]
        assert [(e.source, e.code) for e in externals] == [("arduino", 2)]

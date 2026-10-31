"""Tests for the analysis-window editor (``ui/components/analysis_window_panel.py``).

Two layers, two markers:

- The line model (lines ⇄ ``WindowSpec``), the preview and the friendly messages are
  pure functions. They run in the fast suite and are what the mutation catalogue
  checks — the panel's correctness is decided there.
- The Tk panel (``@pytest.mark.gui``) only shuttles widget values into that model,
  persists the spec and announces it on the bus.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

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
    spec_hash,
)
from zebtrack.core.conditions.presets import barnes_maze_preset, external_trigger_preset
from zebtrack.ui.components.analysis_window_panel import (
    PROJECT_KEY,
    ROW_KINDS,
    STOP_ONLY_KINDS,
    AnalysisWindowPanel,
    ConditionRow,
    SectionDraft,
    SpecBuildError,
    build_trigger,
    build_window_spec,
    check_row,
    combinator_labels,
    describe_level,
    describe_row,
    describe_trigger,
    describe_window_spec,
    drafts_from_spec,
    format_number,
    friendly_validation_message,
    hold_unit_labels,
    load_window_spec,
    missing_class_names,
    on_start_not_met_labels,
    on_stop_labels,
    parse_number,
    referenced_class_names,
    role_labels,
    row_kind_labels,
    section_labels,
    store_window_spec,
)
from zebtrack.ui.event_bus_v2 import UIEvents

BARNES_FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "conditions" / "barnes_window.json"
)


def _fixture_spec() -> WindowSpec:
    return WindowSpec.model_validate(json.loads(BARNES_FIXTURE.read_text(encoding="utf-8")))


def _rat_absent() -> ClassPresence:
    return ClassPresence(target=ClassTarget.of_class("rat"), present=False)


def _section(*rows: ConditionRow, combinator: Any = "all_of") -> SectionDraft:
    return SectionDraft(combinator=combinator, rows=rows)


BARNES_START_ROWS = (
    ConditionRow(kind="class_absent", target="start_box"),
    ConditionRow(kind="class_absent", target="experimenter"),
    ConditionRow(kind="class_present", target="rat"),
    ConditionRow(kind="hold", value=3.0, unit="frames"),
)
BARNES_STOP_ROWS = (
    ConditionRow(kind="end_of_video"),
    ConditionRow(kind="class_absent", target="rat"),
    ConditionRow(kind="hold", value=2.0, unit="seconds"),
    ConditionRow(kind="delay_after_start", value=240.0),
)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class TestLabels:
    def test_every_line_kind_has_a_label(self) -> None:
        assert set(row_kind_labels()) == set(ROW_KINDS)
        assert len(set(row_kind_labels().values())) == len(ROW_KINDS)

    def test_option_labels_cover_every_model_token(self) -> None:
        assert set(on_start_not_met_labels()) == {"whole_recording", "empty"}
        assert set(on_stop_labels()) == {"mark", "end_session"}
        assert set(combinator_labels()) == {"all_of", "any_of", "sequence"}
        assert set(hold_unit_labels()) == {"seconds", "frames"}
        assert set(role_labels()) == {"subject", "context"}
        assert set(section_labels()) == {"start", "stop"}

    def test_stop_only_kinds(self) -> None:
        assert STOP_ONLY_KINDS == {"delay_after_start", "end_of_video"}


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------


class TestNumbers:
    @pytest.mark.parametrize(
        ("value", "expected"), [(3.0, "3"), (2.5, "2.5"), (240.0, "240"), (0.0, "0")]
    )
    def test_format_number(self, value: float, expected: str) -> None:
        assert format_number(value) == expected

    def test_blank_is_not_given(self) -> None:
        assert parse_number("  ", integer=False) is None

    def test_decimal_comma_is_accepted(self) -> None:
        assert parse_number("2,5", integer=False) == 2.5

    def test_integer_text(self) -> None:
        assert parse_number(" 12 ", integer=True) == 12.0

    def test_not_a_number(self) -> None:
        with pytest.raises(SpecBuildError, match="abc"):
            parse_number("abc", integer=False)

    def test_fraction_rejected_when_integer(self) -> None:
        with pytest.raises(SpecBuildError, match="whole number"):
            parse_number("2.5", integer=True)


# ---------------------------------------------------------------------------
# Friendly validation messages
# ---------------------------------------------------------------------------


class TestFriendlyValidationMessage:
    @staticmethod
    def _error(factory: Any) -> ValidationError:
        with pytest.raises(ValidationError) as info:
            factory()
        return info.value

    def test_greater_than_names_the_limit(self) -> None:
        exc = self._error(lambda: Hold(seconds=-1.0))
        assert friendly_validation_message(exc) == "The number must be greater than 0."

    def test_greater_than_equal_names_the_limit(self) -> None:
        exc = self._error(lambda: Hold(frames=0))
        assert friendly_validation_message(exc) == "The number must be at least 1."

    def test_less_than_equal_names_the_limit(self) -> None:
        exc = self._error(
            lambda: ClassPresence(target=ClassTarget.of_class("rat"), min_confidence=2.0)
        )
        assert friendly_validation_message(exc) == "The number must be at most 1."

    def test_blank_class_name(self) -> None:
        exc = self._error(lambda: ClassTarget.of_class("   "))
        assert friendly_validation_message(exc) == "Type or choose a class name."

    def test_window_rules_are_explained(self) -> None:
        exc = self._error(lambda: WindowSpec(start=EndOfStream()))
        assert friendly_validation_message(exc) == "'End of the video' can only be used in Stop."
        exc = self._error(lambda: WindowSpec(start=Delay(after="start", seconds=1.0)))
        assert friendly_validation_message(exc) == (
            "'Time after the start' can only be used in Stop."
        )

    def test_unknown_type_falls_back_to_a_generic_sentence(self) -> None:
        exc = ValidationError.from_exception_data(
            "X", [{"type": "missing", "loc": ("a",), "input": {}}]
        )
        assert friendly_validation_message(exc) == "A value is not valid."

    def test_repeated_problems_are_reported_once(self) -> None:
        exc = ValidationError.from_exception_data(
            "X",
            [
                {"type": "missing", "loc": ("a",), "input": {}},
                {"type": "missing", "loc": ("b",), "input": {}},
            ],
        )
        assert friendly_validation_message(exc) == "A value is not valid."


# ---------------------------------------------------------------------------
# Lines → spec
# ---------------------------------------------------------------------------


class TestBuildTrigger:
    def test_empty_section_is_none(self) -> None:
        assert build_trigger(SectionDraft(), "start") is None

    def test_single_class_line_fires_on_its_first_true_frame(self) -> None:
        node = build_trigger(_section(ConditionRow(kind="class_present", target="rat")), "start")

        assert node == Persist(
            level=ClassPresence(target=ClassTarget.of_class("rat")), hold=Hold(frames=1)
        )

    def test_hold_in_seconds(self) -> None:
        node = build_trigger(
            _section(
                ConditionRow(kind="class_absent", target="rat"),
                ConditionRow(kind="hold", value=2.0, unit="seconds"),
            ),
            "stop",
        )

        assert node == Persist(level=_rat_absent(), hold=Hold(seconds=2.0))

    def test_hold_in_frames(self) -> None:
        node = build_trigger(
            _section(
                ConditionRow(kind="class_absent", target="rat"),
                ConditionRow(kind="hold", value=4.0, unit="frames"),
            ),
            "stop",
        )

        assert node == Persist(level=_rat_absent(), hold=Hold(frames=4))

    def test_class_lines_are_grouped_together_for_all_of(self) -> None:
        node = build_trigger(_section(*BARNES_START_ROWS), "start")

        assert node == _fixture_spec().start

    def test_class_lines_are_grouped_as_any_for_any_of(self) -> None:
        node = build_trigger(
            _section(
                ConditionRow(kind="class_present", target="rat"),
                ConditionRow(kind="class_present", role="subject"),
                combinator="any_of",
            ),
            "start",
        )

        assert node == Persist(
            level=AnyOfLevel(
                children=(
                    ClassPresence(target=ClassTarget.of_class("rat")),
                    ClassPresence(target=ClassTarget.of_role("subject")),
                )
            ),
            hold=Hold(frames=1),
        )

    def test_sequence_groups_class_lines_together(self) -> None:
        node = build_trigger(
            _section(
                ConditionRow(kind="class_present", target="rat"),
                ConditionRow(kind="class_absent", target="experimenter"),
                ConditionRow(kind="roi_enter", target="Goal"),
                combinator="sequence",
            ),
            "start",
        )

        assert isinstance(node, Sequence)
        group, edge = node.children
        assert isinstance(group, Persist)
        assert isinstance(group.level, AllOfLevel)
        assert edge == RoiEdge(roi="Goal", edge="enter")

    def test_group_takes_the_place_of_the_first_class_line(self) -> None:
        node = build_trigger(
            _section(
                ConditionRow(kind="roi_enter", target="A"),
                ConditionRow(kind="class_present", target="rat"),
                ConditionRow(kind="arduino", value=4.0),
                ConditionRow(kind="class_absent", target="experimenter"),
            ),
            "start",
        )

        assert isinstance(node, AllOf)
        kinds = [child.kind for child in node.children]
        assert kinds == ["roi_edge", "persist", "external"]

    def test_combinators(self) -> None:
        rows = (ConditionRow(kind="manual"), ConditionRow(kind="frame", value=10.0))

        assert isinstance(build_trigger(_section(*rows), "start"), AllOf)
        assert isinstance(build_trigger(_section(*rows, combinator="any_of"), "start"), FirstOf)
        assert isinstance(build_trigger(_section(*rows, combinator="sequence"), "start"), Sequence)

    @pytest.mark.parametrize(
        ("row", "expected"),
        [
            (ConditionRow(kind="roi_enter", target=" A "), RoiEdge(roi="A", edge="enter")),
            (ConditionRow(kind="roi_exit", target="A"), RoiEdge(roi="A", edge="exit")),
            (ConditionRow(kind="video_time", value=6.5), TimeReached(clock="video", at_s=6.5)),
            (ConditionRow(kind="frame", value=67.0), FrameReached(frame=67)),
            (
                ConditionRow(kind="delay_after_start", value=240.0),
                Delay(after="start", seconds=240.0),
            ),
            (ConditionRow(kind="arduino", value=1.0), External(source="arduino", code=1)),
            (ConditionRow(kind="arduino"), External(source="arduino", code=None)),
            (ConditionRow(kind="manual"), External(source="manual", code=None)),
            (ConditionRow(kind="end_of_video"), EndOfStream()),
        ],
    )
    def test_each_line_kind(self, row: ConditionRow, expected: Any) -> None:
        assert build_trigger(_section(row), "stop") == expected

    def test_role_target(self) -> None:
        node = build_trigger(_section(ConditionRow(kind="class_absent", role="context")), "start")

        assert isinstance(node, Persist)
        assert node.level == ClassPresence(target=ClassTarget.of_role("context"), present=False)

    @pytest.mark.parametrize("kind", sorted(STOP_ONLY_KINDS))
    def test_stop_only_kinds_are_rejected_in_start(self, kind: Any) -> None:
        row = ConditionRow(kind=kind, value=1.0)
        with pytest.raises(SpecBuildError, match=r"^Start, line 2: .*only be used in Stop"):
            build_trigger(_section(ConditionRow(kind="manual"), row), "start")

    def test_two_hold_lines_are_rejected_at_the_second(self) -> None:
        rows = (
            ConditionRow(kind="class_present", target="rat"),
            ConditionRow(kind="hold", value=1.0),
            ConditionRow(kind="hold", value=2.0),
        )
        with pytest.raises(SpecBuildError, match=r"^Stop, line 3: Use a single"):
            build_trigger(_section(*rows), "stop")

    def test_hold_without_class_line_is_rejected(self) -> None:
        rows = (ConditionRow(kind="manual"), ConditionRow(kind="hold", value=1.0))
        with pytest.raises(SpecBuildError, match=r"^Start, line 2: 'Held for' applies"):
            build_trigger(_section(*rows), "start")

    @pytest.mark.parametrize(
        ("row", "message"),
        [
            (ConditionRow(kind="class_present", target="  "), "Type or choose a class name."),
            (ConditionRow(kind="roi_exit", target=""), "Choose an ROI."),
            (ConditionRow(kind="video_time"), "Type a number."),
            (ConditionRow(kind="hold"), "Type a number."),
            (ConditionRow(kind="frame", value=2.5), "The number must be a whole number."),
            (ConditionRow(kind="arduino", value=1.5), "The number must be a whole number."),
            (
                ConditionRow(kind="hold", value=2.5, unit="frames"),
                "The number must be a whole number.",
            ),
            (ConditionRow(kind="video_time", value=-1.0), "The number must be at least 0."),
            (
                ConditionRow(kind="hold", value=0.0, unit="seconds"),
                "The number must be greater than 0.",
            ),
        ],
    )
    def test_invalid_lines_name_section_line_and_problem(
        self, row: ConditionRow, message: str
    ) -> None:
        rows = (ConditionRow(kind="class_present", target="rat"), row)
        with pytest.raises(SpecBuildError) as info:
            build_trigger(_section(*rows), "stop")
        assert str(info.value) == f"Stop, line 2: {message}"

    def test_fractional_hold_in_seconds_is_fine(self) -> None:
        check_row(ConditionRow(kind="hold", value=2.5, unit="seconds"), "start")

    def test_check_row_without_line_number(self) -> None:
        with pytest.raises(SpecBuildError) as info:
            check_row(ConditionRow(kind="end_of_video"), "start")
        assert str(info.value) == "'End of the video' can only be used in Stop."
        check_row(ConditionRow(kind="end_of_video"), "stop")


class TestBuildWindowSpec:
    def test_no_condition_is_the_whole_recording(self) -> None:
        assert build_window_spec(SectionDraft(), SectionDraft(), on_stop="end_session") is None

    def test_barnes_lines_build_the_acceptance_fixture(self) -> None:
        spec = build_window_spec(
            _section(*BARNES_START_ROWS), _section(*BARNES_STOP_ROWS, combinator="any_of")
        )

        assert spec == _fixture_spec()
        assert spec is not None and spec_hash(spec) == spec_hash(_fixture_spec())

    def test_options_reach_the_spec(self) -> None:
        spec = build_window_spec(
            _section(ConditionRow(kind="manual")),
            SectionDraft(),
            on_start_not_met="empty",
            on_stop="end_session",
        )

        assert spec == WindowSpec(
            start=External(source="manual"), on_start_not_met="empty", on_stop="end_session"
        )

    def test_stop_only_window(self) -> None:
        spec = build_window_spec(
            SectionDraft(), _section(ConditionRow(kind="delay_after_start", value=60.0))
        )

        assert spec == WindowSpec(stop=Delay(after="start", seconds=60.0))


# ---------------------------------------------------------------------------
# Spec → lines
# ---------------------------------------------------------------------------


class TestDraftsFromSpec:
    def test_none_is_two_empty_sections(self) -> None:
        assert drafts_from_spec(None) == (SectionDraft(), SectionDraft())

    def test_barnes_fixture_becomes_the_documented_lines(self) -> None:
        drafts = drafts_from_spec(_fixture_spec())

        assert drafts == (
            _section(*BARNES_START_ROWS, combinator="all_of"),
            _section(*BARNES_STOP_ROWS, combinator="any_of"),
        )

    @pytest.mark.parametrize(
        "spec",
        [
            barnes_maze_preset(),
            external_trigger_preset(),
            WindowSpec(start=External(source="manual"), on_start_not_met="empty"),
            WindowSpec(
                start=Persist(
                    level=AnyOfLevel(
                        children=(
                            ClassPresence(target=ClassTarget.of_role("subject")),
                            ClassPresence(target=ClassTarget.of_class("rat"), present=False),
                        )
                    ),
                    hold=Hold(seconds=1.5),
                ),
                stop=Sequence(
                    children=(
                        RoiEdge(roi="A", edge="enter"),
                        TimeReached(clock="video", at_s=30.0),
                        FrameReached(frame=900),
                    )
                ),
            ),
            WindowSpec(stop=FirstOf(children=(EndOfStream(), Delay(after="start", seconds=5.0)))),
        ],
    )
    def test_round_trip_is_exact(self, spec: WindowSpec) -> None:
        drafts = drafts_from_spec(spec)

        assert drafts is not None
        rebuilt = build_window_spec(
            drafts[0], drafts[1], on_start_not_met=spec.on_start_not_met, on_stop=spec.on_stop
        )
        assert rebuilt == spec

    def test_condition_free_spec_is_the_whole_recording(self) -> None:
        assert drafts_from_spec(WindowSpec(on_stop="end_session")) == (
            SectionDraft(),
            SectionDraft(),
        )

    @pytest.mark.parametrize(
        "spec",
        [
            WindowSpec(
                start=Sequence(children=(External(source="manual"),), within_s=10.0),
            ),
            WindowSpec(
                start=Persist(
                    level=ClassPresence(target=ClassTarget.of_class("rat"), min_confidence=0.5),
                    hold=Hold(frames=2),
                )
            ),
            WindowSpec(
                start=Persist(
                    level=ClassPresence(target=ClassTarget.of_class("rat"), min_count=2),
                    hold=Hold(frames=2),
                )
            ),
            WindowSpec(
                start=Persist(level=_rat_absent(), hold=Hold(frames=2), max_gap_s=1.0),
            ),
            WindowSpec(stop=Delay(after=External(source="manual"), seconds=3.0)),
            WindowSpec(start=TimeReached(clock="wall", at_s=3.0)),
            WindowSpec(start=External(source="manual", code=3)),
            WindowSpec(start=FirstOf(children=(External(source="manual"),))),
            WindowSpec(
                stop=FirstOf(
                    children=(
                        Persist(level=_rat_absent(), hold=Hold(seconds=1.0)),
                        Persist(level=_rat_absent(), hold=Hold(seconds=2.0)),
                    )
                )
            ),
            WindowSpec(
                start=Persist(level=RoiInside(roi="A", state="inside"), hold=Hold(frames=1))
            ),
            WindowSpec(
                start=Persist(
                    level=Not(child=ClassPresence(target=ClassTarget.of_class("rat"))),
                    hold=Hold(frames=1),
                )
            ),
            WindowSpec(
                start=FirstOf(
                    children=(
                        Persist(
                            level=AllOfLevel(
                                children=(
                                    ClassPresence(target=ClassTarget.of_class("a")),
                                    ClassPresence(target=ClassTarget.of_class("b")),
                                )
                            ),
                            hold=Hold(frames=1),
                        ),
                        External(source="manual"),
                    )
                )
            ),
        ],
        ids=[
            "sequence-time-limit",
            "confidence-filter",
            "min-count",
            "custom-gap",
            "delay-after-trigger",
            "wall-clock",
            "manual-code",
            "one-child-wrapper",
            "two-class-groups",
            "roi-level",
            "negated-level",
            "all-level-inside-first-of",
        ],
    )
    def test_specs_the_lines_cannot_express_are_refused(self, spec: WindowSpec) -> None:
        assert drafts_from_spec(spec) is None


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


class TestDescribe:
    def test_no_window(self) -> None:
        assert describe_window_spec(None) == (
            "No analysis window: the whole recording is analysed."
        )

    def test_barnes_preview(self) -> None:
        text = describe_window_spec(_fixture_spec())

        assert text.splitlines() == [
            "Start: at the same time: 'start_box' is not visible; 'experimenter' is not "
            "visible; 'rat' is visible, for 3 frame(s) in a row.",
            "Stop: the first of: the video ends; 'rat' is not visible, for 2 s; "
            "240 s after the start.",
            "If Start never happens, the whole recording is analysed (with a warning).",
        ]

    def test_open_ended_sections_and_options(self) -> None:
        text = describe_window_spec(
            WindowSpec(stop=External(source="arduino", code=0), on_stop="end_session")
        )

        assert text.splitlines() == [
            "Start: at the first processed frame.",
            "Stop: the Arduino sends code 0.",
            "In a live session, Stop ends the recording.",
        ]

    def test_empty_metrics_option(self) -> None:
        text = describe_window_spec(
            WindowSpec(start=External(source="arduino"), on_start_not_met="empty")
        )

        assert text.splitlines() == [
            "Start: the Arduino sends any code.",
            "Stop: at the end of the recording.",
            "If Start never happens, the metrics are left empty.",
        ]

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            (
                Persist(level=_rat_absent(), hold=Hold(frames=1)),
                "as soon as 'rat' is not visible",
            ),
            (RoiEdge(roi="A", edge="enter"), "the subject enters ROI 'A'"),
            (RoiEdge(roi="A", edge="exit"), "the subject leaves ROI 'A'"),
            (TimeReached(clock="video", at_s=6.5), "the video reaches 6.5 s"),
            (TimeReached(clock="wall", at_s=3.0), "3 s of clock time have passed"),
            (FrameReached(frame=67), "frame 67 is reached"),
            (
                Delay(after=External(source="manual"), seconds=2.0),
                "2 s after the operator gives the manual signal",
            ),
            (External(source="manual", code=4), "the operator gives manual signal 4"),
            (
                AllOf(children=(External(source="manual"), FrameReached(frame=1))),
                "once all have happened: the operator gives the manual signal; frame 1 is reached",
            ),
            (
                Sequence(children=(External(source="manual"),)),
                "in this order: the operator gives the manual signal",
            ),
            (
                Sequence(children=(External(source="manual"),), within_s=5.0),
                "in this order, within 5 s: the operator gives the manual signal",
            ),
        ],
    )
    def test_describe_trigger(self, node: Any, expected: str) -> None:
        assert describe_trigger(node) == expected

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            (ClassPresence(target=ClassTarget.of_role("subject")), "any subject class is visible"),
            (
                ClassPresence(target=ClassTarget.of_role("context"), present=False),
                "any context class is not visible",
            ),
            (
                ClassPresence(target=ClassTarget.of_class("rat"), min_count=2),
                "at least 2 of 'rat' visible",
            ),
            (
                ClassPresence(target=ClassTarget.of_class("rat"), min_count=2, present=False),
                "fewer than 2 of 'rat' visible",
            ),
            (
                ClassPresence(target=ClassTarget.of_class("rat"), min_confidence=0.5),
                "'rat' is visible (confidence ≥ 0.5)",
            ),
            (RoiInside(roi="A", state="inside"), "the subject is inside ROI 'A'"),
            (RoiInside(roi="A", state="outside"), "the subject is outside ROI 'A'"),
            (Not(child=_rat_absent()), "not ('rat' is not visible)"),
            (
                AnyOfLevel(children=(_rat_absent(), RoiInside(roi="A", state="inside"))),
                "any of: 'rat' is not visible; the subject is inside ROI 'A'",
            ),
        ],
    )
    def test_describe_level(self, node: Any, expected: str) -> None:
        assert describe_level(node) == expected

    @pytest.mark.parametrize(
        ("row", "expected"),
        [
            (ConditionRow(kind="class_present", target="rat"), "rat"),
            (
                ConditionRow(kind="class_present", role="subject"),
                "Role: subject (any subject class)",
            ),
            (ConditionRow(kind="roi_enter", target="A"), "A"),
            (ConditionRow(kind="hold", value=3.0, unit="frames"), "3 frames"),
            (ConditionRow(kind="hold", value=1.5, unit="seconds"), "1.5 seconds"),
            (ConditionRow(kind="hold"), ""),
            (ConditionRow(kind="video_time", value=6.0), "6 s"),
            (ConditionRow(kind="delay_after_start"), ""),
            (ConditionRow(kind="frame", value=12.0), "12"),
            (ConditionRow(kind="frame"), ""),
            (ConditionRow(kind="arduino"), "any code"),
            (ConditionRow(kind="arduino", value=1.0), "code 1"),
            (ConditionRow(kind="manual"), ""),
            (ConditionRow(kind="end_of_video"), ""),
        ],
    )
    def test_describe_row(self, row: ConditionRow, expected: str) -> None:
        assert describe_row(row) == expected


class TestClassNames:
    def test_referenced_class_names_in_order_without_roles(self) -> None:
        spec = WindowSpec(
            start=Persist(
                level=AllOfLevel(
                    children=(
                        ClassPresence(target=ClassTarget.of_class("b")),
                        ClassPresence(target=ClassTarget.of_role("subject")),
                        ClassPresence(target=ClassTarget.of_class("a")),
                    )
                ),
                hold=Hold(frames=1),
            ),
            stop=Persist(
                level=ClassPresence(target=ClassTarget.of_class("b"), present=False),
                hold=Hold(frames=1),
            ),
        )

        assert referenced_class_names(spec) == ["b", "a"]
        assert referenced_class_names(None) == []

    def test_missing_class_names_compares_normalized(self) -> None:
        spec = _fixture_spec()

        assert missing_class_names(spec, ["Start Box", "RAT"]) == ["experimenter"]

    def test_unknown_class_list_reports_nothing(self) -> None:
        assert missing_class_names(_fixture_spec(), []) == []
        assert missing_class_names(_fixture_spec(), ["  "]) == []


class TestPersistence:
    def test_absent_key_is_no_window(self) -> None:
        assert load_window_spec({}) == (None, False)
        assert load_window_spec({PROJECT_KEY: None}) == (None, False)

    def test_stored_spec_round_trips(self) -> None:
        project_data: dict[str, Any] = {}
        store_window_spec(project_data, _fixture_spec())

        assert project_data[PROJECT_KEY] == json.loads(
            json.dumps(_fixture_spec().model_dump(mode="json", by_alias=True))
        )
        assert project_data[PROJECT_KEY]["start"]["level"]["children"][2]["target"]["class"] == (
            "rat"
        )
        assert load_window_spec(project_data) == (_fixture_spec(), False)

    def test_storing_none_clears_the_window(self) -> None:
        project_data: dict[str, Any] = {PROJECT_KEY: {"version": 1}}
        store_window_spec(project_data, None)

        assert project_data == {PROJECT_KEY: None}

    def test_corrupt_value_degrades_to_none(self) -> None:
        assert load_window_spec({PROJECT_KEY: {"version": 1, "start": {"kind": "nope"}}}) == (
            None,
            True,
        )


# ---------------------------------------------------------------------------
# Tk panel
# ---------------------------------------------------------------------------


def _make_controller(
    project_data: dict[str, Any],
    *,
    roi_names: list[str] | None = None,
    project_path: str | None = "/proj",
) -> tuple[SimpleNamespace, MagicMock]:
    pm = MagicMock()
    pm.project_data = project_data
    pm.project_path = project_path
    pm.get_zone_data.return_value = SimpleNamespace(roi_names=roi_names or [])
    pm.save_project = MagicMock()
    return SimpleNamespace(project_manager=pm), pm


def _published_payloads(bus: MagicMock) -> list[Any]:
    events = [call.args[0] for call in bus.publish.call_args_list]
    assert all(event.type is UIEvents.ANALYSIS_WINDOW_SPEC_CHANGED for event in events)
    return [event.data for event in events]


@pytest.mark.gui
class TestAnalysisWindowPanel:
    def _panel(
        self,
        root: Any,
        project_data: dict[str, Any],
        *,
        provider: Any = None,
        roi_names: list[str] | None = None,
        project_path: str | None = "/proj",
        open_editor: bool = True,
    ) -> tuple[AnalysisWindowPanel, MagicMock, MagicMock]:
        controller, pm = _make_controller(
            project_data, roi_names=roi_names, project_path=project_path
        )
        bus = MagicMock()
        panel = AnalysisWindowPanel(root, controller, event_bus=bus, class_names_provider=provider)
        if open_editor:
            panel.open_editor()
        root.update_idletasks()
        return panel, pm, bus

    @staticmethod
    def _tree_rows(panel: AnalysisWindowPanel, section: Any) -> list[tuple[str, ...]]:
        tree = panel._trees[section]
        return [tuple(tree.item(iid, "values")) for iid in tree.get_children()]

    def test_stored_window_is_loaded_into_the_sections(self, tkinter_root: Any) -> None:
        data = {PROJECT_KEY: _fixture_spec().model_dump(mode="json", by_alias=True)}
        panel, _pm, _bus = self._panel(tkinter_root, data)

        assert self._tree_rows(panel, "start") == [
            ("Class is absent", "start_box"),
            ("Class is absent", "experimenter"),
            ("Class is present", "rat"),
            ("…held for (seconds or frames)", "3 frames"),
        ]
        assert len(self._tree_rows(panel, "stop")) == 4
        assert panel.combinator_vars["stop"].get() == "any of (the first one wins)"
        assert str(panel._preview.cget("text")).startswith("Start: at the same time:")  # type: ignore[union-attr]

    def test_add_line_appends_to_the_chosen_section(self, tkinter_root: Any) -> None:
        panel, pm, _bus = self._panel(tkinter_root, {})

        panel.target_section.set("Stop")
        panel._refresh_kind_choices()
        panel.row_kind.set("End of the video")
        panel._on_kind_changed()
        panel.add_line()

        assert panel.drafts["stop"].rows == (ConditionRow(kind="end_of_video"),)
        assert self._tree_rows(panel, "stop") == [("End of the video", "")]
        assert "(not saved yet)" in str(panel._preview.cget("text"))  # type: ignore[union-attr]
        pm.save_project.assert_not_called()

    def test_start_section_does_not_offer_stop_only_lines(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {})

        panel.target_section.set("Start")
        panel._refresh_kind_choices()
        offered = list(panel._kind_combo["values"])  # type: ignore[index]

        assert "End of the video" not in offered
        assert "Time after the start" not in offered
        panel.target_section.set("Stop")
        panel._refresh_kind_choices()
        assert "End of the video" in list(panel._kind_combo["values"])  # type: ignore[index]

    def test_incomplete_line_is_not_added(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {})

        panel.row_kind.set("Class is present")
        panel._on_kind_changed()
        panel.row_target.set("")
        panel.add_line()

        assert panel.drafts["start"].rows == ()
        assert panel._status.cget("text") == "Type or choose a class name."  # type: ignore[union-attr]

    def test_role_label_becomes_a_role_token(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {})

        panel.row_kind.set("Class is absent")
        panel._on_kind_changed()
        panel.row_target.set("Role: context (any context class)")
        panel.add_line()

        assert panel.drafts["start"].rows == (ConditionRow(kind="class_absent", role="context"),)

    def test_hold_line_reads_number_and_unit(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {})

        panel.row_kind.set("…held for (seconds or frames)")
        panel._on_kind_changed()
        panel.row_number.set("1,5")
        panel.row_unit.set("seconds")

        assert panel.read_line() == ConditionRow(kind="hold", value=1.5, unit="seconds")

    def test_roi_lines_offer_the_project_rois(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {}, roi_names=["Goal", "Start"])

        panel.row_kind.set("Subject enters ROI")
        panel._on_kind_changed()

        assert list(panel._target_combo["values"]) == ["Goal", "Start"]  # type: ignore[index]
        assert str(panel._target_combo.cget("state")) == "readonly"  # type: ignore[union-attr]

    def test_class_names_free_text_without_provider(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {})

        panel.row_kind.set("Class is present")
        panel._on_kind_changed()

        assert str(panel._target_combo.cget("state")) == "normal"  # type: ignore[union-attr]
        assert list(panel._target_combo["values"]) == list(role_labels().values())  # type: ignore[index]

    def test_class_names_from_provider_are_a_closed_list(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {}, provider=lambda: ["rat", "experimenter"])

        panel.row_kind.set("Class is present")
        panel._on_kind_changed()

        values = list(panel._target_combo["values"])  # type: ignore[index]
        assert values[-2:] == ["rat", "experimenter"]
        assert str(panel._target_combo.cget("state")) == "readonly"  # type: ignore[union-attr]

    def test_failing_provider_falls_back_to_free_text(self, tkinter_root: Any) -> None:
        def broken() -> list[str]:
            raise RuntimeError("no weight")

        panel, _pm, _bus = self._panel(tkinter_root, {}, provider=broken)
        panel.row_kind.set("Class is present")
        panel._on_kind_changed()

        assert str(panel._target_combo.cget("state")) == "normal"  # type: ignore[union-attr]

    def test_save_persists_and_publishes(self, tkinter_root: Any) -> None:
        data: dict[str, Any] = {}
        panel, pm, bus = self._panel(tkinter_root, data)
        panel.drafts = {
            "start": _section(*BARNES_START_ROWS),
            "stop": _section(*BARNES_STOP_ROWS, combinator="any_of"),
        }

        assert panel.save() is True

        assert data[PROJECT_KEY] == _fixture_spec().model_dump(mode="json", by_alias=True)
        pm.save_project.assert_called_once()
        (payload,) = _published_payloads(bus)
        assert payload.spec == data[PROJECT_KEY]
        assert payload.spec_hash == spec_hash(_fixture_spec())
        assert panel._status.cget("text") == "Analysis window saved."  # type: ignore[union-attr]

    def test_save_options(self, tkinter_root: Any) -> None:
        data: dict[str, Any] = {}
        panel, _pm, _bus = self._panel(tkinter_root, data)
        panel.drafts = {"start": _section(ConditionRow(kind="manual")), "stop": SectionDraft()}
        panel.on_start_not_met.set("Leave the metrics empty")
        panel.on_stop.set("End the live session")

        assert panel.save() is True
        assert data[PROJECT_KEY]["on_start_not_met"] == "empty"
        assert data[PROJECT_KEY]["on_stop"] == "end_session"

    def test_save_without_project_path_applies_in_memory(self, tkinter_root: Any) -> None:
        data: dict[str, Any] = {}
        panel, pm, bus = self._panel(tkinter_root, data, project_path=None)
        panel.drafts = {"start": _section(ConditionRow(kind="manual")), "stop": SectionDraft()}

        assert panel.save() is True
        assert data[PROJECT_KEY]["start"] == {"kind": "external", "source": "manual", "code": None}
        pm.save_project.assert_not_called()
        assert len(_published_payloads(bus)) == 1

    def test_invalid_draft_is_not_saved(self, tkinter_root: Any) -> None:
        data: dict[str, Any] = {}
        panel, pm, bus = self._panel(tkinter_root, data)
        panel.drafts = {
            "start": _section(ConditionRow(kind="hold", value=1.0)),
            "stop": SectionDraft(),
        }

        assert panel.save() is False
        assert PROJECT_KEY not in data
        pm.save_project.assert_not_called()
        bus.publish.assert_not_called()
        assert "Start, line 1" in panel._status.cget("text")  # type: ignore[union-attr]

    def test_failed_disk_write_rolls_back(self, tkinter_root: Any) -> None:
        previous = {"version": 1, "start": {"kind": "external", "source": "manual", "code": None}}
        data: dict[str, Any] = {PROJECT_KEY: previous}
        panel, pm, bus = self._panel(tkinter_root, data)
        pm.save_project.side_effect = OSError("disk full")
        panel.clear_all()

        assert panel.save() is False
        assert data[PROJECT_KEY] is previous
        bus.publish.assert_not_called()
        assert "disk full" in panel._status.cget("text")  # type: ignore[union-attr]

    def test_clearing_saves_none(self, tkinter_root: Any) -> None:
        data = {PROJECT_KEY: _fixture_spec().model_dump(mode="json", by_alias=True)}
        panel, _pm, bus = self._panel(tkinter_root, data)

        panel.clear_all()
        assert panel.save() is True

        assert data[PROJECT_KEY] is None
        (payload,) = _published_payloads(bus)
        assert payload.spec is None
        assert payload.spec_hash is None

    def test_barnes_preset_fills_the_editor_without_saving(self, tkinter_root: Any) -> None:
        data: dict[str, Any] = {}
        panel, pm, _bus = self._panel(tkinter_root, data, open_editor=False)

        panel.apply_barnes_preset()

        assert panel._editor is not None, "the preset opens the editor for review"
        assert len(self._tree_rows(panel, "stop")) == 4
        assert panel.current_spec() == barnes_maze_preset()
        assert PROJECT_KEY not in data
        pm.save_project.assert_not_called()
        assert panel._status.cget("text") == "Preset loaded. Review the lines, then Save."  # type: ignore[union-attr]

    def test_barnes_preset_warns_about_missing_classes(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {}, provider=lambda: ["rat", "zebrafish"])

        panel.apply_barnes_preset()

        status = panel._status.cget("text")  # type: ignore[union-attr]
        assert "'start_box', 'experimenter'" in status

    def test_window_written_elsewhere_is_described_and_flagged(self, tkinter_root: Any) -> None:
        spec = WindowSpec(start=TimeReached(clock="wall", at_s=3.0))
        data = {PROJECT_KEY: spec.model_dump(mode="json", by_alias=True)}
        panel, _pm, _bus = self._panel(tkinter_root, data)

        assert panel.drafts["start"] == SectionDraft()
        assert panel._notice.winfo_manager()  # type: ignore[union-attr]
        assert "3 s of clock time" in str(panel._preview.cget("text"))  # type: ignore[union-attr]

    def test_corrupt_window_is_flagged(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {PROJECT_KEY: {"version": 99}})

        assert panel._notice.winfo_manager()  # type: ignore[union-attr]
        assert "could not be read" in str(panel._notice.cget("text"))  # type: ignore[union-attr]

    def test_project_switch_reloads(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {})
        _new_controller, new_pm = _make_controller(
            {PROJECT_KEY: external_trigger_preset().model_dump(mode="json", by_alias=True)}
        )

        panel.on_project_manager_replaced(new_pm)

        assert panel.project_manager is new_pm
        assert panel.drafts["start"].rows == (ConditionRow(kind="arduino", value=1.0),)
        assert panel.on_stop.get() == "End the live session"

    def test_revert_discards_unsaved_lines(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {})
        panel.drafts["start"] = _section(ConditionRow(kind="manual"))

        panel.refresh()

        assert panel.drafts["start"] == SectionDraft()

    def test_remove_and_move_lines(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {})
        panel.drafts["stop"] = _section(*BARNES_STOP_ROWS)
        panel._render_sections()
        tree = panel._trees["stop"]

        tree.selection_set("3")
        panel.move_selected("stop", -1)
        assert [row.kind for row in panel.drafts["stop"].rows] == [
            "end_of_video",
            "class_absent",
            "delay_after_start",
            "hold",
        ]

        panel._trees["stop"].selection_set("0")
        panel.remove_selected("stop")
        assert [row.kind for row in panel.drafts["stop"].rows] == [
            "class_absent",
            "delay_after_start",
            "hold",
        ]

    def test_combinator_change_updates_the_draft(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {})

        panel.combinator_vars["start"].set("in sequence (in this order)")
        panel._on_combinator_changed("start")

        assert panel.drafts["start"].combinator == "sequence"

    def test_editor_opens_in_its_own_window(self, tkinter_root: Any) -> None:
        data = {PROJECT_KEY: _fixture_spec().model_dump(mode="json", by_alias=True)}
        panel, _pm, _bus = self._panel(tkinter_root, data, open_editor=False)
        assert panel._editor is None
        assert panel._trees == {}
        assert str(panel._preview.cget("text")).startswith("Start:")  # type: ignore[union-attr]

        panel.open_editor()
        editor = panel._editor
        assert editor is not None and editor.winfo_exists()
        assert len(self._tree_rows(panel, "start")) == 4
        assert panel._editor_preview.cget("text") == panel._preview.cget("text")  # type: ignore[union-attr]

        panel.open_editor()
        assert panel._editor is editor

    def test_closing_the_editor_keeps_unsaved_lines(self, tkinter_root: Any) -> None:
        panel, pm, _bus = self._panel(tkinter_root, {})
        panel.drafts["start"] = _section(ConditionRow(kind="manual"))
        panel._on_draft_changed()
        editor = panel._editor
        assert editor is not None

        panel.close_editor()

        assert not editor.winfo_exists()
        assert panel._editor is None and panel._trees == {} and panel._kind_combo is None
        assert panel.drafts["start"].rows == (ConditionRow(kind="manual"),)
        assert "(not saved yet)" in str(panel._preview.cget("text"))  # type: ignore[union-attr]
        pm.save_project.assert_not_called()
        panel.close_editor()  # closing twice is harmless

    def test_status_reaches_both_windows(self, tkinter_root: Any) -> None:
        panel, _pm, _bus = self._panel(tkinter_root, {})
        panel.drafts["start"] = _section(ConditionRow(kind="hold", value=1.0))

        panel.save()

        assert panel._status.cget("text") == panel._editor_status.cget("text")  # type: ignore[union-attr]
        assert str(panel._status.cget("foreground")) == "red"  # type: ignore[union-attr]

    def test_destroyed_panel_ignores_refresh(self, tkinter_root: Any) -> None:
        panel, pm, _bus = self._panel(tkinter_root, {})
        panel.destroy()
        pm.project_data[PROJECT_KEY] = {"version": 1}

        panel.refresh()

        assert panel.is_alive() is False

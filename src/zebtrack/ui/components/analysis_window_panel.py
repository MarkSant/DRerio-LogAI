"""Project-scoped editor for the analysis window's START/STOP conditions (ADR-011).

The researcher builds the window from typed lines — "class absent", "held for",
"subject enters ROI", "Arduino signal", … — grouped in two sections, Start and
Stop, each combined by "all of", "any of" or "in sequence". The editor turns those
lines into a :class:`~zebtrack.core.conditions.WindowSpec` and stores it in
``project_data["analysis_window"]`` (``spec.model_dump(mode="json")``), or ``None``
for "analyse the whole recording".

The module has two halves:

- **Pure** (top): the line model (:class:`ConditionRow`, :class:`SectionDraft`),
  :func:`build_window_spec` / :func:`drafts_from_spec` (lines ⇄ spec), the readable
  preview (:func:`describe_window_spec`) and the friendly validation messages.
  None of it touches Tk, so it is tested and mutation-checked headless.
- **Tk** (bottom): :class:`AnalysisWindowPanel`, which only shuttles widget values
  into that model and back.

How lines become a spec — the one rule worth knowing:

- Class lines ("present"/"absent") are *levels*: true or false on every frame. A
  section's class lines are grouped into ONE level (all of them together, or any
  of them for "any of") and wrapped in a ``Persist``. The optional "held for" line
  sets how long that group must stay true; without it the group fires on its first
  true frame (``Hold(frames=1)``).
- Every other line is a *trigger* that fires once. The class group takes the place
  of the first class line among the triggers, and the section's combinator joins
  them: "all of" → ``AllOf``, "any of" → ``FirstOf``, "in sequence" → ``Sequence``.
  A section with a single element is that element, with no wrapper.

That is exactly the shape of the Barnes acceptance spec, so the preset round-trips
through the editor without changing its hash.

Every ``kind``/``role``/combinator token here is a persistence or model contract
and is never translated; only the labels built by the ``*_labels()`` functions are.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from tkinter import StringVar, Toplevel, ttk
from typing import Any, Literal, cast, get_args

import structlog
from pydantic import ValidationError

from zebtrack.core.conditions import (
    AllOf,
    AllOfLevel,
    AnyOfLevel,
    ClassPresence,
    ClassTarget,
    ConditionNode,
    Delay,
    EndOfStream,
    External,
    FirstOf,
    FrameReached,
    Hold,
    LevelNode,
    Not,
    Persist,
    RoiEdge,
    RoiInside,
    Sequence,
    TimeReached,
    TriggerNode,
    WindowSpec,
    iter_nodes,
    spec_hash,
)
from zebtrack.core.conditions.presets import barnes_maze_preset
from zebtrack.i18n import _
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents

log = structlog.get_logger()

#: Key of the spec inside ``project_data`` (persistence contract, ADR-012).
PROJECT_KEY = "analysis_window"

RowKind = Literal[
    "class_present",
    "class_absent",
    "hold",
    "roi_enter",
    "roi_exit",
    "video_time",
    "frame",
    "delay_after_start",
    "arduino",
    "manual",
    "end_of_video",
]
SectionName = Literal["start", "stop"]
Combinator = Literal["all_of", "any_of", "sequence"]
HoldUnit = Literal["seconds", "frames"]
Role = Literal["subject", "context"]
OnStartNotMet = Literal["whole_recording", "empty"]
OnStop = Literal["mark", "end_session"]

#: Every line type, in the order the "Condition" dropdown lists them.
ROW_KINDS: tuple[RowKind, ...] = get_args(RowKind)
#: Lines that only make sense once the window has started.
STOP_ONLY_KINDS: frozenset[RowKind] = frozenset({"delay_after_start", "end_of_video"})
#: Lines that are levels (grouped into one ``Persist``), not triggers.
LEVEL_KINDS: frozenset[RowKind] = frozenset({"class_present", "class_absent"})
#: Lines whose ``target`` is required (class name or role, ROI name).
TARGET_KINDS: frozenset[RowKind] = frozenset(
    {"class_present", "class_absent", "roi_enter", "roi_exit"}
)
#: Lines that need a number, and lines where that number must be a whole number.
NUMBER_REQUIRED_KINDS: frozenset[RowKind] = frozenset(
    {"hold", "video_time", "frame", "delay_after_start"}
)
NUMBER_OPTIONAL_KINDS: frozenset[RowKind] = frozenset({"arduino"})
INTEGER_KINDS: frozenset[RowKind] = frozenset({"frame", "arduino"})


# ---------------------------------------------------------------------------
# Labels — functions, never constants: ``_()`` resolves the catalogue on call.
# ---------------------------------------------------------------------------


def section_labels() -> dict[SectionName, str]:
    return {"start": _("Start"), "stop": _("Stop")}


def row_kind_labels() -> dict[RowKind, str]:
    return {
        "class_present": _("Class is present"),
        "class_absent": _("Class is absent"),
        "hold": _("…held for (seconds or frames)"),
        "roi_enter": _("Subject enters ROI"),
        "roi_exit": _("Subject leaves ROI"),
        "video_time": _("Video time reaches"),
        "frame": _("Frame number reaches"),
        "delay_after_start": _("Time after the start"),
        "arduino": _("Arduino signal"),
        "manual": _("Manual signal"),
        "end_of_video": _("End of the video"),
    }


def combinator_labels() -> dict[Combinator, str]:
    return {
        "all_of": _("all of"),
        "any_of": _("any of (the first one wins)"),
        "sequence": _("in sequence (in this order)"),
    }


def hold_unit_labels() -> dict[HoldUnit, str]:
    return {"seconds": _("seconds"), "frames": _("frames")}


def role_labels() -> dict[Role, str]:
    return {
        "subject": _("Role: subject (any subject class)"),
        "context": _("Role: context (any context class)"),
    }


def on_start_not_met_labels() -> dict[OnStartNotMet, str]:
    return {
        "whole_recording": _("Use the whole recording"),
        "empty": _("Leave the metrics empty"),
    }


def on_stop_labels() -> dict[OnStop, str]:
    return {
        "mark": _("Only mark the stop"),
        "end_session": _("End the live session"),
    }


def intro_text() -> str:
    return _(
        "Optional. Choose when the analysis STARTS and STOPS inside each recording. "
        "The video is always recorded in full; only the metrics are restricted to the "
        "window, so changing a condition only needs a new analysis."
    )


def external_spec_notice() -> str:
    return _(
        "This window was written outside this editor and cannot be shown as lines. "
        "Its rule is described above; saving here replaces it."
    )


def corrupt_spec_notice() -> str:
    return _(
        "The saved analysis window could not be read and is being ignored. "
        "Save a new one, or clear it, to fix the project."
    )


# ---------------------------------------------------------------------------
# Line model
# ---------------------------------------------------------------------------


class SpecBuildError(ValueError):
    """The lines cannot become a :class:`WindowSpec`.

    The message is already translated and meant for the user. Callers display it;
    they never branch on it.
    """


@dataclass(frozen=True)
class ConditionRow:
    """One line of a section.

    Attributes:
        kind: Line type (see :data:`ROW_KINDS`).
        target: Class name (class lines) or ROI name (ROI lines); ignored otherwise.
        role: Class role instead of a class name (class lines only).
        value: Seconds, frame number, hold amount or Arduino code, by kind.
        unit: Unit of a "held for" line.
    """

    kind: RowKind
    target: str = ""
    role: Role | None = None
    value: float | None = None
    unit: HoldUnit = "frames"


@dataclass(frozen=True)
class SectionDraft:
    """The lines of one section and how they combine."""

    combinator: Combinator = "all_of"
    rows: tuple[ConditionRow, ...] = field(default_factory=tuple)


def format_number(value: float) -> str:
    """``3.0`` → ``"3"``, ``2.5`` → ``"2.5"`` — for labels, never for storage."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def parse_number(text: str, *, integer: bool) -> float | None:
    """Parse a number typed by the user; blank means "not given".

    Accepts a decimal comma (``"2,5"``), since the app is used with pt-BR keyboards.

    Raises:
        SpecBuildError: not a number, or not a whole number when ``integer``.
    """
    cleaned = str(text).strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        raise SpecBuildError(
            _("'{value}' is not a number.").format(value=str(text).strip())
        ) from None
    if integer and not number.is_integer():
        raise SpecBuildError(_("'{value}' must be a whole number.").format(value=str(text).strip()))
    return number


# ---------------------------------------------------------------------------
# Friendly validation messages
# ---------------------------------------------------------------------------


def _validation_type_messages() -> dict[str, str]:
    """Pydantic error ``type`` → user text. Keyed by type, never by message text."""
    return {
        "class_name_blank": _("Type or choose a class name."),
        "class_target_needs_exactly_one": _("Choose either a class or a role, not both."),
        "hold_needs_exactly_one": _("A 'held for' line needs a number of seconds or frames."),
        "string_too_short": _("Choose an ROI."),
        "too_short": _("Add at least one condition."),
        "start_refers_to_itself": _("'Time after the start' can only be used in Stop."),
        "start_uses_end_of_stream": _("'End of the video' can only be used in Stop."),
        "finite_number": _("The number must be finite."),
        "int_from_float": _("The number must be a whole number."),
    }


def friendly_validation_message(exc: ValidationError) -> str:
    """Turn a pydantic error into one readable sentence per distinct problem."""
    known = _validation_type_messages()
    messages: list[str] = []
    for error in exc.errors():
        error_type = str(error.get("type", ""))
        ctx = error.get("ctx") or {}
        if error_type == "greater_than":
            text = _("The number must be greater than {limit}.").format(
                limit=format_number(float(ctx.get("gt", 0)))
            )
        elif error_type == "greater_than_equal":
            text = _("The number must be at least {limit}.").format(
                limit=format_number(float(ctx.get("ge", 0)))
            )
        elif error_type == "less_than_equal":
            text = _("The number must be at most {limit}.").format(
                limit=format_number(float(ctx.get("le", 0)))
            )
        else:
            text = known.get(error_type, _("A value is not valid."))
        if text not in messages:
            messages.append(text)
    return " ".join(messages) if messages else _("A value is not valid.")


def _line_error(section: SectionName, index: int, message: str) -> SpecBuildError:
    return SpecBuildError(
        _("{section}, line {line}: {message}").format(
            section=section_labels()[section], line=index, message=message
        )
    )


# ---------------------------------------------------------------------------
# Lines → spec
# ---------------------------------------------------------------------------


def _class_target(row: ConditionRow) -> ClassTarget:
    if row.role is not None:
        return ClassTarget.of_role(row.role)
    return ClassTarget.of_class(row.target)


def _hold(row: ConditionRow | None) -> Hold:
    """The group's hold: the "held for" line, or one frame (= "as soon as")."""
    if row is None or row.value is None:
        return Hold(frames=1)
    if row.unit == "seconds":
        return Hold(seconds=row.value)
    return Hold(frames=int(row.value))


def _row_trigger(row: ConditionRow) -> TriggerNode:
    """Trigger of a line that is neither a class line nor "held for"."""
    value = row.value
    if row.kind == "roi_enter":
        return RoiEdge(roi=row.target.strip(), edge="enter")
    if row.kind == "roi_exit":
        return RoiEdge(roi=row.target.strip(), edge="exit")
    if row.kind == "video_time":
        return TimeReached(clock="video", at_s=cast(float, value))
    if row.kind == "frame":
        return FrameReached(frame=int(cast(float, value)))
    if row.kind == "delay_after_start":
        return Delay(after="start", seconds=cast(float, value))
    if row.kind == "arduino":
        return External(source="arduino", code=None if value is None else int(value))
    if row.kind == "manual":
        return External(source="manual", code=None)
    return EndOfStream()


def check_row(row: ConditionRow, section: SectionName) -> None:
    """Reject a line that cannot be part of ``section`` (message without line number).

    Builds the line's own node, so range rules (a negative time, a zero hold) are
    caught when the line is ADDED, not only when the whole window is saved.

    Raises:
        SpecBuildError: translated, user-facing.
    """
    if section == "start" and row.kind in STOP_ONLY_KINDS:
        raise SpecBuildError(
            _("'{condition}' can only be used in Stop.").format(
                condition=row_kind_labels()[row.kind]
            )
        )
    if row.kind in ("roi_enter", "roi_exit") and not row.target.strip():
        raise SpecBuildError(_("Choose an ROI."))
    if row.kind in NUMBER_REQUIRED_KINDS and row.value is None:
        raise SpecBuildError(_("Type a number."))
    whole_number_needed = row.kind in INTEGER_KINDS or (row.kind == "hold" and row.unit == "frames")
    if whole_number_needed and row.value is not None and not float(row.value).is_integer():
        raise SpecBuildError(_("The number must be a whole number."))
    try:
        if row.kind in LEVEL_KINDS:
            _class_target(row)
        elif row.kind == "hold":
            _hold(row)
        else:
            _row_trigger(row)
    except ValidationError as exc:
        raise SpecBuildError(friendly_validation_message(exc)) from None


def _class_group(
    level_rows: list[ConditionRow], hold_row: ConditionRow | None, combinator: Combinator
) -> Persist:
    levels: list[LevelNode] = [
        ClassPresence(target=_class_target(row), present=row.kind == "class_present")
        for row in level_rows
    ]
    level: LevelNode
    if len(levels) == 1:
        level = levels[0]
    elif combinator == "any_of":
        level = AnyOfLevel(children=tuple(levels))
    else:
        level = AllOfLevel(children=tuple(levels))
    return Persist(level=level, hold=_hold(hold_row))


def build_trigger(draft: SectionDraft, section: SectionName) -> TriggerNode | None:
    """Turn one section's lines into its trigger; ``None`` for an empty section.

    Raises:
        SpecBuildError: a line is incomplete or invalid; the message names the
            section and the line.
    """
    rows = draft.rows
    if not rows:
        return None
    for index, row in enumerate(rows, start=1):
        try:
            check_row(row, section)
        except SpecBuildError as exc:
            raise _line_error(section, index, str(exc)) from None

    hold_lines = [index for index, row in enumerate(rows, start=1) if row.kind == "hold"]
    level_rows = [row for row in rows if row.kind in LEVEL_KINDS]
    if len(hold_lines) > 1:
        raise _line_error(section, hold_lines[1], _("Use a single 'held for' line per section."))
    if hold_lines and not level_rows:
        raise _line_error(
            section,
            hold_lines[0],
            _("'Held for' applies to the class lines; add a class line first."),
        )
    hold_row = rows[hold_lines[0] - 1] if hold_lines else None

    children: list[TriggerNode] = []
    group_added = False
    for row in rows:
        if row.kind == "hold":
            continue
        if row.kind in LEVEL_KINDS:
            if not group_added:
                children.append(_class_group(level_rows, hold_row, draft.combinator))
                group_added = True
            continue
        children.append(_row_trigger(row))

    if len(children) == 1:
        return children[0]
    if draft.combinator == "any_of":
        return FirstOf(children=tuple(children))
    if draft.combinator == "sequence":
        return Sequence(children=tuple(children))
    return AllOf(children=tuple(children))


def build_window_spec(
    start: SectionDraft,
    stop: SectionDraft,
    *,
    on_start_not_met: OnStartNotMet = "whole_recording",
    on_stop: OnStop = "mark",
) -> WindowSpec | None:
    """Build the project's window; ``None`` when both sections are empty.

    With no condition at all the options have nothing to act on, so the result is
    the "whole recording" value, ``None``, rather than a spec equivalent to it.

    Raises:
        SpecBuildError: with a translated, user-facing message.
    """
    start_node = build_trigger(start, "start")
    stop_node = build_trigger(stop, "stop")
    if start_node is None and stop_node is None:
        return None
    try:
        return WindowSpec(
            start=start_node,
            stop=stop_node,
            on_start_not_met=on_start_not_met,
            on_stop=on_stop,
        )
    except ValidationError as exc:
        raise SpecBuildError(friendly_validation_message(exc)) from None


# ---------------------------------------------------------------------------
# Spec → lines
# ---------------------------------------------------------------------------


def _row_for_trigger(node: TriggerNode) -> ConditionRow | None:
    """The line for a simple trigger; ``None`` when no line type expresses it."""
    if isinstance(node, RoiEdge):
        kind: RowKind = "roi_enter" if node.edge == "enter" else "roi_exit"
        return ConditionRow(kind=kind, target=node.roi)
    if isinstance(node, TimeReached) and node.clock == "video":
        return ConditionRow(kind="video_time", value=node.at_s)
    if isinstance(node, FrameReached):
        return ConditionRow(kind="frame", value=float(node.frame))
    if isinstance(node, Delay) and node.after == "start":
        return ConditionRow(kind="delay_after_start", value=node.seconds)
    if isinstance(node, External) and node.source == "arduino":
        return ConditionRow(kind="arduino", value=None if node.code is None else float(node.code))
    if isinstance(node, External) and node.code is None:
        return ConditionRow(kind="manual")
    if isinstance(node, EndOfStream):
        return ConditionRow(kind="end_of_video")
    return None


def _rows_for_persist(node: Persist) -> tuple[list[ConditionRow], Combinator | None] | None:
    """Class lines (+ "held for") of a ``Persist`` and the combinator its level implies."""
    level = node.level
    implied: Combinator | None = None
    presences: tuple[LevelNode, ...] = (level,)
    if isinstance(level, AllOfLevel):
        presences, implied = level.children, "all_of"
    elif isinstance(level, AnyOfLevel):
        presences, implied = level.children, "any_of"
    rows: list[ConditionRow] = []
    for presence in presences:
        if not isinstance(presence, ClassPresence):
            return None
        rows.append(
            ConditionRow(
                kind="class_present" if presence.present else "class_absent",
                target=presence.target.class_name or "",
                role=presence.target.role,
            )
        )
    if node.hold.seconds is not None:
        rows.append(ConditionRow(kind="hold", value=node.hold.seconds, unit="seconds"))
    elif node.hold.frames is not None and node.hold.frames != 1:
        rows.append(ConditionRow(kind="hold", value=float(node.hold.frames), unit="frames"))
    return rows, implied


def _section_from_trigger(node: TriggerNode | None) -> SectionDraft | None:
    """Candidate lines for one section; :func:`drafts_from_spec` verifies them."""
    if node is None:
        return SectionDraft()
    combinator: Combinator | None = None
    children: tuple[TriggerNode, ...] = (node,)
    if isinstance(node, AllOf):
        combinator, children = "all_of", node.children
    elif isinstance(node, FirstOf):
        combinator, children = "any_of", node.children
    elif isinstance(node, Sequence):
        combinator, children = "sequence", node.children

    rows: list[ConditionRow] = []
    implied: Combinator | None = None
    for child in children:
        if isinstance(child, Persist):
            parsed = _rows_for_persist(child)
            if parsed is None:
                return None
            class_rows, implied = parsed
            rows.extend(class_rows)
            continue
        row = _row_for_trigger(child)
        if row is None:
            return None
        rows.append(row)
    return SectionDraft(combinator=combinator or implied or "all_of", rows=tuple(rows))


def drafts_from_spec(spec: WindowSpec | None) -> tuple[SectionDraft, SectionDraft] | None:
    """Lines that rebuild ``spec`` exactly; ``None`` when the editor cannot show it.

    A spec written by hand (or by a later version) can nest conditions the line
    editor has no way to express — two class groups, a one-child wrapper, a
    ``Sequence`` time limit, a confidence filter. The candidate lines are rebuilt
    and compared with the original, so anything the lines would silently change
    is reported as ``None``: the panel then describes the stored rule and warns
    that saving replaces it, instead of showing an approximation.
    """
    if spec is None:
        return SectionDraft(), SectionDraft()
    start = _section_from_trigger(spec.start)
    stop = _section_from_trigger(spec.stop)
    if start is None or stop is None:
        return None
    try:
        rebuilt = build_window_spec(
            start, stop, on_start_not_met=spec.on_start_not_met, on_stop=spec.on_stop
        )
    except SpecBuildError:
        return None
    if rebuilt is None and spec.start is None and spec.stop is None:
        # A condition-free spec IS the whole recording; its options act on nothing.
        return start, stop
    if rebuilt != spec:
        return None
    return start, stop


# ---------------------------------------------------------------------------
# Readable preview
# ---------------------------------------------------------------------------


def _describe_target(target: ClassTarget) -> str:
    if target.role == "subject":
        return _("any subject class")
    if target.role == "context":
        return _("any context class")
    return f"'{target.class_name}'"


def describe_level(node: LevelNode) -> str:
    """One phrase for a level node."""
    if isinstance(node, ClassPresence):
        target = _describe_target(node.target)
        if node.min_count == 1:
            text = (
                _("{target} is visible") if node.present else _("{target} is not visible")
            ).format(target=target)
        elif node.present:
            text = _("at least {count} of {target} visible").format(
                count=node.min_count, target=target
            )
        else:
            text = _("fewer than {count} of {target} visible").format(
                count=node.min_count, target=target
            )
        if node.min_confidence is not None:
            text = _("{condition} (confidence ≥ {value})").format(
                condition=text, value=format_number(node.min_confidence)
            )
        return text
    if isinstance(node, RoiInside):
        if node.state == "inside":
            return _("the subject is inside ROI '{roi}'").format(roi=node.roi)
        return _("the subject is outside ROI '{roi}'").format(roi=node.roi)
    if isinstance(node, Not):
        return _("not ({condition})").format(condition=describe_level(node.child))
    if isinstance(node, AllOfLevel):
        return _("at the same time: {conditions}").format(
            conditions="; ".join(describe_level(child) for child in node.children)
        )
    return _("any of: {conditions}").format(
        conditions="; ".join(describe_level(child) for child in node.children)
    )


def describe_trigger(node: TriggerNode) -> str:
    """One phrase for a trigger node (recursive)."""
    if isinstance(node, Persist):
        level = describe_level(node.level)
        if node.hold.seconds is not None:
            return _("{condition}, for {seconds} s").format(
                condition=level, seconds=format_number(node.hold.seconds)
            )
        if node.hold.frames == 1:
            return _("as soon as {condition}").format(condition=level)
        return _("{condition}, for {frames} frame(s) in a row").format(
            condition=level, frames=node.hold.frames
        )
    if isinstance(node, RoiEdge):
        if node.edge == "enter":
            return _("the subject enters ROI '{roi}'").format(roi=node.roi)
        return _("the subject leaves ROI '{roi}'").format(roi=node.roi)
    if isinstance(node, TimeReached):
        if node.clock == "video":
            return _("the video reaches {seconds} s").format(seconds=format_number(node.at_s))
        return _("{seconds} s of clock time have passed").format(seconds=format_number(node.at_s))
    if isinstance(node, FrameReached):
        return _("frame {frame} is reached").format(frame=node.frame)
    if isinstance(node, Delay):
        if isinstance(node.after, str):
            return _("{seconds} s after the start").format(seconds=format_number(node.seconds))
        return _("{seconds} s after {condition}").format(
            seconds=format_number(node.seconds), condition=describe_trigger(node.after)
        )
    if isinstance(node, External):
        if node.source == "arduino":
            if node.code is None:
                return _("the Arduino sends any code")
            return _("the Arduino sends code {code}").format(code=node.code)
        if node.code is None:
            return _("the operator gives the manual signal")
        return _("the operator gives manual signal {code}").format(code=node.code)
    if isinstance(node, EndOfStream):
        return _("the video ends")
    items = "; ".join(describe_trigger(child) for child in node.children)
    if isinstance(node, FirstOf):
        return _("the first of: {conditions}").format(conditions=items)
    if isinstance(node, AllOf):
        return _("once all have happened: {conditions}").format(conditions=items)
    if node.within_s is not None:
        return _("in this order, within {seconds} s: {conditions}").format(
            seconds=format_number(node.within_s), conditions=items
        )
    return _("in this order: {conditions}").format(conditions=items)


def describe_window_spec(spec: WindowSpec | None) -> str:
    """The rule in plain words, one line per part — the panel's preview."""
    if spec is None:
        return _("No analysis window: the whole recording is analysed.")
    lines = [
        _("Start: {condition}.").format(
            condition=describe_trigger(spec.start)
            if spec.start is not None
            else _("at the first processed frame")
        ),
        _("Stop: {condition}.").format(
            condition=describe_trigger(spec.stop)
            if spec.stop is not None
            else _("at the end of the recording")
        ),
    ]
    if spec.start is not None:
        if spec.on_start_not_met == "whole_recording":
            lines.append(
                _("If Start never happens, the whole recording is analysed (with a warning).")
            )
        else:
            lines.append(_("If Start never happens, the metrics are left empty."))
    if spec.on_stop == "end_session":
        lines.append(_("In a live session, Stop ends the recording."))
    return "\n".join(lines)


def describe_row(row: ConditionRow) -> str:
    """Detail column of a line in the table."""
    if row.kind in LEVEL_KINDS:
        if row.role is not None:
            return role_labels()[row.role]
        return row.target
    if row.kind in ("roi_enter", "roi_exit"):
        return row.target
    if row.kind == "hold":
        if row.value is None:
            return ""
        return f"{format_number(row.value)} {hold_unit_labels()[row.unit]}"
    if row.kind in ("video_time", "delay_after_start"):
        return (
            "" if row.value is None else _("{seconds} s").format(seconds=format_number(row.value))
        )
    if row.kind == "frame":
        return "" if row.value is None else format_number(row.value)
    if row.kind == "arduino":
        if row.value is None:
            return _("any code")
        return _("code {code}").format(code=format_number(row.value))
    return ""


def referenced_class_names(spec: WindowSpec | None) -> list[str]:
    """Class names a spec waits for, in order of first appearance (roles excluded)."""
    if spec is None:
        return []
    names: list[str] = []
    for root in (spec.start, spec.stop):
        if root is None:
            continue
        for node in iter_nodes(cast(ConditionNode, root)):
            if isinstance(node, ClassPresence) and node.target.class_name is not None:
                if node.target.class_name not in names:
                    names.append(node.target.class_name)
    return names


def missing_class_names(spec: WindowSpec | None, available: Iterable[str]) -> list[str]:
    """Class names the spec needs that the current weight does not declare.

    Both sides are compared normalized (the model normalizes stored names). An
    empty ``available`` means "unknown" — nothing is reported missing, because the
    provider is not wired yet and a warning about every class would be noise.
    """
    known = {_normalized_class_name(name) for name in available if name.strip()}
    if not known:
        return []
    return [name for name in referenced_class_names(spec) if name not in known]


def _normalized_class_name(name: str) -> str:
    """The model's own normalization (``"Start Box"`` → ``"start_box"``)."""
    return ClassTarget.of_class(name).class_name or ""


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def load_window_spec(project_data: Mapping[str, Any]) -> tuple[WindowSpec | None, bool]:
    """Read the stored window: ``(spec, corrupt)``.

    A value that does not validate degrades to ``(None, True)`` — the caller warns —
    rather than raising into the UI: a hand-edited project must still open.
    """
    raw = project_data.get(PROJECT_KEY)
    if raw is None:
        return None, False
    try:
        return WindowSpec.model_validate(raw), False
    except ValidationError as exc:
        log.warning("analysis_window_panel.load.invalid", errors=exc.error_count())
        return None, True


def store_window_spec(project_data: dict[str, Any], spec: WindowSpec | None) -> None:
    """Write ``spec`` (or ``None`` = whole recording) into ``project_data``."""
    project_data[PROJECT_KEY] = (
        None if spec is None else spec.model_dump(mode="json", by_alias=True)
    )


def _label_to_token(labels: Mapping[Any, str], label: str, default: Any) -> Any:
    for token, text in labels.items():
        if text == label:
            return token
    return default


# ---------------------------------------------------------------------------
# Tk panel
# ---------------------------------------------------------------------------


class AnalysisWindowPanel(ttk.Frame):
    """Start/Stop condition editor for the project's analysis window."""

    def __init__(
        self,
        parent: Any,
        controller: Any,
        *,
        event_bus: Any = None,
        class_names_provider: Callable[[], list[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.project_manager = controller.project_manager
        self.event_bus = event_bus
        self._class_names_provider = class_names_provider

        self.drafts: dict[SectionName, SectionDraft] = {
            "start": SectionDraft(),
            "stop": SectionDraft(),
        }
        self._stored_spec: WindowSpec | None = None
        self._dirty = False

        self.combinator_vars: dict[SectionName, StringVar] = {
            "start": StringVar(master=self),
            "stop": StringVar(master=self),
        }
        self.target_section = StringVar(master=self)
        self.row_kind = StringVar(master=self)
        self.row_target = StringVar(master=self)
        self.row_number = StringVar(master=self)
        self.row_unit = StringVar(master=self)
        self.on_start_not_met = StringVar(master=self)
        self.on_stop = StringVar(master=self)

        self._trees: dict[SectionName, ttk.Treeview] = {}
        self._kind_combo: ttk.Combobox | None = None
        self._target_combo: ttk.Combobox | None = None
        self._number_entry: ttk.Entry | None = None
        self._unit_combo: ttk.Combobox | None = None
        self._number_hint: ttk.Label | None = None
        self._preview: ttk.Label | None = None
        self._notice: ttk.Label | None = None
        self._status: ttk.Label | None = None
        # The editor lives in its own window: expanded inline it is ~840 px tall,
        # more than the zone tab's left column can give without hiding the zone
        # controls above it. Only the summary stays in the column.
        self._editor: Toplevel | None = None
        self._editor_preview: ttk.Label | None = None
        self._editor_status: ttk.Label | None = None

        self.target_section.set(section_labels()["start"])
        self.row_unit.set(hold_unit_labels()["frames"])

        self._build()
        self.refresh()

    def on_project_manager_replaced(self, new_manager: Any) -> None:
        """Adopt the ``ProjectManager`` that replaced the one we were built with.

        ``close_project`` swaps the instance; without this the panel would keep
        editing the CLOSED project's ``project_data``.
        """
        self.project_manager = new_manager
        self.refresh()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self) -> None:
        frame = ttk.LabelFrame(self, text=_("Analysis Window (Optional)"), padding=8)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=intro_text(), foreground="gray", wraplength=380, justify="left").pack(
            anchor="w", pady=(0, 4)
        )

        self._preview = ttk.Label(frame, text="", wraplength=380, justify="left")
        self._preview.pack(anchor="w", fill="x", pady=(0, 4))

        self._notice = ttk.Label(
            frame, text="", foreground="darkorange", wraplength=380, justify="left"
        )

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Button(top, text=_("Edit conditions…"), command=self.open_editor).pack(side="left")
        ttk.Button(top, text=_("Barnes maze preset"), command=self.apply_barnes_preset).pack(
            side="left", padx=4
        )

        self._status = ttk.Label(frame, text="", foreground="gray", wraplength=380)
        self._status.pack(anchor="w", pady=(4, 0))

    def open_editor(self) -> None:
        """Open (or raise) the Start/Stop editor window."""
        if self._editor is not None and self._editor_exists():
            self._editor.lift()
            return
        editor = Toplevel(self)
        editor.title(_("Analysis window: Start and Stop conditions"))
        editor.transient(self.winfo_toplevel())
        editor.protocol("WM_DELETE_WINDOW", self.close_editor)
        self._editor = editor

        body = ttk.Frame(editor, padding=10)
        body.pack(fill="both", expand=True)
        self._editor_preview = ttk.Label(body, text="", wraplength=420, justify="left")
        self._editor_preview.pack(anchor="w", fill="x")

        for section in ("start", "stop"):
            self._build_section(body, cast(SectionName, section))
        self._build_line_editor(body)
        self._build_options(body)

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text=_("Save"), command=self.save).pack(side="left")
        ttk.Button(actions, text=_("Revert"), command=self.refresh).pack(side="left", padx=4)
        ttk.Button(actions, text=_("Clear all"), command=self.clear_all).pack(side="left")
        ttk.Button(actions, text=_("Close"), command=self.close_editor).pack(side="right")
        self._editor_status = ttk.Label(body, text="", foreground="gray", wraplength=420)
        self._editor_status.pack(anchor="w", pady=(4, 0))

        self._render_sections()
        self._refresh_kind_choices()
        self._update_preview()

    def close_editor(self) -> None:
        """Close the editor window. Unsaved lines stay in memory until Revert."""
        editor, self._editor = self._editor, None
        self._trees = {}
        self._kind_combo = None
        self._target_combo = None
        self._number_entry = None
        self._unit_combo = None
        self._number_hint = None
        self._editor_preview = None
        self._editor_status = None
        if editor is not None:
            try:
                editor.destroy()
            # except Exception justified: the window may already be gone with
            # its parent; closing it twice is not an error.
            except Exception:
                log.debug("analysis_window_panel.close_editor.already_gone")

    def _editor_exists(self) -> bool:
        try:
            return self._editor is not None and bool(self._editor.winfo_exists())
        # except Exception justified: same as ``is_alive``.
        except Exception:
            return False

    def _build_section(self, parent: Any, section: SectionName) -> None:
        box = ttk.LabelFrame(parent, text=section_labels()[section], padding=4)
        box.pack(fill="x", pady=(6, 0))

        combine = ttk.Frame(box)
        combine.pack(fill="x")
        ttk.Label(combine, text=_("Combine the lines:")).pack(side="left")
        combo = ttk.Combobox(
            combine,
            textvariable=self.combinator_vars[section],
            state="readonly",
            width=26,
            values=list(combinator_labels().values()),
        )
        combo.pack(side="left", padx=(4, 0))
        combo.bind("<<ComboboxSelected>>", lambda _event: self._on_combinator_changed(section))

        tree = ttk.Treeview(box, columns=("condition", "detail"), show="headings", height=4)
        tree.heading("condition", text=_("Condition"))
        tree.heading("detail", text=_("Value"))
        tree.column("condition", width=190, anchor="w")
        tree.column("detail", width=170, anchor="w")
        tree.pack(fill="x", pady=(4, 0))
        self._trees[section] = tree

        buttons = ttk.Frame(box)
        buttons.pack(fill="x", pady=(2, 0))
        ttk.Button(
            buttons, text=_("Remove selected"), command=lambda: self.remove_selected(section)
        ).pack(side="left")
        ttk.Button(
            buttons, text=_("Move up"), command=lambda: self.move_selected(section, -1)
        ).pack(side="left", padx=4)

    def _build_line_editor(self, parent: Any) -> None:
        editor = ttk.LabelFrame(parent, text=_("Add a line"), padding=4)
        editor.pack(fill="x", pady=(6, 0))

        row1 = ttk.Frame(editor)
        row1.pack(fill="x")
        ttk.Label(row1, text=_("To:")).pack(side="left")
        section_combo = ttk.Combobox(
            row1,
            textvariable=self.target_section,
            state="readonly",
            width=8,
            values=list(section_labels().values()),
        )
        section_combo.pack(side="left", padx=(2, 8))
        section_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_kind_choices())
        ttk.Label(row1, text=_("Condition:")).pack(side="left")
        self._kind_combo = ttk.Combobox(
            row1, textvariable=self.row_kind, state="readonly", width=28
        )
        self._kind_combo.pack(side="left", padx=(2, 0))
        self._kind_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_kind_changed())

        row2 = ttk.Frame(editor)
        row2.pack(fill="x", pady=(4, 0))
        ttk.Label(row2, text=_("Name:")).pack(side="left")
        self._target_combo = ttk.Combobox(row2, textvariable=self.row_target, width=22)
        self._target_combo.pack(side="left", padx=(2, 8))
        ttk.Label(row2, text=_("Number:")).pack(side="left")
        self._number_entry = ttk.Entry(row2, textvariable=self.row_number, width=8)
        self._number_entry.pack(side="left", padx=(2, 4))
        self._unit_combo = ttk.Combobox(
            row2,
            textvariable=self.row_unit,
            state="readonly",
            width=8,
            values=list(hold_unit_labels().values()),
        )
        self._unit_combo.pack(side="left")

        self._number_hint = ttk.Label(editor, text="", foreground="gray", wraplength=380)
        self._number_hint.pack(anchor="w", pady=(2, 0))

        ttk.Button(editor, text=_("Add line"), command=self.add_line).pack(anchor="w", pady=(4, 0))

    def _build_options(self, parent: Any) -> None:
        options = ttk.Frame(parent)
        options.pack(fill="x", pady=(6, 0))
        ttk.Label(options, text=_("If Start never happens:")).grid(row=0, column=0, sticky="w")
        start_combo = ttk.Combobox(
            options,
            textvariable=self.on_start_not_met,
            state="readonly",
            width=26,
            values=list(on_start_not_met_labels().values()),
        )
        start_combo.grid(row=0, column=1, sticky="w", padx=(4, 0))
        start_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_draft_changed())
        ttk.Label(options, text=_("When Stop happens:")).grid(row=1, column=0, sticky="w")
        stop_combo = ttk.Combobox(
            options,
            textvariable=self.on_stop,
            state="readonly",
            width=26,
            values=list(on_stop_labels().values()),
        )
        stop_combo.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(2, 0))
        stop_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_draft_changed())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def is_alive(self) -> bool:
        """True while this panel's Tk widgets still exist (see ArduinoBindingsPanel)."""
        try:
            return bool(self.winfo_exists())
        # except Exception justified: Tk raises assorted errors once the
        # interpreter behind the widget is gone; "not alive" is the answer.
        except Exception:
            return False

    def refresh(self) -> None:
        """Reload the stored window into the editor, discarding unsaved edits."""
        if not self.is_alive():
            log.debug("analysis_window_panel.refresh.skipped_destroyed")
            return
        spec, corrupt = load_window_spec(self._project_data())
        self._stored_spec = spec
        drafts = drafts_from_spec(spec)
        if drafts is None:
            self.drafts = {"start": SectionDraft(), "stop": SectionDraft()}
            self._show_notice(external_spec_notice())
        else:
            self.drafts = {"start": drafts[0], "stop": drafts[1]}
            self._show_notice(corrupt_spec_notice() if corrupt else "")
        policy_spec = spec if spec is not None else WindowSpec()
        self.on_start_not_met.set(on_start_not_met_labels()[policy_spec.on_start_not_met])
        self.on_stop.set(on_stop_labels()[policy_spec.on_stop])
        self._dirty = False
        self._render_sections()
        self._refresh_target_choices()
        self._update_preview()
        self._set_status("")

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------
    def selected_section(self) -> SectionName:
        token = _label_to_token(section_labels(), self.target_section.get(), "start")
        return cast(SectionName, token)

    def selected_kind(self) -> RowKind | None:
        token = _label_to_token(row_kind_labels(), self.row_kind.get(), None)
        return cast("RowKind | None", token)

    def read_line(self) -> ConditionRow:
        """The line described by the editor widgets.

        Raises:
            SpecBuildError: nothing chosen, or the number does not parse.
        """
        kind = self.selected_kind()
        if kind is None:
            raise SpecBuildError(_("Choose a condition."))
        number = parse_number(self.row_number.get(), integer=kind in INTEGER_KINDS)
        text = self.row_target.get().strip()
        role = cast("Role | None", _label_to_token(role_labels(), text, None))
        unit = cast(HoldUnit, _label_to_token(hold_unit_labels(), self.row_unit.get(), "frames"))
        if kind in LEVEL_KINDS:
            return ConditionRow(kind=kind, target="" if role else text, role=role)
        if kind in ("roi_enter", "roi_exit"):
            return ConditionRow(kind=kind, target=text)
        if kind == "hold":
            return ConditionRow(kind=kind, value=number, unit=unit)
        return ConditionRow(kind=kind, value=number)

    def add_line(self) -> None:
        """Append the editor's line to the chosen section (rejected lines are not added)."""
        section = self.selected_section()
        try:
            row = self.read_line()
            check_row(row, section)
        except SpecBuildError as exc:
            self._set_status(str(exc), error=True)
            return
        draft = self.drafts[section]
        self.drafts[section] = replace(draft, rows=(*draft.rows, row))
        self.row_number.set("")
        self._on_draft_changed()

    def remove_selected(self, section: SectionName) -> None:
        tree = self._trees.get(section)
        if tree is None:
            return
        doomed = {int(iid) for iid in tree.selection()}
        if not doomed:
            return
        draft = self.drafts[section]
        rows = tuple(row for index, row in enumerate(draft.rows) if index not in doomed)
        self.drafts[section] = replace(draft, rows=rows)
        self._on_draft_changed()

    def move_selected(self, section: SectionName, offset: int) -> None:
        tree = self._trees.get(section)
        if tree is None or not tree.selection():
            return
        index = int(tree.selection()[0])
        target = index + offset
        rows = list(self.drafts[section].rows)
        if not 0 <= target < len(rows):
            return
        rows[index], rows[target] = rows[target], rows[index]
        self.drafts[section] = replace(self.drafts[section], rows=tuple(rows))
        self._on_draft_changed()
        tree.selection_set(str(target))

    def clear_all(self) -> None:
        self.drafts = {"start": SectionDraft(), "stop": SectionDraft()}
        self._on_draft_changed()

    def apply_barnes_preset(self) -> None:
        """Fill the editor with the Barnes-maze preset (not saved until "Save")."""
        spec = barnes_maze_preset()
        drafts = drafts_from_spec(spec)
        if drafts is None:  # pragma: no cover - guarded by the round-trip test
            log.error("analysis_window_panel.preset.not_representable")
            return
        self.drafts = {"start": drafts[0], "stop": drafts[1]}
        self.on_start_not_met.set(on_start_not_met_labels()[spec.on_start_not_met])
        self.on_stop.set(on_stop_labels()[spec.on_stop])
        self.open_editor()
        self._on_draft_changed()
        missing = missing_class_names(spec, self._class_names())
        if missing:
            self._set_status(
                _(
                    "Preset loaded. The current model has no class named {names}; "
                    "review the lines, then Save."
                ).format(names=", ".join(f"'{name}'" for name in missing)),
                error=True,
            )
        else:
            self._set_status(_("Preset loaded. Review the lines, then Save."))

    def current_spec(self) -> WindowSpec | None:
        """Build the spec from the editor (raises :class:`SpecBuildError`)."""
        return build_window_spec(
            self.drafts["start"],
            self.drafts["stop"],
            on_start_not_met=cast(
                OnStartNotMet,
                _label_to_token(
                    on_start_not_met_labels(), self.on_start_not_met.get(), "whole_recording"
                ),
            ),
            on_stop=cast(OnStop, _label_to_token(on_stop_labels(), self.on_stop.get(), "mark")),
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self) -> bool:
        """Validate, store, persist and announce the window. ``True`` on success."""
        try:
            spec = self.current_spec()
        except SpecBuildError as exc:
            self._set_status(str(exc), error=True)
            return False

        project_data = self._project_data()
        previous = project_data.get(PROJECT_KEY)
        store_window_spec(project_data, spec)
        try:
            if getattr(self.project_manager, "project_path", None):
                self.project_manager.save_project()
                self._set_status(_("Analysis window saved."))
            else:
                self._set_status(_("Analysis window applied (project has no path on disk)."))
        # except Exception justified: disk/serialization errors must not crash the
        # UI; the in-memory value is rolled back so memory and disk agree.
        except Exception as exc:
            project_data[PROJECT_KEY] = previous
            log.error("analysis_window_panel.save_failed", error=str(exc), exc_info=True)
            self._set_status(_("Error while saving: {error}").format(error=exc), error=True)
            return False

        self._stored_spec = spec
        self._dirty = False
        self._show_notice("")
        self._update_preview()
        log.info(
            "analysis_window_panel.save.success",
            has_window=spec is not None,
            spec_hash=None if spec is None else spec_hash(spec),
        )
        self._publish_changed(spec)
        return True

    def _publish_changed(self, spec: WindowSpec | None) -> None:
        if self.event_bus is None:
            return
        self.event_bus.publish(
            Event(
                type=UIEvents.ANALYSIS_WINDOW_SPEC_CHANGED,
                data=payloads.AnalysisWindowSpecChangedPayload(
                    spec=None if spec is None else spec.model_dump(mode="json", by_alias=True),
                    spec_hash=None if spec is None else spec_hash(spec),
                ),
                source="AnalysisWindowPanel.save",
            )
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _on_draft_changed(self) -> None:
        self._dirty = True
        self._render_sections()
        self._update_preview()

    def _on_combinator_changed(self, section: SectionName) -> None:
        combinator = cast(
            Combinator,
            _label_to_token(combinator_labels(), self.combinator_vars[section].get(), "all_of"),
        )
        self.drafts[section] = replace(self.drafts[section], combinator=combinator)
        self._on_draft_changed()

    def _render_sections(self) -> None:
        kinds = row_kind_labels()
        for section, draft in self.drafts.items():
            self.combinator_vars[section].set(combinator_labels()[draft.combinator])
            tree = self._trees.get(section)
            if tree is None:
                continue
            tree.delete(*tree.get_children())
            for index, row in enumerate(draft.rows):
                tree.insert("", "end", iid=str(index), values=(kinds[row.kind], describe_row(row)))

    def _update_preview(self) -> None:
        text, error = self.preview_text()
        for label in (self._preview, self._editor_preview):
            if label is not None:
                label.config(text=text, foreground="red" if error else "")

    def preview_text(self) -> tuple[str, bool]:
        """``(text, is_error)`` of the preview for the editor's current state."""
        if not self._dirty and drafts_from_spec(self._stored_spec) is None:
            return describe_window_spec(self._stored_spec), False
        try:
            spec = self.current_spec()
        except SpecBuildError as exc:
            return str(exc), True
        text = describe_window_spec(spec)
        if self._dirty:
            text = _("{rule}\n(not saved yet)").format(rule=text)
        return text, False

    def _refresh_kind_choices(self) -> None:
        if self._kind_combo is None:
            return
        section = self.selected_section()
        labels = row_kind_labels()
        allowed = [
            labels[kind] for kind in ROW_KINDS if section == "stop" or kind not in STOP_ONLY_KINDS
        ]
        self._kind_combo["values"] = allowed
        if self.row_kind.get() not in allowed:
            self.row_kind.set(allowed[0])
        self._on_kind_changed()

    def _on_kind_changed(self) -> None:
        kind = self.selected_kind()
        if self._target_combo is not None:
            if kind in LEVEL_KINDS:
                names = self._class_names()
                self._target_combo["values"] = [*role_labels().values(), *names]
                # Free text until the class-role front wires the weight's names in.
                self._target_combo.config(state="readonly" if names else "normal")
            elif kind in ("roi_enter", "roi_exit"):
                self._target_combo["values"] = self._roi_names()
                self._target_combo.config(state="readonly")
            else:
                self._target_combo["values"] = []
                self._target_combo.config(state="disabled")
            if kind not in TARGET_KINDS:
                self.row_target.set("")
        uses_number = kind in NUMBER_REQUIRED_KINDS or kind in NUMBER_OPTIONAL_KINDS
        if self._number_entry is not None:
            self._number_entry.config(state="normal" if uses_number else "disabled")
            if not uses_number:
                self.row_number.set("")
        if self._unit_combo is not None:
            self._unit_combo.config(state="readonly" if kind == "hold" else "disabled")
        if self._number_hint is not None:
            self._number_hint.config(text=self._number_hint_text(kind))

    @staticmethod
    def _number_hint_text(kind: RowKind | None) -> str:
        hints: dict[RowKind, str] = {
            "hold": _("How long ALL the class lines above must hold together."),
            "video_time": _("Seconds from the beginning of the video."),
            "frame": _("Frame number (the first frame is 0)."),
            "delay_after_start": _("Seconds after the window started."),
            "arduino": _("Code sent by the Arduino; leave blank to accept any code."),
            "manual": _("Fires when the operator gives the manual signal."),
            "end_of_video": _("Fires when the recording ends."),
        }
        return hints.get(kind, "") if kind is not None else ""

    def _refresh_target_choices(self) -> None:
        self._on_kind_changed()

    def refresh_class_names(self) -> None:
        """Re-read the class names: the project's weight finished loading or changed.

        The names come from the injected provider, which answers ``[]`` until the
        weight's model was read on a background thread; this is the hook that
        turns the class lines from free text into the weight's own list then.
        """
        if not self.is_alive():
            return
        self._refresh_target_choices()

    def _show_notice(self, text: str) -> None:
        if self._notice is None or self._preview is None:
            return
        if text:
            self._notice.config(text=text)
            if not self._notice.winfo_manager():
                self._notice.pack(anchor="w", fill="x", after=self._preview)
        else:
            self._notice.config(text="")
            self._notice.pack_forget()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _project_data(self) -> dict[str, Any]:
        # ``or {}`` would be wrong here: an EMPTY dict is falsy, and the save
        # would then land in a throwaway dict instead of the project's own.
        data = getattr(self.project_manager, "project_data", None)
        return data if isinstance(data, dict) else {}

    def _class_names(self) -> list[str]:
        if self._class_names_provider is None:
            return []
        try:
            names = self._class_names_provider()
        # except Exception justified: the provider reads the active weight, which
        # may be unavailable; free entry is the documented fallback.
        except Exception:
            log.debug("analysis_window_panel.class_names.unavailable", exc_info=True)
            return []
        return [str(name) for name in names if str(name).strip()]

    def _roi_names(self) -> list[str]:
        try:
            zone_data = self.project_manager.get_zone_data()
        # except Exception justified: zone data may be unavailable early on.
        except Exception:
            return []
        names = list(getattr(zone_data, "roi_names", []) or [])
        return [str(n) for n in names if str(n).strip()]

    def _set_status(self, message: str, *, error: bool = False) -> None:
        for label in (self._status, self._editor_status):
            if label is not None:
                label.config(text=message, foreground="red" if error else "green")

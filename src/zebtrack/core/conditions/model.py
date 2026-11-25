"""Condition AST that defines an analysis window (ADR-011).

A :class:`WindowSpec` says when the analysis of a recording STARTS and when it
STOPS. It is stored inside the project and copied into every
``7_AnalysisWindow_<base>.json`` artifact, so every ``kind`` token and field name
here is a persistence contract: renaming one stops the app from reading the
projects it wrote itself.

Two node families:

- **Level** nodes are true or false on each processed frame (``ClassPresence``,
  ``RoiInside``, ``Not``, ``AllOfLevel``, ``AnyOfLevel``, and the subject-geometry
  levels ``SubjectOverRoi``, ``SubjectVisibleFraction``, ``LastSeenIn``).
- **Trigger** nodes fire once, at one instant (``Persist``, ``RoiEdge``,
  ``TimeReached``, ``FrameReached``, ``Delay``, ``External``, ``EndOfStream``,
  ``BurrowEntry``, ``FirstOf``, ``AllOf``, ``Sequence``).

The module is pure: pydantic, stdlib and nothing else. Evaluation lives in
:mod:`zebtrack.core.conditions.evaluator`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

__all__ = [
    "AllOf",
    "AllOfLevel",
    "AnyOfLevel",
    "BurrowEntry",
    "ClassPresence",
    "ClassTarget",
    "ConditionNode",
    "Delay",
    "EndOfStream",
    "External",
    "FirstOf",
    "FrameReached",
    "Hold",
    "LastSeenIn",
    "LevelNode",
    "Not",
    "Persist",
    "RoiEdge",
    "RoiInside",
    "Sequence",
    "SubjectOverRoi",
    "SubjectVisibleFraction",
    "TimeReached",
    "TriggerNode",
    "WindowSpec",
    "iter_nodes",
    "spec_hash",
]

# Same rule as ``core.detection.class_aliases.normalize_class_name``. Duplicated on
# purpose: importing ``core.detection`` pulls torch/ultralytics (~4 s), and this
# package must stay importable without the detector. A test pins the equivalence.
_SEPARATORS = re.compile(r"[\s\-]+")

_MODEL_CONFIG = ConfigDict(
    frozen=True,
    extra="forbid",
    allow_inf_nan=False,
    validate_by_alias=True,
    validate_by_name=True,
    serialize_by_alias=True,
)


def _normalize_class_name(name: str) -> str:
    return _SEPARATORS.sub("_", name.strip().lower())


class _Node(BaseModel):
    model_config = _MODEL_CONFIG


# ---------------------------------------------------------------------------
# Level nodes
# ---------------------------------------------------------------------------


class ClassTarget(_Node):
    """Which detections a :class:`ClassPresence` counts.

    Serialized as ``{"class": "<normalized name>"}`` or ``{"role": "subject"}``;
    exactly one of the two is set. A role is resolved at evaluation time through
    the class-role map (ADR-009), so the same spec works for any weight that
    declares the role.
    """

    class_name: str | None = Field(default=None, alias="class")
    role: Literal["subject", "context"] | None = None

    @classmethod
    def of_class(cls, name: str) -> ClassTarget:
        """Target one class by name (normalized)."""
        return cls.model_validate({"class": name})

    @classmethod
    def of_role(cls, role: Literal["subject", "context"]) -> ClassTarget:
        """Target every class mapped to ``role``."""
        return cls.model_validate({"role": role})

    @field_validator("class_name")
    @classmethod
    def _normalize(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_class_name(value)
        if not normalized:
            raise PydanticCustomError("class_name_blank", "A class name cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def _exactly_one(self) -> ClassTarget:
        if (self.class_name is None) == (self.role is None):
            raise PydanticCustomError(
                "class_target_needs_exactly_one",
                'A class target needs exactly one of "class" or "role".',
            )
        return self


class ClassPresence(_Node):
    """True when at least ``min_count`` matching detections exist (``present=True``).

    With ``present=False`` the node is true when FEWER than ``min_count``
    detections match, so the default ``min_count=1`` reads as "class absent".
    ``min_confidence`` filters detections before counting.
    """

    kind: Literal["class_presence"] = "class_presence"
    target: ClassTarget
    present: bool = True
    min_count: int = Field(default=1, ge=1)
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class RoiInside(_Node):
    """True when the subject is (``inside``) or is not (``outside``) in ``roi``."""

    kind: Literal["roi_inside"] = "roi_inside"
    roi: str = Field(min_length=1)
    state: Literal["inside", "outside"]


class Not(_Node):
    """Negation of a level."""

    kind: Literal["not"] = "not"
    child: LevelNode


class AllOfLevel(_Node):
    """True when every child level is true on the same frame."""

    kind: Literal["all_of_level"] = "all_of_level"
    children: tuple[LevelNode, ...] = Field(min_length=1)


class AnyOfLevel(_Node):
    """True when at least one child level is true on the frame."""

    kind: Literal["any_of_level"] = "any_of_level"
    children: tuple[LevelNode, ...] = Field(min_length=1)


class SubjectOverRoi(_Node):
    """True when at least ``min_cover`` of the subject's VISIBLE box lies over ``roi``.

    The fraction is ``area(box ∩ roi) / area(box)``
    (:mod:`zebtrack.core.conditions.subject_geometry`), so a rat whose body is
    mostly over the escape hole reads high even when only part of it is visible,
    and one that only reaches it with its nose reads low.
    """

    kind: Literal["subject_over_roi"] = "subject_over_roi"
    roi: str = Field(min_length=1)
    min_cover: float = Field(default=0.5, gt=0.0, le=1.0)


class SubjectVisibleFraction(_Node):
    """True when the subject's box is at most ``max_fraction`` of its usual size.

    "Usual" is the running median of the box area over the frames with a
    subject detection since START; the frame being tested joins that reference
    only AFTER the test. False before START, on a frame without the subject, and
    until ``min_reference_frames`` detected frames make up the reference. Only
    meaningful inside STOP (the reference starts with START).
    """

    kind: Literal["subject_visible_fraction"] = "subject_visible_fraction"
    max_fraction: float = Field(gt=0.0, lt=1.0)
    min_reference_frames: int = Field(default=10, ge=1)


class LastSeenIn(_Node):
    """True on a frame WITHOUT the subject whose last detection was over ``roi``.

    "Over" uses the same fraction as :class:`SubjectOverRoi` (``min_cover``).
    Wrapped in a ``Persist`` it reads "vanished into ``roi`` for N seconds".
    """

    kind: Literal["last_seen_in"] = "last_seen_in"
    roi: str = Field(min_length=1)
    min_cover: float = Field(default=0.5, gt=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Trigger nodes
# ---------------------------------------------------------------------------


class Hold(_Node):
    """How long a level must persist: ``seconds`` (recommended) or ``frames``."""

    seconds: float | None = Field(default=None, gt=0.0)
    frames: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _exactly_one(self) -> Hold:
        if (self.seconds is None) == (self.frames is None):
            raise PydanticCustomError(
                "hold_needs_exactly_one",
                'A hold needs exactly one of "seconds" or "frames".',
            )
        return self


class Persist(_Node):
    """Fires when ``level`` stays true for ``hold``; back-dated to the run's first frame.

    A gap between observations larger than ``max_gap_s`` resets the run. Without
    it, the evaluator uses 3x the median interval seen so far.
    """

    kind: Literal["persist"] = "persist"
    level: LevelNode
    hold: Hold
    max_gap_s: float | None = Field(default=None, gt=0.0)


class RoiEdge(_Node):
    """Fires on a real transition of the subject into (``enter``) or out of ``roi``."""

    kind: Literal["roi_edge"] = "roi_edge"
    roi: str = Field(min_length=1)
    edge: Literal["enter", "exit"]


class TimeReached(_Node):
    """Fires at the first frame whose clock reads ``at_s`` or later.

    ``video`` is the event clock (PTS pre-recorded, capture clock live);
    ``wall`` is wall-clock time elapsed since the first observation.
    """

    kind: Literal["time_reached"] = "time_reached"
    clock: Literal["video", "wall"]
    at_s: float = Field(ge=0.0)


class FrameReached(_Node):
    """Fires at the first processed frame whose index is ``frame`` or later."""

    kind: Literal["frame_reached"] = "frame_reached"
    frame: int = Field(ge=0)


class Delay(_Node):
    """Fires ``seconds`` after START (``after="start"``, STOP only) or after a trigger."""

    kind: Literal["delay"] = "delay"
    after: Literal["start"] | TriggerNode
    seconds: float = Field(ge=0.0)


class External(_Node):
    """Fires on an external event (Arduino or manual); ``code=None`` matches any code."""

    kind: Literal["external"] = "external"
    source: Literal["arduino", "manual"]
    code: int | None = None


class EndOfStream(_Node):
    """Fires when the stream ends. Only meaningful inside STOP."""

    kind: Literal["end_of_stream"] = "end_of_stream"


class BurrowEntry(_Node):
    """Fires when the subject ENTERS ``roi`` (four paws in), not when it touches it.

    The first of two runs, each back-dated to its first frame:

    - **(a) over the hole and small** — ``SubjectOverRoi(roi, min_cover)`` and
      ``SubjectVisibleFraction(max_visible_fraction, min_reference_frames)``
      together, held for ``hold``;
    - **(b) vanished into the hole** — ``LastSeenIn(roi, min_cover)`` held for
      ``absent_s`` seconds.

    ``max_gap_s`` resets either run on a gap between observations, as in
    :class:`Persist`. The window's STOP reason is ``burrow_entry``. STOP only:
    the size reference starts with START.
    """

    kind: Literal["burrow_entry"] = "burrow_entry"
    roi: str = Field(min_length=1)
    min_cover: float = Field(default=0.5, gt=0.0, le=1.0)
    max_visible_fraction: float = Field(default=0.35, gt=0.0, lt=1.0)
    hold: Hold = Field(default_factory=lambda: Hold(seconds=0.5))
    absent_s: float = Field(default=3.0, gt=0.0)
    min_reference_frames: int = Field(default=10, ge=1)
    max_gap_s: float | None = Field(default=None, gt=0.0)


class FirstOf(_Node):
    """OR: fires with the first child that fires."""

    kind: Literal["first_of"] = "first_of"
    children: tuple[TriggerNode, ...] = Field(min_length=1)


class AllOf(_Node):
    """AND: fires once every child fired; its instant is the latest child instant."""

    kind: Literal["all_of"] = "all_of"
    children: tuple[TriggerNode, ...] = Field(min_length=1)


class Sequence(_Node):
    """Fires when the children fire in order; restarts if ``within_s`` runs out."""

    kind: Literal["sequence"] = "sequence"
    children: tuple[TriggerNode, ...] = Field(min_length=1)
    within_s: float | None = Field(default=None, gt=0.0)


LevelNode = Annotated[
    ClassPresence
    | RoiInside
    | Not
    | AllOfLevel
    | AnyOfLevel
    | SubjectOverRoi
    | SubjectVisibleFraction
    | LastSeenIn,
    Field(discriminator="kind"),
]
TriggerNode = Annotated[
    Persist
    | RoiEdge
    | TimeReached
    | FrameReached
    | Delay
    | External
    | EndOfStream
    | BurrowEntry
    | FirstOf
    | AllOf
    | Sequence,
    Field(discriminator="kind"),
]

#: Any node of either family (what :func:`iter_nodes` yields).
ConditionNode = (
    ClassPresence
    | RoiInside
    | Not
    | AllOfLevel
    | AnyOfLevel
    | SubjectOverRoi
    | SubjectVisibleFraction
    | LastSeenIn
    | Persist
    | RoiEdge
    | TimeReached
    | FrameReached
    | Delay
    | External
    | EndOfStream
    | BurrowEntry
    | FirstOf
    | AllOf
    | Sequence
)


def iter_nodes(node: ConditionNode) -> Iterator[ConditionNode]:
    """Yield ``node`` and every descendant, depth-first, in declaration order."""
    yield node
    if isinstance(node, Not):
        yield from iter_nodes(node.child)
    elif isinstance(node, AllOfLevel | AnyOfLevel | FirstOf | AllOf | Sequence):
        for child in node.children:
            yield from iter_nodes(child)
    elif isinstance(node, Persist):
        yield from iter_nodes(node.level)
    elif isinstance(node, Delay) and not isinstance(node.after, str):
        yield from iter_nodes(node.after)


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------


class WindowSpec(_Node):
    """START/STOP conditions of the analysis window.

    ``start=None`` starts at the first processed frame (pre-v8 behaviour);
    ``stop=None`` stops at the end of the stream. ``on_start_not_met`` and
    ``on_stop`` are read by the analysis and live layers, not by the evaluator.
    """

    version: Literal[1] = 1
    start: TriggerNode | None = None
    stop: TriggerNode | None = None
    on_start_not_met: Literal["whole_recording", "empty"] = "whole_recording"
    on_stop: Literal["mark", "end_session"] = "mark"

    @model_validator(mode="after")
    def _start_is_evaluable(self) -> WindowSpec:
        if self.start is None:
            return self
        for node in iter_nodes(self.start):
            if isinstance(node, Delay) and node.after == "start":
                raise PydanticCustomError(
                    "start_refers_to_itself",
                    'Delay(after="start") cannot be part of the START condition: '
                    "START cannot wait for itself.",
                )
            if isinstance(node, EndOfStream):
                raise PydanticCustomError(
                    "start_uses_end_of_stream",
                    "EndOfStream cannot be part of the START condition: "
                    "a window cannot start once the recording is over.",
                )
            if isinstance(node, BurrowEntry | SubjectVisibleFraction):
                raise PydanticCustomError(
                    "start_uses_subject_size",
                    "BurrowEntry and SubjectVisibleFraction cannot be part of the START "
                    "condition: the subject's usual size is measured from START on.",
                )
        return self


for _model in (Not, AllOfLevel, AnyOfLevel, Persist, Delay, FirstOf, AllOf, Sequence, WindowSpec):
    _model.model_rebuild()


def spec_hash(spec: WindowSpec) -> str:
    """Return ``"sha256:<hex>"`` of the canonical JSON of ``spec``.

    Canonical = every field (defaults included), keys sorted, no whitespace, so
    the hash does not depend on how the JSON was spelled.
    """
    canonical = json.dumps(
        spec.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

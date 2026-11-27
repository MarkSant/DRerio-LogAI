"""Evaluate a :class:`WindowSpec` over a stream of per-frame observations (ADR-011).

One implementation serves both pipelines: the live runtime calls
:meth:`ConditionEvaluator.step` once per processed frame, and the offline
analysis folds the whole recording through :func:`evaluate_window`, which is
literally ``step`` + ``finish``. Online and batch therefore cannot disagree on
the same input; any divergence between the ``online`` and ``offline`` sections
of the artifact comes from different INPUTS, never from the engine.

Semantics (the contract the tests pin):

- STOP is evaluated only after START, and only on observations strictly LATER
  than the instant START was confirmed. One frame, one external press or one
  duplicated observation can therefore never satisfy both.
- ``Persist`` measures its hold on the event clock (``t_s``); its event is
  back-dated to the first frame of the run. A gap between observations larger
  than ``max_gap_s`` (default: 3 x the median interval seen so far, zero
  intervals excluded) resets the run.
- ``Sequence`` arms each stage on observations strictly later than the
  previous stage's confirmation, and restarts when ``within_s`` elapses
  between the first stage's instant and now.
- ``BurrowEntry`` is two ``Persist`` runs (over the hole and small; vanished
  into the hole) and fires with the earlier one, back-dated like ``Persist``,
  with reason ``burrow_entry``. Its size reference — the running median of the
  subject box area — is stream-wide state: it starts with the observation that
  confirms START (the frames START back-dates over are not in it) and each
  frame joins it only AFTER the levels were evaluated on that frame.
- No re-arming: the first window wins.
- START never met -> ``status="start_not_met"``. STOP never met -> ``finish``
  emits an ``end_of_stream`` STOP at the last observation, ``censored=True``
  unless the STOP condition is exactly ``EndOfStream`` (or absent).
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

import structlog

from zebtrack.core.conditions.model import (
    AllOf,
    AllOfLevel,
    AnyOfLevel,
    BurrowEntry,
    ClassPresence,
    Delay,
    EndOfStream,
    External,
    FirstOf,
    FrameReached,
    Hold,
    LastSeenIn,
    LevelNode,
    Not,
    Persist,
    RoiEdge,
    RoiInside,
    Sequence,
    SubjectOverRoi,
    SubjectVisibleFraction,
    TimeReached,
    TriggerNode,
    WindowSpec,
    _normalize_class_name,
    iter_nodes,
)

__all__ = [
    "ConditionEvaluator",
    "ExternalEvent",
    "FrameObservation",
    "WindowEvent",
    "WindowReason",
    "WindowResult",
    "WindowStatus",
    "evaluate_window",
]

logger = structlog.get_logger()

#: Tolerance for clock comparisons. PTS arrive as ``POS_MSEC / 1000`` and
#: ``6.7 - 4.7`` is ``1.9999999999999996``; a hold of exactly 2 s must still fire.
_TIME_EPS = 1e-9

#: Default gap limit, as a multiple of the median inter-observation interval.
_DEFAULT_GAP_FACTOR = 3.0

#: Tolerance for cover fractions: an intersection area over a box area that is
#: "exactly half" geometrically can come out as ``0.49999999999999994``.
_COVER_EPS = 1e-9

WindowReason = Literal[
    "first_frame",
    "persist",
    "roi_edge",
    "time",
    "frame",
    "delay",
    "external",
    "end_of_stream",
    "burrow_entry",
]
WindowStatus = Literal["pending", "complete", "start_not_met", "censored"]


@dataclass(frozen=True, slots=True)
class ExternalEvent:
    """An Arduino or manual event, stamped on the event clock when it was read."""

    source: Literal["arduino", "manual"]
    code: int | None
    t_s: float


@dataclass(frozen=True, slots=True)
class FrameObservation:
    """What the engine needs to know about one processed frame.

    Attributes:
        frame: Frame index (pre-recorded: 0-based video frame; live: pipeline frame).
        t_s: Event clock in seconds — PTS pre-recorded, capture clock live. Never
            the live processing ``timestamp``.
        classes: Normalized class name -> confidences of that class's detections
            in this frame.
        subject_rois: ROIs the subject occupies in this frame.
        external: External events delivered with this frame.
        t_wall: Wall-clock seconds, for ``TimeReached(clock="wall")``.
        aquarium_id: Aquarium this stream belongs to (one evaluator per aquarium).
        subject_area_px: Area (px²) of the subject box chosen for this frame;
            ``None`` when the subject was not detected.
        subject_cover: ROI name -> ``area(box ∩ roi) / area(box)`` in ``(0, 1]``
            for every ROI the box overlaps; a missing name reads as ``0.0``. Both
            come from :mod:`zebtrack.core.conditions.subject_geometry`.
    """

    frame: int
    t_s: float
    classes: Mapping[str, tuple[float, ...]] = field(default_factory=dict)
    subject_rois: frozenset[str] = frozenset()
    external: tuple[ExternalEvent, ...] = ()
    t_wall: float | None = None
    aquarium_id: int | None = None
    subject_area_px: float | None = None
    subject_cover: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WindowEvent:
    """START or STOP of the window.

    ``frame``/``t_s`` is the instant the event refers to (back-dated for
    ``Persist``); ``confirmed_frame``/``confirmed_t_s`` is the observation on
    which the engine became sure of it. The live pipeline acts at the second,
    the analysis cuts at the first.
    """

    kind: Literal["start", "stop"]
    frame: int
    t_s: float
    reason: WindowReason
    confirmed_frame: int | None = None
    confirmed_t_s: float | None = None


@dataclass(frozen=True, slots=True)
class WindowResult:
    """Outcome of a window evaluation.

    ``status="pending"`` only appears before :meth:`ConditionEvaluator.finish`
    while the STOP is still open (or the START still unmet).
    """

    start: WindowEvent | None
    stop: WindowEvent | None
    status: WindowStatus
    censored: bool


# ---------------------------------------------------------------------------
# Runtime context and helpers
# ---------------------------------------------------------------------------


class _RunningMedian:
    """Median of a growing multiset in O(log n) per insert (two heaps)."""

    def __init__(self) -> None:
        self._low: list[float] = []  # max-heap through negation
        self._high: list[float] = []

    def add(self, value: float) -> None:
        if not self._low or value <= -self._low[0]:
            heapq.heappush(self._low, -value)
        else:
            heapq.heappush(self._high, value)
        if len(self._low) > len(self._high) + 1:
            heapq.heappush(self._high, -heapq.heappop(self._low))
        elif len(self._high) > len(self._low):
            heapq.heappush(self._low, -heapq.heappop(self._high))

    def median(self) -> float | None:
        if not self._low:
            return None
        if len(self._low) > len(self._high):
            return -self._low[0]
        return (-self._low[0] + self._high[0]) / 2.0

    def __len__(self) -> int:
        return len(self._low) + len(self._high)


@dataclass(slots=True)
class _Context:
    """Stream-wide state every node may read during one ``step``.

    ``subject_size`` (the running median of the subject box area since START)
    and ``last_detected`` (the latest observation WITH the subject) are updated
    by :meth:`ConditionEvaluator.step` after the nodes ran, so on any frame they
    describe the frames BEFORE it.
    """

    roles: Mapping[str, frozenset[str]]
    prev: FrameObservation | None = None
    dt: float | None = None
    default_max_gap: float | None = None
    first_t_wall: float | None = None
    start: WindowEvent | None = None
    subject_size: _RunningMedian | None = None
    last_detected: FrameObservation | None = None


@dataclass(frozen=True, slots=True)
class _Fire:
    frame: int
    t_s: float
    reason: WindowReason


def _instant_key(fire: _Fire) -> tuple[float, int]:
    return (fire.t_s, fire.frame)


_Level = Callable[[FrameObservation, _Context], bool]


def _compile_level(node: LevelNode, roles: Mapping[str, frozenset[str]]) -> _Level:
    if isinstance(node, ClassPresence):
        return _class_presence(node, roles)
    if isinstance(node, RoiInside):
        roi = node.roi
        if node.state == "inside":
            return lambda obs, ctx: roi in obs.subject_rois
        return lambda obs, ctx: roi not in obs.subject_rois
    if isinstance(node, SubjectOverRoi):
        return _subject_over_roi(node.roi, node.min_cover)
    if isinstance(node, SubjectVisibleFraction):
        return _subject_visible_fraction(node.max_fraction, node.min_reference_frames)
    if isinstance(node, LastSeenIn):
        return _last_seen_in(node.roi, node.min_cover)
    if isinstance(node, Not):
        child = _compile_level(node.child, roles)
        return lambda obs, ctx: not child(obs, ctx)
    children = tuple(_compile_level(c, roles) for c in node.children)
    if isinstance(node, AllOfLevel):
        return lambda obs, ctx: all(c(obs, ctx) for c in children)
    if isinstance(node, AnyOfLevel):
        return lambda obs, ctx: any(c(obs, ctx) for c in children)
    raise TypeError(f"Unknown level node: {type(node).__name__}")


def _covers(cover: Mapping[str, float], roi: str, min_cover: float) -> bool:
    return cover.get(roi, 0.0) >= min_cover - _COVER_EPS


def _subject_over_roi(roi: str, min_cover: float) -> _Level:
    def level(obs: FrameObservation, ctx: _Context) -> bool:
        return obs.subject_area_px is not None and _covers(obs.subject_cover, roi, min_cover)

    return level


def _subject_visible_fraction(max_fraction: float, min_reference_frames: int) -> _Level:
    def level(obs: FrameObservation, ctx: _Context) -> bool:
        reference = ctx.subject_size
        if ctx.start is None or obs.subject_area_px is None or reference is None:
            return False
        if len(reference) < min_reference_frames:
            return False
        median = reference.median()
        return median is not None and obs.subject_area_px <= max_fraction * median

    return level


def _last_seen_in(roi: str, min_cover: float) -> _Level:
    def level(obs: FrameObservation, ctx: _Context) -> bool:
        last = ctx.last_detected
        if obs.subject_area_px is not None or last is None:
            return False
        return _covers(last.subject_cover, roi, min_cover)

    return level


def _class_presence(node: ClassPresence, roles: Mapping[str, frozenset[str]]) -> _Level:
    if node.target.class_name is not None:
        names: frozenset[str] = frozenset({node.target.class_name})
    else:
        names = roles.get(str(node.target.role), frozenset())
    min_confidence = node.min_confidence
    min_count = node.min_count
    present = node.present

    def level(obs: FrameObservation, ctx: _Context) -> bool:
        count = 0
        for name in names:
            confidences = obs.classes.get(name, ())
            if min_confidence is None:
                count += len(confidences)
            else:
                count += sum(1 for c in confidences if c >= min_confidence)
        return (count >= min_count) == present

    return level


# ---------------------------------------------------------------------------
# Trigger runtime nodes
# ---------------------------------------------------------------------------


class _Trigger:
    """Fires at most once; ``fired`` keeps the instant afterwards."""

    def __init__(self) -> None:
        self.fired: _Fire | None = None

    def feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        if self.fired is not None:
            return None
        fire = self._feed(obs, ctx)
        if fire is not None:
            self.fired = fire
        return fire

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        raise NotImplementedError  # pragma: no cover


class _Persist(_Trigger):
    def __init__(self, node: Persist, roles: Mapping[str, frozenset[str]]) -> None:
        super().__init__()
        self._level = _compile_level(node.level, roles)
        self._seconds = node.hold.seconds
        self._frames = node.hold.frames
        self._max_gap_s = node.max_gap_s
        self._run: tuple[int, float] | None = None
        self._count = 0

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        gap_limit = self._max_gap_s if self._max_gap_s is not None else ctx.default_max_gap
        if self._run is not None and gap_limit is not None and ctx.dt is not None:
            if ctx.dt > gap_limit:
                self._run = None
        if not self._level(obs, ctx):
            self._run = None
            return None
        if self._run is None:
            self._run = (obs.frame, obs.t_s)
            self._count = 0
        self._count += 1
        frame0, t0 = self._run
        if self._seconds is not None:
            held = obs.t_s - t0 >= self._seconds - _TIME_EPS
        else:
            held = self._frames is not None and self._count >= self._frames
        if not held:
            return None
        return _Fire(frame0, t0, "persist")


class _RoiEdge(_Trigger):
    def __init__(self, node: RoiEdge) -> None:
        super().__init__()
        self._roi = node.roi
        self._enter = node.edge == "enter"

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        if ctx.prev is None:
            return None
        was_inside = self._roi in ctx.prev.subject_rois
        is_inside = self._roi in obs.subject_rois
        if was_inside == is_inside or is_inside != self._enter:
            return None
        return _Fire(obs.frame, obs.t_s, "roi_edge")


class _TimeReached(_Trigger):
    def __init__(self, node: TimeReached) -> None:
        super().__init__()
        self._wall = node.clock == "wall"
        self._at_s = node.at_s

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        if self._wall:
            if obs.t_wall is None or ctx.first_t_wall is None:
                return None
            clock = obs.t_wall - ctx.first_t_wall
        else:
            clock = obs.t_s
        if clock >= self._at_s - _TIME_EPS:
            return _Fire(obs.frame, obs.t_s, "time")
        return None


class _FrameReached(_Trigger):
    def __init__(self, node: FrameReached) -> None:
        super().__init__()
        self._frame = node.frame

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        if obs.frame >= self._frame:
            return _Fire(obs.frame, obs.t_s, "frame")
        return None


class _Delay(_Trigger):
    def __init__(self, node: Delay, roles: Mapping[str, frozenset[str]]) -> None:
        super().__init__()
        self._inner = None if isinstance(node.after, str) else _compile_trigger(node.after, roles)
        self._seconds = node.seconds

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        if self._inner is None:
            anchor = None if ctx.start is None else ctx.start.t_s
        else:
            self._inner.feed(obs, ctx)
            anchor = None if self._inner.fired is None else self._inner.fired.t_s
        if anchor is None:
            return None
        if obs.t_s >= anchor + self._seconds - _TIME_EPS:
            return _Fire(obs.frame, obs.t_s, "delay")
        return None


class _External(_Trigger):
    def __init__(self, node: External) -> None:
        super().__init__()
        self._source = node.source
        self._code = node.code

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        for event in obs.external:
            if event.source == self._source and (self._code is None or event.code == self._code):
                return _Fire(obs.frame, obs.t_s, "external")
        return None


class _BurrowEntry(_Trigger):
    """Entry into ``roi``: the earlier of "over it and small" and "vanished into it"."""

    def __init__(self, node: BurrowEntry, roles: Mapping[str, frozenset[str]]) -> None:
        super().__init__()
        over = SubjectOverRoi(roi=node.roi, min_cover=node.min_cover)
        small = SubjectVisibleFraction(
            max_fraction=node.max_visible_fraction,
            min_reference_frames=node.min_reference_frames,
        )
        self._runs = (
            _Persist(
                Persist(
                    level=AllOfLevel(children=(over, small)),
                    hold=node.hold,
                    max_gap_s=node.max_gap_s,
                ),
                roles,
            ),
            _Persist(
                Persist(
                    level=LastSeenIn(roi=node.roi, min_cover=node.min_cover),
                    hold=Hold(seconds=node.absent_s),
                    max_gap_s=node.max_gap_s,
                ),
                roles,
            ),
        )

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        # Both runs see every frame (no short-circuit): each keeps its own run.
        fires = [f for run in self._runs if (f := run.feed(obs, ctx)) is not None]
        if not fires:
            return None
        first = min(fires, key=_instant_key)
        return _Fire(first.frame, first.t_s, "burrow_entry")


class _EndOfStream(_Trigger):
    """Never fires inside the stream; :meth:`ConditionEvaluator.finish` handles it."""

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        return None


class _FirstOf(_Trigger):
    def __init__(self, node: FirstOf, roles: Mapping[str, frozenset[str]]) -> None:
        super().__init__()
        self._children = [_compile_trigger(c, roles) for c in node.children]

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        fires = [f for child in self._children if (f := child.feed(obs, ctx)) is not None]
        if not fires:
            return None
        # Several children confirmed on the same frame: the earliest instant wins,
        # declaration order breaks ties (min() keeps the first minimum).
        return min(fires, key=_instant_key)


class _AllOf(_Trigger):
    def __init__(self, node: AllOf, roles: Mapping[str, frozenset[str]]) -> None:
        super().__init__()
        self._children = [_compile_trigger(c, roles) for c in node.children]

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        for child in self._children:
            child.feed(obs, ctx)
        fired = [child.fired for child in self._children]
        if not all(f is not None for f in fired):
            return None
        return max((f for f in fired if f is not None), key=_instant_key)


class _Sequence(_Trigger):
    def __init__(self, node: Sequence, roles: Mapping[str, frozenset[str]]) -> None:
        super().__init__()
        self._node = node
        self._roles = roles
        self._within_s = node.within_s
        self._restart()

    def _restart(self) -> None:
        self._stages = [_compile_trigger(c, self._roles) for c in self._node.children]
        self._index = 0
        self._first: _Fire | None = None
        self._armed_after: float | None = None

    def _feed(self, obs: FrameObservation, ctx: _Context) -> _Fire | None:
        if self._within_s is not None and self._first is not None:
            if obs.t_s - self._first.t_s > self._within_s + _TIME_EPS:
                self._restart()
        if self._armed_after is not None and obs.t_s <= self._armed_after:
            return None
        fire = self._stages[self._index].feed(obs, ctx)
        if fire is None:
            return None
        if self._first is None:
            self._first = fire
        self._index += 1
        if self._index == len(self._stages):
            return fire
        self._armed_after = obs.t_s
        return None


def _compile_trigger(node: TriggerNode, roles: Mapping[str, frozenset[str]]) -> _Trigger:
    if isinstance(node, Persist):
        return _Persist(node, roles)
    if isinstance(node, RoiEdge):
        return _RoiEdge(node)
    if isinstance(node, TimeReached):
        return _TimeReached(node)
    if isinstance(node, FrameReached):
        return _FrameReached(node)
    if isinstance(node, Delay):
        return _Delay(node, roles)
    if isinstance(node, External):
        return _External(node)
    if isinstance(node, EndOfStream):
        return _EndOfStream()
    if isinstance(node, BurrowEntry):
        return _BurrowEntry(node, roles)
    if isinstance(node, FirstOf):
        return _FirstOf(node, roles)
    if isinstance(node, AllOf):
        return _AllOf(node, roles)
    if isinstance(node, Sequence):
        return _Sequence(node, roles)
    raise TypeError(f"Unknown trigger node: {type(node).__name__}")


# ---------------------------------------------------------------------------
# Public evaluator
# ---------------------------------------------------------------------------


class ConditionEvaluator:
    """Online evaluator of one window over one stream (one aquarium).

    Args:
        spec: The window to evaluate.
        role_names: Role -> class names (``{"subject": {"rat"}, "context": {...}}``)
            used by ``{"role": ...}`` targets. A role with no names is never
            present. Names are normalized here.
    """

    def __init__(self, spec: WindowSpec, *, role_names: Mapping[str, Iterable[str]]) -> None:
        roles = {
            role: frozenset(_normalize_class_name(str(name)) for name in names)
            for role, names in role_names.items()
        }
        self._spec = spec
        self._ctx = _Context(roles=roles)
        self._start_node = None if spec.start is None else _compile_trigger(spec.start, roles)
        self._stop_node = None if spec.stop is None else _compile_trigger(spec.stop, roles)
        self._stop_is_end_of_stream = spec.stop is None or isinstance(spec.stop, EndOfStream)
        self._start: WindowEvent | None = None
        self._stop: WindowEvent | None = None
        # STOP only sees observations strictly later than START's confirmation.
        self._stop_armed_after = float("inf")
        self._censored = False
        self._finished = False
        self._last: FrameObservation | None = None
        self._dts = _RunningMedian()
        self._aquarium_id: int | None = None
        self._skipped = 0
        # The size reference costs one float per detected frame: kept only when a
        # node reads it (both are refused inside START).
        self._tracks_subject_size = spec.stop is not None and any(
            isinstance(node, BurrowEntry | SubjectVisibleFraction) for node in iter_nodes(spec.stop)
        )

    @property
    def spec(self) -> WindowSpec:
        """The window being evaluated."""
        return self._spec

    @property
    def finished(self) -> bool:
        """Whether :meth:`finish` was called."""
        return self._finished

    @property
    def result(self) -> WindowResult:
        """Current outcome; reading it never changes the evaluation."""
        if self._start is None:
            status: WindowStatus = "start_not_met" if self._finished else "pending"
        elif self._stop is None:
            status = "pending"
        else:
            status = "censored" if self._censored else "complete"
        return WindowResult(
            start=self._start, stop=self._stop, status=status, censored=self._censored
        )

    def step(self, obs: FrameObservation) -> list[WindowEvent]:
        """Feed one observation; return the window events it confirmed (0 or 1).

        Raises:
            RuntimeError: After :meth:`finish`.
            ValueError: If observations of different aquariums are mixed.
        """
        if self._finished:
            raise RuntimeError("ConditionEvaluator.step() called after finish().")
        self._check_aquarium(obs)
        last = self._last
        if last is not None and obs.t_s < last.t_s:
            self._skipped += 1
            logger.warning(
                "conditions.evaluator.non_monotonic_skipped",
                frame=obs.frame,
                t_s=obs.t_s,
                previous_t_s=last.t_s,
                skipped=self._skipped,
            )
            return []

        ctx = self._ctx
        ctx.prev = last
        ctx.dt = None if last is None else obs.t_s - last.t_s
        median = self._dts.median()
        ctx.default_max_gap = None if median is None else _DEFAULT_GAP_FACTOR * median
        if ctx.first_t_wall is None and obs.t_wall is not None:
            ctx.first_t_wall = obs.t_wall

        events = self._advance(obs, ctx)

        if ctx.dt is not None and ctx.dt > 0.0:
            self._dts.add(ctx.dt)
        self._observe_subject(obs, ctx)
        self._last = obs
        return events

    def _observe_subject(self, obs: FrameObservation, ctx: _Context) -> None:
        """Fold this frame's subject into the stream state, AFTER the nodes ran."""
        area = obs.subject_area_px
        if area is None:
            return
        ctx.last_detected = obs
        if not self._tracks_subject_size or ctx.start is None:
            return
        if ctx.subject_size is None:
            ctx.subject_size = _RunningMedian()
        ctx.subject_size.add(float(area))

    def finish(self) -> list[WindowEvent]:
        """Close the stream: an open window gets its ``end_of_stream`` STOP.

        Idempotent; a second call returns ``[]``.
        """
        if self._finished:
            return []
        self._finished = True
        if self._start is None or self._stop is not None or self._last is None:
            if self._start is None:
                logger.info("conditions.window.start_not_met")
            return []
        last = self._last
        self._censored = not self._stop_is_end_of_stream
        self._stop = WindowEvent(
            kind="stop",
            frame=last.frame,
            t_s=last.t_s,
            reason="end_of_stream",
            confirmed_frame=last.frame,
            confirmed_t_s=last.t_s,
        )
        logger.info(
            "conditions.window.stop",
            frame=last.frame,
            t_s=last.t_s,
            reason="end_of_stream",
            censored=self._censored,
        )
        return [self._stop]

    def _advance(self, obs: FrameObservation, ctx: _Context) -> list[WindowEvent]:
        if self._stop is not None:
            return []
        if self._start is None:
            if self._start_node is None:
                fire: _Fire | None = _Fire(obs.frame, obs.t_s, "first_frame")
            else:
                fire = self._start_node.feed(obs, ctx)
            if fire is None:
                return []
            self._start = self._event("start", fire, obs)
            self._stop_armed_after = obs.t_s
            ctx.start = self._start
            return [self._start]
        if self._stop_node is None or obs.t_s <= self._stop_armed_after:
            return []
        fire = self._stop_node.feed(obs, ctx)
        if fire is None:
            return []
        self._stop = self._event("stop", fire, obs)
        return [self._stop]

    @staticmethod
    def _event(kind: Literal["start", "stop"], fire: _Fire, obs: FrameObservation) -> WindowEvent:
        logger.info(
            f"conditions.window.{kind}",
            frame=fire.frame,
            t_s=fire.t_s,
            reason=fire.reason,
            confirmed_frame=obs.frame,
        )
        return WindowEvent(
            kind=kind,
            frame=fire.frame,
            t_s=fire.t_s,
            reason=fire.reason,
            confirmed_frame=obs.frame,
            confirmed_t_s=obs.t_s,
        )

    def _check_aquarium(self, obs: FrameObservation) -> None:
        if obs.aquarium_id is None:
            return
        if self._aquarium_id is None:
            self._aquarium_id = obs.aquarium_id
        elif obs.aquarium_id != self._aquarium_id:
            raise ValueError(
                f"Observation of aquarium {obs.aquarium_id} fed to the evaluator of aquarium "
                f"{self._aquarium_id}; use one evaluator per aquarium."
            )


def evaluate_window(
    spec: WindowSpec,
    observations: Iterable[FrameObservation],
    *,
    role_names: Mapping[str, Iterable[str]],
) -> WindowResult:
    """Batch evaluation: the fold of :meth:`ConditionEvaluator.step` plus ``finish``."""
    evaluator = ConditionEvaluator(spec, role_names=role_names)
    for observation in observations:
        evaluator.step(observation)
    evaluator.finish()
    return evaluator.result

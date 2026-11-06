"""Live analysis-window runtime (ADR-011, § Live integration).

One :class:`ConditionRuntime` lives for one live session. It wraps the online
:class:`~zebtrack.core.conditions.ConditionEvaluator` and adds what only the
live pipeline has: a clock origin taken from the frame ledger, a thread-safe
inbox for Arduino and manual events, and the bookkeeping the pipeline acts on
(window phase for the UI, the instant to sweep the Arduino outputs, whether the
session must end).

Pure state on purpose: no Tk, no event bus, no recorder, no settings. The
pipeline (``frame_processing_pipeline.FrameProcessingMixin``) feeds it one
observation per ANALYSED frame from the processing thread and marshals every
side effect itself; Arduino and manual events arrive from other threads through
:meth:`ConditionRuntime.offer_external`, which only touches a ``SimpleQueue``.

Clock (ADR-011, § Clocks)
    ``t_s = t_capture_perf - t0_perf``, where ``t0_perf`` is the anchor of the
    session's ``6_FrameLedger`` — the same origin ``retime_from_ledger`` uses,
    so the ``online`` and ``offline`` sections of the artifact are on one clock.
    The trajectory ``timestamp`` is a PROCESSING clock (after the queue and the
    inference) and is never used here. Persistence holds are evaluated on these
    capture seconds: the live stream has duplicated frames (camera polling) and
    two decimation cadences, so counting frames is not a reliable measure of
    time; a ``Hold(frames=...)`` is accepted but warned about.

External events
    Stamped by their producer (the Arduino reader thread right after
    ``readline()``, the Tk thread at the button click) with ``perf_counter`` and
    delivered with the first analysed frame CAPTURED at or after that instant —
    the engine's ``External`` fires "on the observation that delivers the
    event". Events that never reach a frame (pressed after the last one) are
    still recorded in the artifact's ``external_events``.
"""

from __future__ import annotations

import queue
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import ValidationError

from zebtrack.core.conditions import (
    AnalysisWindowArtifact,
    ArtifactExternalEvent,
    ConditionEvaluator,
    External,
    ExternalEvent,
    FrameObservation,
    OnlineWindow,
    Persist,
    WindowEvent,
    WindowResult,
    WindowSpec,
    artifact_path,
    iter_nodes,
    write_artifact,
)
from zebtrack.core.conditions.model import _normalize_class_name
from zebtrack.i18n import _

__all__ = [
    "ConditionRuntime",
    "ExternalSource",
    "RuntimeUpdate",
    "WindowPhase",
    "classes_from_observations",
    "parse_window_spec",
    "role_names_from_role_map",
    "spec_listens_to",
    "window_phase_message",
]

log = structlog.get_logger()

ExternalSource = Literal["arduino", "manual"]


class WindowPhase(StrEnum):
    """Where the live window is. The values travel in UI payloads."""

    WAITING_START = "waiting_start"
    IN_ANALYSIS = "in_analysis"
    FINISHED = "finished"
    START_NOT_MET = "start_not_met"


@dataclass(frozen=True, slots=True)
class RuntimeUpdate:
    """What one :meth:`ConditionRuntime.step` (or ``finish``) changed.

    Attributes:
        phase: Phase after this call.
        phase_changed: Whether ``phase`` differs from the previous call's.
        events: Window events the engine confirmed in this call (0 or 1).
        stop_confirmed: This call confirmed the STOP: the Arduino outputs must
            be swept NOW (window STOP, not session end).
        end_session: The STOP was confirmed and the spec says
            ``on_stop="end_session"``. Set at most once per runtime (the engine
            confirms one STOP), never by :meth:`ConditionRuntime.finish` (the
            session is ending already).
    """

    phase: WindowPhase
    phase_changed: bool
    events: tuple[WindowEvent, ...] = ()
    stop_confirmed: bool = False
    end_session: bool = False


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def parse_window_spec(raw: Any) -> WindowSpec | None:
    """The window of a session, from ``project_data["analysis_window"]`` or a dialog config.

    ``None`` / empty means "no window" (pre-v8 behaviour). A spec that does not
    validate DEGRADES to ``None`` with a warning: the recording must never be
    refused because the analysis rule is unreadable — the analysis can still be
    re-run once the rule is fixed.
    """
    if raw is None:
        return None
    if isinstance(raw, WindowSpec):
        return raw
    if not isinstance(raw, Mapping) or not raw:
        if raw:
            log.warning("condition_runtime.spec.unexpected_type", type=type(raw).__name__)
        return None
    try:
        return WindowSpec.model_validate(dict(raw))
    except ValidationError as exc:
        log.warning("condition_runtime.spec.invalid", error=str(exc))
        return None


def spec_listens_to(spec: WindowSpec | None, source: ExternalSource) -> bool:
    """Whether any START/STOP node waits for an external event of ``source``."""
    if spec is None:
        return False
    for root in (spec.start, spec.stop):
        if root is None:
            continue
        for node in iter_nodes(root):
            if isinstance(node, External) and node.source == source:
                return True
    return False


def _uses_frame_holds(spec: WindowSpec) -> bool:
    for root in (spec.start, spec.stop):
        if root is None:
            continue
        for node in iter_nodes(root):
            if isinstance(node, Persist) and node.hold.frames is not None:
                return True
    return False


def role_names_from_role_map(role_map: Any) -> dict[str, frozenset[str]]:
    """``{role token: class names}`` from the detector's resolved ``ClassRoleMap``.

    ``None`` (a detector without roles, e.g. a test double) yields ``{}``: then
    only ``{"class": ...}`` targets can be satisfied, and ``{"role": ...}``
    targets are never present.
    """
    roles_as_dict = getattr(role_map, "roles_as_dict", None)
    if not callable(roles_as_dict):
        return {}
    grouped: dict[str, set[str]] = {}
    for name, role in dict(roles_as_dict()).items():
        grouped.setdefault(str(role), set()).add(_normalize_class_name(str(name)))
    return {role: frozenset(names) for role, names in grouped.items()}


def classes_from_observations(
    observations: Iterable[Mapping[str, Any]],
) -> dict[str, tuple[float, ...]]:
    """``{normalized class name: confidences}`` of one frame's class observations.

    ``observations`` are ``pop_class_observations()`` items. Malformed items
    are skipped; a missing confidence counts as ``0.0`` so the class is still
    PRESENT (only a ``min_confidence`` filter can discard it).
    """
    grouped: dict[str, list[float]] = {}
    for item in observations:
        name = item.get("class_name") if isinstance(item, Mapping) else None
        if not name:
            continue
        try:
            confidence = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        grouped.setdefault(_normalize_class_name(str(name)), []).append(confidence)
    return {name: tuple(values) for name, values in grouped.items()}


def window_phase_message(
    phase: WindowPhase | str,
    *,
    t_s: float | None = None,
    on_start_not_met: str | None = None,
) -> str:
    """User-facing sentence for a window phase (banner and preview status)."""
    token = WindowPhase(phase)
    if token is WindowPhase.WAITING_START:
        return _("Recording — waiting for the start condition of the analysis window.")
    if token is WindowPhase.IN_ANALYSIS:
        if t_s is None:
            return _("Analysis window open.")
        return _("Analysis window open since {seconds:.1f} s.").format(seconds=t_s)
    if token is WindowPhase.FINISHED:
        if t_s is None:
            return _("Analysis window finished.")
        return _("Analysis window finished at {seconds:.1f} s.").format(seconds=t_s)
    if on_start_not_met == "empty":
        return _("The start condition was never met: the window metrics will be empty.")
    return _("The start condition was never met: the whole recording will be analysed.")


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class ConditionRuntime:
    """Online evaluation of one window during one live session.

    Args:
        spec: The window (never written to the shared ``Settings``).
        role_names: Role -> class names, from the live detector's role map
            (:func:`role_names_from_role_map`).
        clock_origin: Returns the session's ``t0_perf`` (the frame ledger's
            anchor) or ``None`` while it is unknown. Without it, or while it
            returns ``None``, the first stepped frame's capture instant becomes
            the origin (warned): the live window then starts its clock at the
            first analysed frame instead of the first captured one.

    Thread model: :meth:`step`, :meth:`finish` and the read-only properties run
    on the processing thread. :meth:`offer_external` and :meth:`push_manual`
    may be called from ANY thread.
    """

    def __init__(
        self,
        spec: WindowSpec,
        *,
        role_names: Mapping[str, Iterable[str]],
        clock_origin: Callable[[], float | None] | None = None,
    ) -> None:
        self._spec = spec
        self._evaluator = ConditionEvaluator(spec, role_names=role_names)
        self._clock_origin = clock_origin
        self._origin: float | None = None
        self._inbox: queue.SimpleQueue[tuple[ExternalSource, int | None, float]] = (
            queue.SimpleQueue()
        )
        self._pending: list[tuple[float, ExternalSource, int | None]] = []
        self._seen: list[tuple[float, ExternalSource, int | None]] = []
        self._phase = WindowPhase.WAITING_START
        self._listens = {
            "arduino": spec_listens_to(spec, "arduino"),
            "manual": spec_listens_to(spec, "manual"),
        }
        if _uses_frame_holds(spec):
            log.warning(
                "condition_runtime.frame_hold_in_live",
                hint=(
                    "Live frames are polled from the camera (duplicates) and decimated "
                    "twice; a hold in seconds is the reliable measure."
                ),
            )

    # -- read-only state -----------------------------------------------------
    @property
    def spec(self) -> WindowSpec:
        """The window being evaluated."""
        return self._spec

    @property
    def phase(self) -> WindowPhase:
        """Phase after the last :meth:`step` / :meth:`finish`."""
        return self._phase

    @property
    def result(self) -> WindowResult:
        """The engine's current result (``pending`` until finished)."""
        return self._evaluator.result

    @property
    def origin_perf(self) -> float | None:
        """``perf_counter`` instant ``t_s = 0`` refers to, once known."""
        return self._origin

    @property
    def window_open(self) -> bool:
        """START confirmed and STOP not yet: per-ROI Arduino commands may run."""
        return self._phase is WindowPhase.IN_ANALYSIS

    @property
    def window_opened(self) -> bool:
        """Whether the window was ever open (START confirmed at some point)."""
        return self._evaluator.result.start is not None

    def listens_to(self, source: ExternalSource) -> bool:
        """Whether the spec waits for external events of ``source``."""
        return self._listens.get(source, False)

    @property
    def external_events(self) -> tuple[ExternalEvent, ...]:
        """Every external event offered so far, on the capture clock, in time order."""
        origin = self._origin
        if origin is None and self._clock_origin is not None:
            origin = self._clock_origin()
        if origin is None:
            origin = 0.0
        return tuple(
            ExternalEvent(source=source, code=code, t_s=t_perf - origin)
            for t_perf, source, code in sorted(self._seen, key=lambda item: item[0])
        )

    # -- producers (any thread) ----------------------------------------------
    def offer_external(self, source: ExternalSource, code: int | None, t_perf: float) -> bool:
        """Queue an external event stamped with ``perf_counter`` at its source.

        Returns:
            ``True`` when the spec waits for events of ``source``: the caller
            must then treat the event as CLAIMED by the window (for the
            Arduino, the recording coordinators must not act on it).
        """
        self._inbox.put((source, None if code is None else int(code), float(t_perf)))
        return self.listens_to(source)

    def push_manual(self, t_perf: float | None = None) -> bool:
        """The operator's "Mark start/stop" press, stamped now unless given."""
        stamp = time.perf_counter() if t_perf is None else float(t_perf)
        log.info("condition_runtime.manual_event", t_perf=stamp)
        return self.offer_external("manual", None, stamp)

    # -- consumer (processing thread) ----------------------------------------
    def step(
        self,
        *,
        frame: int,
        t_capture_perf: float,
        classes: Mapping[str, tuple[float, ...]],
        subject_rois: Iterable[str],
        t_wall: float | None = None,
    ) -> RuntimeUpdate:
        """Feed one analysed frame, dated by its CAPTURE instant."""
        origin = self._resolve_origin(t_capture_perf)
        observation = FrameObservation(
            frame=int(frame),
            t_s=float(t_capture_perf) - origin,
            classes=dict(classes),
            subject_rois=frozenset(subject_rois),
            external=self._deliver_external(float(t_capture_perf), origin),
            t_wall=t_wall,
        )
        events = tuple(self._evaluator.step(observation))
        return self._update(events, from_finish=False)

    def finish(self) -> RuntimeUpdate:
        """Close the stream (session end): an open window gets its end-of-stream STOP."""
        self._drain_inbox()
        events = tuple(self._evaluator.finish())
        return self._update(events, from_finish=True)

    def build_artifact(self, *, fps_video: float | None = None) -> AnalysisWindowArtifact:
        """The ``online`` + ``external_events`` part of ``7_AnalysisWindow_``.

        The ``offline`` section belongs to the analysis (it recomputes the
        window from the recorded inputs) and is left empty here.
        """
        self._drain_inbox()
        fps = fps_video if fps_video is not None and fps_video > 0 else None
        return AnalysisWindowArtifact.for_spec(
            self._spec,
            clock="capture_perf",
            fps_video=fps,
            external_events=tuple(
                ArtifactExternalEvent.from_event(event) for event in self.external_events
            ),
            online=OnlineWindow.from_result(self._evaluator.result),
        )

    def write_artifact(
        self, results_dir: str | Path, base_name: str, *, fps_video: float | None = None
    ) -> Path:
        """Write the artifact next to the trajectory of ``base_name`` (atomic).

        Raises:
            OSError: The write failed (the caller degrades: an artifact is
                optional, the recording is not).
        """
        path = artifact_path(results_dir, base_name)
        write_artifact(path, self.build_artifact(fps_video=fps_video))
        log.info(
            "condition_runtime.artifact_written",
            path=str(path),
            status=self._evaluator.result.status,
            external_events=len(self._seen),
        )
        return path

    # -- internals -----------------------------------------------------------
    def _resolve_origin(self, t_capture_perf: float) -> float:
        if self._origin is not None:
            return self._origin
        provided = self._clock_origin() if self._clock_origin is not None else None
        if provided is None:
            provided = float(t_capture_perf)
            log.warning(
                "condition_runtime.origin_from_first_frame",
                hint="no frame-ledger anchor yet; t_s=0 is the first analysed frame",
            )
        self._origin = float(provided)
        return self._origin

    def _drain_inbox(self) -> None:
        while True:
            try:
                source, code, t_perf = self._inbox.get_nowait()
            except queue.Empty:
                return
            item = (t_perf, source, code)
            self._pending.append(item)
            self._seen.append(item)

    def _deliver_external(self, t_capture_perf: float, origin: float) -> tuple[ExternalEvent, ...]:
        self._drain_inbox()
        if not self._pending:
            return ()
        self._pending.sort(key=lambda item: item[0])
        due = [item for item in self._pending if item[0] <= t_capture_perf]
        if not due:
            return ()
        self._pending = [item for item in self._pending if item[0] > t_capture_perf]
        return tuple(
            ExternalEvent(source=source, code=code, t_s=t_perf - origin)
            for t_perf, source, code in due
        )

    def _update(self, events: tuple[WindowEvent, ...], *, from_finish: bool) -> RuntimeUpdate:
        previous = self._phase
        result = self._evaluator.result
        if result.start is None:
            self._phase = (
                WindowPhase.START_NOT_MET if self._evaluator.finished else WindowPhase.WAITING_START
            )
        elif result.stop is None:
            self._phase = WindowPhase.IN_ANALYSIS
        else:
            self._phase = WindowPhase.FINISHED
        stop_confirmed = any(event.kind == "stop" for event in events)
        # The engine confirms the STOP exactly once, so this is signalled once.
        end_session = stop_confirmed and not from_finish and self._spec.on_stop == "end_session"
        for event in events:
            log.info(
                "condition_runtime.window_event",
                kind=event.kind,
                frame=event.frame,
                t_s=event.t_s,
                reason=event.reason,
                confirmed_t_s=event.confirmed_t_s,
            )
        return RuntimeUpdate(
            phase=self._phase,
            phase_changed=self._phase is not previous,
            events=events,
            stop_confirmed=stop_confirmed,
            end_session=end_session,
        )

"""Resolve the analysis window of one recording (ADR-011, front F4b).

Every analysis entry point — report coordinator, pipeline runner, summaries,
and the live post-processor (front F5) — gets its window from ONE function,
:func:`resolve_analysis_window`, so no two paths can apply different windows to
the same recording:

1. :func:`resolve_window_spec` reads the spec (``project_data["analysis_window"]``;
   ``None`` = analyse the whole recording, exactly as before v8).
2. :class:`AnalysisWindowService` finds START and STOP. It reuses the
   ``offline`` section of the ``7_AnalysisWindow_<base>.json`` artifact next to
   the trajectory when the spec hash AND the hashes of its inputs (trajectory,
   ``3c_Objetos_``, ROIs) still match; otherwise it rebuilds the observations
   (:mod:`zebtrack.analysis.window_observations`), folds them through
   :func:`zebtrack.core.conditions.evaluate_window` and rewrites the artifact
   atomically, keeping what only the live session could record (its
   ``external_events`` and ``online`` section).
3. The resulting :class:`WindowResolution` is handed to
   ``AnalysisService.run_full_analysis(window=...)``.

``offline`` governs the analysis. ``online`` (written live) only drove the
display and the session end; when it disagrees with ``offline`` by more than
one frame the report says so.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import structlog
from pydantic import ValidationError

from zebtrack.analysis.track_significance import (
    DEFAULT_MIN_TRACK_DURATION_S,
    min_track_duration_from,
)
from zebtrack.analysis.window_observations import (
    build_window_observations,
    missing_inputs,
    no_object_sidecar_warning,
)
from zebtrack.core.conditions import (
    ARTIFACT_PREFIX,
    AnalysisWindowArtifact,
    ArtifactEvent,
    ExternalEvent,
    OfflineWindow,
    OnlineWindow,
    RoiEdge,
    RoiInside,
    WindowSpec,
    evaluate_window,
    iter_nodes,
    read_artifact,
    spec_hash,
    write_artifact,
)
from zebtrack.i18n import _
from zebtrack.io.object_sidecar import (
    CLOCK_PTS,
    TRAJECTORY_PREFIX,
    read_object_sidecar,
    resolve_object_sidecar,
)

if TYPE_CHECKING:
    import pandas as pd

    from zebtrack.analysis.roi import ROI
    from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig

__all__ = [
    "AnalysisWindowService",
    "InvalidWindowSpecError",
    "WindowBound",
    "WindowResolution",
    "WindowStatusValue",
    "analysis_window_artifact_path",
    "project_subject_names",
    "resolve_analysis_window",
    "resolve_window_spec",
]

log = structlog.get_logger()

WindowStatusValue = Literal["complete", "censored", "start_not_met", "inputs_missing"]

#: An online START/STOP further than this from the offline one is reported.
_DIVERGENCE_FRAMES = 1

_HASH_CHUNK = 1 << 20


class InvalidWindowSpecError(ValueError):
    """``project_data["analysis_window"]`` is not a valid :class:`WindowSpec`.

    Raised instead of falling back to the whole recording: publishing numbers
    for the wrong interval without saying so is worse than not publishing.
    """


@dataclass(frozen=True)
class WindowBound:
    """START or STOP as the analysis uses it (the back-dated instant)."""

    frame: int
    t_s: float
    reason: str | None = None

    @classmethod
    def from_artifact(cls, event: ArtifactEvent | None) -> WindowBound | None:
        """Convert an artifact event (``None`` stays ``None``)."""
        if event is None:
            return None
        return cls(frame=int(event.frame), t_s=float(event.t_s), reason=event.reason)

    def as_dict(self) -> dict[str, Any]:
        """Report form: ``{"frame", "t_s", "reason"}``."""
        return {"frame": self.frame, "t_s": self.t_s, "reason": self.reason}


@dataclass(frozen=True)
class WindowResolution:
    """The window one analysis applies.

    Attributes:
        status: ``complete`` (STOP met), ``censored`` (the recording ended
            first), ``start_not_met`` or ``inputs_missing``.
        spec_hash: Hash of the spec that produced it.
        on_start_not_met: The spec's policy when there is no window to cut.
        clock: Clock of the instants (``pts`` or ``capture_perf``).
        start: START, back-dated (``None`` when not met).
        stop: STOP, back-dated (``None`` when not met).
        censored: STOP came from the end of the recording, not from its rule.
        reused: The artifact's ``offline`` section was reused as is.
        artifact_path: Where the ``7_`` artifact lives (``None`` without one).
        warnings: User-facing warnings for the report, already translated.
        missing: What the spec needed and the recording lacks.
        aquarium_id: Aquarium the window belongs to (``None`` = single arena).
        spec: The spec as stored (JSON form), for the report's rule note.
    """

    status: WindowStatusValue
    spec_hash: str
    on_start_not_met: str = "whole_recording"
    clock: str = CLOCK_PTS
    start: WindowBound | None = None
    stop: WindowBound | None = None
    censored: bool = False
    reused: bool = False
    artifact_path: Path | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)
    aquarium_id: int | None = None
    spec: Mapping[str, Any] | None = None

    @property
    def met(self) -> bool:
        """START and STOP exist: the analysis is cut to them."""
        return (
            self.status in ("complete", "censored")
            and self.start is not None
            and self.stop is not None
        )

    @property
    def cut(self) -> tuple[float, float] | None:
        """``(t_start, t_end)`` to cut at, or ``None`` when nothing is cut."""
        if not self.met or self.start is None or self.stop is None:
            return None
        return (self.start.t_s, self.stop.t_s)

    @property
    def is_empty(self) -> bool:
        """No window and the spec asked for empty metrics in that case."""
        return not self.met and self.on_start_not_met == "empty"

    @property
    def applied(self) -> Literal["window", "empty", "whole_recording"]:
        """What the analysis actually measured."""
        if self.met:
            return "window"
        return "empty" if self.is_empty else "whole_recording"

    @property
    def window_duration_s(self) -> float | None:
        """STOP - START; ``0.0`` for an empty window; ``None`` for the whole recording."""
        cut = self.cut
        if cut is not None:
            return cut[1] - cut[0]
        return 0.0 if self.is_empty else None

    @property
    def reason(self) -> str | None:
        """Why the window ended (the STOP reason), or why there is none."""
        if self.stop is not None:
            return self.stop.reason
        return None if self.met else self.status

    def cache_token(self) -> str:
        """Stable token of the applied window, for the metrics cache key."""
        cut = self.cut
        bounds = "none" if cut is None else f"{cut[0]:.9f}-{cut[1]:.9f}"
        return f"{self.spec_hash}|{self.applied}|{bounds}"

    def to_report(self) -> dict[str, Any]:
        """``report["analysis_window"]`` (English keys; new in v8)."""
        return {
            "status": self.status,
            "applied": self.applied,
            "start": None if self.start is None else self.start.as_dict(),
            "stop": None if self.stop is None else self.stop.as_dict(),
            "reason": self.reason,
            "censored": self.censored,
            "spec_hash": self.spec_hash,
            "window_duration_s": self.window_duration_s,
            "clock": self.clock,
            "on_start_not_met": self.on_start_not_met,
            "missing_inputs": list(self.missing),
            "spec": None if self.spec is None else dict(self.spec),
        }


# ---------------------------------------------------------------------------
# Spec lookup
# ---------------------------------------------------------------------------


def resolve_window_spec(
    project_data: Mapping[str, Any] | None,
    video_entry: Mapping[str, Any] | None = None,
) -> WindowSpec | None:
    """The window spec an analysis must apply; ``None`` = the whole recording.

    A video entry carrying its own ``analysis_window`` key wins over the
    project's (``None`` there explicitly means "this video, whole recording").

    Raises:
        InvalidWindowSpecError: The stored spec does not validate.
    """
    raw: Any = None
    if isinstance(video_entry, Mapping) and "analysis_window" in video_entry:
        raw = video_entry.get("analysis_window")
    elif isinstance(project_data, Mapping):
        raw = project_data.get("analysis_window")
    if raw is None:
        return None
    if isinstance(raw, WindowSpec):
        return raw
    try:
        return WindowSpec.model_validate(raw)
    except ValidationError as exc:
        log.error("analysis_window.spec.invalid", errors=exc.error_count())
        raise InvalidWindowSpecError(
            _(
                "The project's analysis window is invalid ({count} error(s)); "
                "open the analysis window editor and save it again."
            ).format(count=exc.error_count())
        ) from exc


def project_subject_names(project_data: Mapping[str, Any] | None) -> list[str]:
    """Class names the project maps to the ``subject`` role (ADR-009)."""
    overrides = (project_data or {}).get("model_overrides")
    roles = overrides.get("class_roles") if isinstance(overrides, Mapping) else None
    if not isinstance(roles, Mapping):
        return []
    return sorted(str(name) for name, role in roles.items() if str(role) == "subject")


def analysis_window_artifact_path(trajectory_path: str | os.PathLike[str]) -> Path:
    """``7_AnalysisWindow_<base>.json`` next to the trajectory.

    Derived from the TRAJECTORY path, never from a results folder: the
    multi-aquarium pre-recorded layout (``Grupo_*/Dia_*/Sujeito_*``) puts each
    aquarium's trajectory somewhere a folder rule would not find.
    """
    path = Path(trajectory_path)
    name = path.name
    base = (
        name[len(TRAJECTORY_PREFIX) : -len(".parquet")]
        if name.startswith(TRAJECTORY_PREFIX) and name.endswith(".parquet")
        else path.stem
    )
    return path.with_name(f"{ARTIFACT_PREFIX}{base}.json")


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def _file_sha(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _uses_rois(spec: WindowSpec) -> bool:
    return any(
        isinstance(node, RoiInside | RoiEdge)
        for root in (spec.start, spec.stop)
        if root is not None
        for node in iter_nodes(root)
    )


def _rois_sha(rois: Sequence[ROI], roi_rule: RoiRuleConfig | None) -> str:
    parts = [
        {
            "name": roi.name,
            "space": roi.coordinate_space,
            "wkb": getattr(roi.geometry, "wkb_hex", str(roi.geometry)),
        }
        for roi in sorted(rois, key=lambda r: r.name)
    ]
    payload = json.dumps({"rois": parts, "rule": repr(roi_rule)}, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AnalysisWindowService:
    """Find START/STOP of a recording and keep its ``7_`` artifact current.

    Args:
        roi_rule: The report's resolved ROI rule, so ``RoiInside`` conditions
            use the same presence as the ROI metrics (default rule if ``None``).
        min_track_duration_s: The report's ``min_track_duration_s``
            (``min_track_duration_from(settings)``), so the window drops the
            same short tracks the report does (#671).
    """

    def __init__(
        self,
        *,
        roi_rule: RoiRuleConfig | None = None,
        min_track_duration_s: float = DEFAULT_MIN_TRACK_DURATION_S,
    ) -> None:
        self._roi_rule = roi_rule
        self._min_track_duration_s = float(min_track_duration_s)

    def resolve(
        self,
        trajectory_path: str | os.PathLike[str] | None,
        spec: WindowSpec,
        *,
        aquarium_id: int | None = None,
        trajectory_df: pd.DataFrame | None = None,
        rois: Sequence[ROI] = (),
        subject_names: Iterable[str] = (),
        clock: str | None = None,
        pixelcm: tuple[float, float] = (1.0, 1.0),
        mask_source: Any = None,
    ) -> WindowResolution:
        """Resolve the window of the recording whose trajectory is ``trajectory_path``.

        Args:
            trajectory_path: The ``3_CoordMovimento_`` file. Its folder holds the
                ``3c`` sidecar and the ``7_`` artifact. ``None`` evaluates
                ``trajectory_df`` without any artifact (nothing reused or written).
            spec: The window to apply.
            aquarium_id: Multi-aquarium: this aquarium's rows and evaluator.
            trajectory_df: The trajectory already loaded (and, live, re-timed
                on the capture clock), in the same pixel space as ``rois``.
                Read from ``trajectory_path`` when omitted.
            rois: ROIs for ``RoiInside``/``RoiEdge`` conditions.
            subject_names: Class names known to be the subject (used only
                when there is no ``3c``).
            clock: Clock of the trajectory when there is no ``3c``.
            pixelcm: Calibration, for the buffered-centroid ROI rule.
            mask_source: ``3b`` sidecar, for the ``seg_overlap`` rule.
        """
        digest = spec_hash(spec)
        path = None if trajectory_path is None else Path(trajectory_path)
        artifact_file = None if path is None else analysis_window_artifact_path(path)
        objects_file = None if path is None else resolve_object_sidecar(path)

        inputs: dict[str, str | None] = {
            "trajectory_sha": _file_sha(path),
            "objects_sha": _file_sha(objects_file),
        }
        if _uses_rois(spec):
            inputs["rois_sha"] = _rois_sha(rois, self._roi_rule)
        # The subjects the observations are built from (#671): an artifact
        # computed before rows without an id and short tracks were screened, or
        # with another threshold, is recomputed rather than reused.
        inputs["subject_screening"] = f"untracked+short:{self._min_track_duration_s:g}"

        existing = (
            read_artifact(artifact_file)
            if artifact_file is not None and artifact_file.is_file()
            else None
        )
        same_spec = existing is not None and existing.spec_hash == digest

        if (
            same_spec
            and existing is not None
            and existing.offline is not None
            and existing.offline.inputs == inputs
            and inputs["trajectory_sha"] is not None
        ):
            log.info("analysis_window.resolve.reused", path=str(artifact_file))
            return self._resolution(
                spec,
                existing.offline,
                clock=existing.clock,
                online=existing.online,
                has_objects=inputs["objects_sha"] is not None,
                reused=True,
                artifact_path=artifact_file,
                aquarium_id=aquarium_id,
            )

        if trajectory_df is None and path is not None and path.is_file():
            import pandas as pd

            trajectory_df = pd.read_parquet(path)
        objects_df = read_object_sidecar(objects_file)
        external = (
            [
                ExternalEvent(source=e.source, code=e.code, t_s=float(e.t_s))
                for e in existing.external_events
            ]
            if existing is not None
            else []
        )
        built = build_window_observations(
            trajectory_df,
            objects_df=objects_df,
            rois=rois,
            roi_rule=self._roi_rule,
            external_events=external,
            aquarium_id=aquarium_id,
            subject_names=subject_names,
            clock=clock,
            pixelcm=pixelcm,
            mask_source=mask_source,
            min_track_duration_s=self._min_track_duration_s,
        )
        missing = missing_inputs(
            spec,
            has_objects=built.has_objects,
            subject_names=built.subject_names,
            roi_names=[roi.name for roi in rois],
        )
        if missing:
            offline = OfflineWindow(status="inputs_missing", inputs=dict(inputs))
            log.warning("analysis_window.resolve.inputs_missing", missing=missing)
        else:
            result = evaluate_window(spec, built.observations, role_names=built.role_names)
            offline = OfflineWindow.from_result(result, inputs=inputs)

        online = existing.online if same_spec and existing is not None else OnlineWindow()
        if artifact_file is not None:
            self._write(
                artifact_file,
                spec,
                offline,
                clock=built.clock,
                fps_video=_fps_video(built.observations),
                aquarium_id=aquarium_id,
                existing=existing,
                online=online,
            )
        return self._resolution(
            spec,
            offline,
            clock=built.clock,
            online=online,
            has_objects=built.has_objects,
            reused=False,
            artifact_path=artifact_file,
            aquarium_id=aquarium_id,
            missing=tuple(missing),
        )

    @staticmethod
    def _write(
        artifact_file: Path,
        spec: WindowSpec,
        offline: OfflineWindow,
        *,
        clock: str,
        fps_video: float | None,
        aquarium_id: int | None,
        existing: AnalysisWindowArtifact | None,
        online: OnlineWindow,
    ) -> None:
        clock_token = clock if clock in ("pts", "capture_perf") else CLOCK_PTS
        artifact = AnalysisWindowArtifact.for_spec(
            spec,
            clock=clock_token,
            fps_video=fps_video,
            aquarium_id=aquarium_id,
            # Recorded facts of the session: they survive a spec change.
            external_events=existing.external_events if existing is not None else (),
            online=online,
            offline=offline,
        )
        try:
            write_artifact(artifact_file, artifact)
        except OSError as exc:
            # The window is still applied; only the cache of it is lost.
            log.warning(
                "analysis_window.artifact.write_failed", path=str(artifact_file), error=str(exc)
            )

    @staticmethod
    def _resolution(
        spec: WindowSpec,
        offline: OfflineWindow,
        *,
        clock: str,
        online: OnlineWindow,
        has_objects: bool,
        reused: bool,
        artifact_path: Path | None,
        aquarium_id: int | None,
        missing: tuple[str, ...] = (),
    ) -> WindowResolution:
        start = WindowBound.from_artifact(offline.start)
        stop = WindowBound.from_artifact(offline.stop)
        status: WindowStatusValue = offline.status
        if status == "inputs_missing" and not missing:
            missing = ("objects",)
        resolution = WindowResolution(
            status=status,
            spec_hash=spec_hash(spec),
            on_start_not_met=spec.on_start_not_met,
            clock=clock,
            start=start,
            stop=stop,
            censored=status == "censored",
            reused=reused,
            artifact_path=artifact_path,
            missing=missing,
            aquarium_id=aquarium_id,
            spec=spec.model_dump(mode="json", by_alias=True),
        )
        warnings = _report_warnings(resolution, online=online, has_objects=has_objects)
        return replace(resolution, warnings=tuple(warnings))


def _fps_video(observations: Sequence[Any]) -> float | None:
    if len(observations) < 2:
        return None
    span = float(observations[-1].t_s) - float(observations[0].t_s)
    frames = int(observations[-1].frame) - int(observations[0].frame)
    if span <= 0 or frames <= 0:
        return None
    return frames / span


def _diverges(online: ArtifactEvent | None, offline: WindowBound | None) -> bool:
    if online is None or offline is None:
        return False
    return abs(int(online.frame) - int(offline.frame)) > _DIVERGENCE_FRAMES


def _report_warnings(
    resolution: WindowResolution, *, online: OnlineWindow, has_objects: bool
) -> list[str]:
    """Translated warnings the report must carry for this window."""
    warnings: list[str] = []
    if not has_objects:
        warnings.append(no_object_sidecar_warning())
    whole = resolution.applied == "whole_recording"
    if resolution.status == "start_not_met":
        warnings.append(
            _(
                "The analysis window never started (its START condition was not met). "
                "The metrics cover the whole recording."
            )
            if whole
            else _(
                "The analysis window never started (its START condition was not met). "
                "The window metrics are empty, as the window rule asks."
            )
        )
    elif resolution.status == "inputs_missing":
        warnings.append(
            _(
                "The analysis window could not be evaluated: the recording lacks {missing}. "
                "The metrics cover the whole recording."
            ).format(missing=", ".join(resolution.missing))
            if whole
            else _(
                "The analysis window could not be evaluated: the recording lacks {missing}. "
                "The window metrics are empty, as the window rule asks."
            ).format(missing=", ".join(resolution.missing))
        )
    elif resolution.status == "censored":
        warnings.append(
            _(
                "The recording ended before the analysis window's STOP condition; the window "
                "was closed at the end of the recording (censored)."
            )
        )
    # One complete msgid per edge (#642): splicing an English START/STOP into a
    # translated sentence left it half in English and gave the translator a
    # noun no Portuguese article could agree with.
    if _diverges(online.start, resolution.start):
        assert online.start is not None and resolution.start is not None
        warnings.append(
            _(
                "The live session started the analysis window at frame {online}, the "
                "re-analysis at frame {offline}; the report uses the re-analysis."
            ).format(online=online.start.frame, offline=resolution.start.frame)
        )
    if _diverges(online.stop, resolution.stop):
        assert online.stop is not None and resolution.stop is not None
        warnings.append(
            _(
                "The live session ended the analysis window at frame {online}, the "
                "re-analysis at frame {offline}; the report uses the re-analysis."
            ).format(online=online.stop.frame, offline=resolution.stop.frame)
        )
    return warnings


# ---------------------------------------------------------------------------
# The one entry every analysis path calls
# ---------------------------------------------------------------------------


def resolve_analysis_window(
    project_data: Mapping[str, Any] | None,
    trajectory_path: str | os.PathLike[str] | None,
    *,
    video_entry: Mapping[str, Any] | None = None,
    trajectory_df: pd.DataFrame | None = None,
    rois: Sequence[ROI] = (),
    aquarium_id: int | None = None,
    roi_rule: RoiRuleConfig | None = None,
    settings_obj: Any = None,
    pixelcm: tuple[float, float] = (1.0, 1.0),
    clock: str | None = None,
    mask_source: Any = None,
) -> WindowResolution | None:
    """Window for one analysis run; ``None`` when the project defines none.

    The single call every entry point makes before ``run_full_analysis``
    (pre-recorded reports and summaries, the pipeline runner, the summary view
    model, and the live post-processor). Pass the trajectory in the SAME pixel
    space as ``rois`` (the coordinators normalise both to the arena's local
    space) and, live, already re-timed on the capture clock with
    ``clock="capture_perf"``.

    Raises:
        InvalidWindowSpecError: The project's spec does not validate.
    """
    spec = resolve_window_spec(project_data, video_entry)
    if spec is None:
        return None
    if roi_rule is None:
        from zebtrack.core.services.roi_rule_resolver import resolve_roi_rule

        roi_rule = resolve_roi_rule(
            dict(project_data) if isinstance(project_data, Mapping) else None, settings_obj
        )
    resolution = AnalysisWindowService(
        roi_rule=roi_rule, min_track_duration_s=min_track_duration_from(settings_obj)
    ).resolve(
        trajectory_path,
        spec,
        aquarium_id=aquarium_id,
        trajectory_df=trajectory_df,
        rois=rois,
        subject_names=project_subject_names(project_data),
        clock=clock,
        pixelcm=pixelcm,
        mask_source=mask_source,
    )
    log.info(
        "analysis_window.resolved",
        trajectory=str(trajectory_path) if trajectory_path else None,
        aquarium_id=aquarium_id,
        status=resolution.status,
        applied=resolution.applied,
        reused=resolution.reused,
        start=None if resolution.start is None else resolution.start.t_s,
        stop=None if resolution.stop is None else resolution.stop.t_s,
    )
    return resolution

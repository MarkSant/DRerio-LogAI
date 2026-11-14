"""Single rule for the analysis interval — and for the display interval, which follows it.

There is ONE number the researcher sets: how many frames to skip between
analysed frames. The preview redraw interval is not a second decision; it is the
same number.

Why this module exists
----------------------

Three places resolved the pair independently and could disagree:

* ``MultiAquariumCoordinator._determine_processing_intervals``;
* ``SequentialProcessingCoordinator`` (inline, in the middle of building a
  processing context);
* ``AnalysisService.determine_processing_intervals``.

Two separate inputs were also still on screen — the single-video config dialog
and the zone tab's single-video panel — even though project creation had already
dropped the display field on the grounds that it "only regulates preview redraw,
never the analysed data". Keeping an input that cannot change a result is the
same defect this codebase keeps removing elsewhere: a control that writes a value
nothing meaningfully reads.

Tying display to analysis also removes a real trap. With ``analysis=10`` and
``display=5`` the overlay redrew on frames that carried NO fresh detection, so
the preview showed a stale box on half the frames it painted — indistinguishable
from a tracker that had stopped updating.

Legacy ``display_interval_frames`` values stored in old projects are read only to
report that they are being ignored; they never change the outcome.

The offset (#638)
-----------------

``video_processing.processing_offset`` picks WHICH frame of each interval is
analysed: frame ``i`` (counted from 0 at the first frame of the source) is
analysed iff ``i % N == offset``. It was validated and documented for years while
no loop read it — pre-recorded sampled ``0, N, 2N`` and live (whose pipeline
numbers frames from 1) ``N, 2N``, so the two flows did not even agree with each
other. :func:`is_analysis_frame` is now the one test every sampling loop asks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()

__all__ = [
    "ProcessingIntervals",
    "is_analysis_frame",
    "resolve_processing_intervals",
    "resolve_processing_offset",
]

#: Last-resort interval when nothing else supplies one. Matches the historical
#: ``video_processing.processing_interval`` default.
DEFAULT_ANALYSIS_INTERVAL = 10

_KEY = "analysis_interval_frames"
_OFFSET_KEY = "analysis_offset_frames"
_LEGACY_DISPLAY_KEY = "display_interval_frames"


@dataclass(frozen=True)
class ProcessingIntervals:
    """Resolved answer to "how often do we analyse, and how often do we redraw?"."""

    analysis: int
    """Frames between analysed frames."""

    offset: int = 0
    """Which frame of each interval is analysed (``0 <= offset < analysis``)."""

    def is_analysis_frame(self, frame_index: int) -> bool:
        """See :func:`is_analysis_frame`."""
        return is_analysis_frame(frame_index, self.analysis, self.offset)

    @property
    def display(self) -> int:
        """Frames between preview redraws — always the analysis interval.

        Exposed as a property rather than a second field so no caller can
        construct a pair where the two disagree.
        """
        return self.analysis


def _coerce_interval(value: object, *, source: str) -> int | None:
    """Normalize one candidate interval, or ``None`` to fall through.

    Missing is an ordinary "no preference here" and is silent. A value that is
    present but unusable IS worth a warning: someone wrote it expecting it to
    matter. Never raises — a bad interval must not turn "analyse this video"
    into a traceback.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        interval = int(value)
    except (TypeError, ValueError):
        log.warning(
            "processing_interval_resolver.invalid",
            source=source,
            value=str(value),
        )
        return None
    if interval <= 0:
        log.warning(
            "processing_interval_resolver.non_positive",
            source=source,
            value=interval,
        )
        return None
    return interval


def is_analysis_frame(frame_index: int, interval: int, offset: int = 0) -> bool:
    """Whether the frame at ``frame_index`` of its source is analysed.

    ``frame_index`` counts from **0 at the first frame of the source**: the
    pre-recorded worker's ``frame_num`` as is, and the live pipeline's 1-based
    frame number minus one. Counting the same way is what puts both flows on
    the same phase: ``interval=10, offset=1`` analyses the 2nd, 12th, 22nd frame
    of a video file and of a camera session alike.
    """
    step = max(int(interval), 1)
    return frame_index % step == offset % step


def _coerce_offset(value: object, *, source: str) -> int | None:
    """Normalize one candidate offset, or ``None`` to fall through (never raises)."""
    if value is None or isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        offset = int(value)
    except (TypeError, ValueError):
        log.warning("processing_interval_resolver.offset_invalid", source=source, value=str(value))
        return None
    if offset < 0:
        log.warning("processing_interval_resolver.offset_negative", source=source, value=offset)
        return None
    return offset


def resolve_processing_offset(
    interval: int,
    project_data: dict[str, Any] | None = None,
    settings_obj: Any = None,
) -> int:
    """Resolve the sampling offset for a run analysing every ``interval`` frames.

    Precedence: ``project_data["analysis_offset_frames"]`` >
    ``settings.video_processing.processing_offset`` > ``0``. ``Settings``
    validates ``offset < processing_interval``, but a run may use a smaller
    interval (per-run config, project); an offset past it wraps (``% interval``)
    with a warning rather than silently never matching a frame.
    """
    project_data = project_data or {}
    offset = _coerce_offset(project_data.get(_OFFSET_KEY), source="project_data")
    if offset is None:
        offset = _coerce_offset(
            getattr(
                getattr(settings_obj, "video_processing", None),
                "processing_offset",
                None,
            ),
            source="settings",
        )
    if offset is None:
        return 0
    step = max(int(interval), 1)
    # With every frame analysed (step 1) all offsets are the same phase; the
    # default ``processing_offset: 1`` there is not worth a warning per run.
    if offset >= step > 1:
        log.warning(
            "processing_interval_resolver.offset_wrapped",
            offset=offset,
            interval=step,
            effective=offset % step,
        )
    return offset % step


def resolve_processing_intervals(
    config: dict[str, Any] | None = None,
    project_data: dict[str, Any] | None = None,
    settings_obj: Any = None,
) -> ProcessingIntervals:
    """Resolve the analysis interval; the display interval follows it.

    Precedence: ``config["analysis_interval_frames"]`` >
    ``project_data["analysis_interval_frames"]`` >
    ``settings.video_processing.processing_interval`` > ``10``.

    Args:
        config: Per-run config (the single-video dialog's dict). ``None`` skips
            this level, which is what the project batch path does.
        project_data: The open project's data dict.
        settings_obj: Injected ``Settings`` (never the module singleton).
    """
    config = config or {}
    project_data = project_data or {}

    analysis = (
        _coerce_interval(config.get(_KEY), source="config")
        or _coerce_interval(project_data.get(_KEY), source="project_data")
        or _coerce_interval(
            getattr(
                getattr(settings_obj, "video_processing", None),
                "processing_interval",
                None,
            ),
            source="settings",
        )
        or DEFAULT_ANALYSIS_INTERVAL
    )

    stored_display = _coerce_interval(
        config.get(_LEGACY_DISPLAY_KEY, project_data.get(_LEGACY_DISPLAY_KEY)),
        source="legacy_display",
    )
    if stored_display is not None and stored_display != analysis:
        log.info(
            "processing_interval_resolver.legacy_display_ignored",
            stored=stored_display,
            analysis=analysis,
        )

    return ProcessingIntervals(
        analysis=analysis,
        offset=resolve_processing_offset(analysis, project_data, settings_obj),
    )

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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()

__all__ = ["ProcessingIntervals", "resolve_processing_intervals"]

#: Last-resort interval when nothing else supplies one. Matches the historical
#: ``video_processing.processing_interval`` default.
DEFAULT_ANALYSIS_INTERVAL = 10

_KEY = "analysis_interval_frames"
_LEGACY_DISPLAY_KEY = "display_interval_frames"


@dataclass(frozen=True)
class ProcessingIntervals:
    """Resolved answer to "how often do we analyse, and how often do we redraw?"."""

    analysis: int
    """Frames between analysed frames."""

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

    return ProcessingIntervals(analysis=analysis)

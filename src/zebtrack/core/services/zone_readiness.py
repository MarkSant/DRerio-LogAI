"""Single source for "does this video already have an arena and ROIs?".

Before this module the question was answered in at least three places with three
slightly different rules -- ``_single_video_mixin`` derived it from a ``ZoneData``,
the live coordinators derived it from parquet files on disk, and the UI simply did
not ask. They answer *different* questions and the difference matters:

- **On disk** (``1_ArenaROI_*.parquet`` in a results folder) means "this video was
  already ANALYSED once". That is a history check.
- **In ``project_data``** means "this video is ready to analyse NOW". That is the
  readiness check, and it is the only one that can gate a Start button.

This module owns the second one. It deliberately asks the project manager rather
than reading files, so it reports what the detector would actually receive.

Arena vs ROIs are reported separately because they gate different things: without
an arena there is no detection region at all, so analysis cannot start; without
ROIs the analysis still runs and only the ROI-occupancy metrics come out empty.
Collapsing the two into one "ready" flag would either block work that could
proceed or silently produce reports with empty ROI columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import structlog

if TYPE_CHECKING:  # pragma: no cover - typing only
    from zebtrack.core.project.project_manager import ProjectManager

log = structlog.get_logger()

__all__ = ["ZoneReadiness", "resolve_zone_readiness", "zone_data_readiness"]


class _ZoneManagerLike(Protocol):
    """The slice of ``ProjectManager`` this module needs."""

    def get_zone_data(self, video_path: Any = ..., **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class ZoneReadiness:
    """What a single video already has defined in ``project_data``."""

    video_path: str
    has_arena: bool
    has_rois: bool

    @property
    def can_analyse(self) -> bool:
        """Whether analysis can start at all.

        Gated on the arena only -- see the module docstring for why ROIs do not
        block.
        """
        return self.has_arena


def zone_data_readiness(zone_data: Any) -> tuple[bool, bool]:
    """Return ``(has_arena, has_rois)`` for a ``ZoneData`` or ``MultiAquariumZoneData``.

    The two shapes are distinguished by the ``aquariums`` attribute, mirroring the
    idiom already used in ``coordinators/_single_video_mixin``. A multi-aquarium
    entry counts as having ROIs when ANY aquarium defines them: analysis of the
    remaining aquariums is still meaningful, and demanding all of them would block
    a legitimate partially-configured project.
    """
    if zone_data is None:
        return False, False

    aquariums = getattr(zone_data, "aquariums", None)
    if aquariums is not None:
        return bool(aquariums), any(bool(aq.roi_polygons) for aq in aquariums)

    return bool(getattr(zone_data, "polygon", None)), bool(getattr(zone_data, "roi_polygons", None))


def resolve_zone_readiness(
    project_manager: ProjectManager | _ZoneManagerLike | None,
    video_path: Path | str,
) -> ZoneReadiness:
    """Report what ``video_path`` already has defined, degrading to "nothing".

    Multi-aquarium is consulted FIRST: ``get_zone_data()`` is a legacy shim that
    returns only aquarium 0, so a project whose aquarium 0 happens to be empty
    would read as "no arena" even with the other aquariums fully configured.

    Never raises. A readiness probe that throws would turn a disabled button into
    a crash, and every caller here is a UI gate.
    """
    path_text = str(video_path)
    if project_manager is None or not path_text:
        return ZoneReadiness(video_path=path_text, has_arena=False, has_rois=False)

    multi_getter = getattr(project_manager, "get_multi_aquarium_zone_data", None)
    if callable(multi_getter):
        try:
            multi_data = multi_getter(video_path)
        except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
            log.debug("zone_readiness.multi_aquarium.unavailable", video=path_text, error=str(exc))
        else:
            has_arena, has_rois = zone_data_readiness(multi_data)
            if has_arena:
                return ZoneReadiness(video_path=path_text, has_arena=has_arena, has_rois=has_rois)

    try:
        zone_data = project_manager.get_zone_data(video_path=video_path)
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        log.warning("zone_readiness.zone_data.failed", video=path_text, error=str(exc))
        return ZoneReadiness(video_path=path_text, has_arena=False, has_rois=False)

    has_arena, has_rois = zone_data_readiness(zone_data)
    return ZoneReadiness(video_path=path_text, has_arena=has_arena, has_rois=has_rois)

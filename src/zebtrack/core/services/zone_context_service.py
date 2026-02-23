"""Zone context resolution service.

Encapsulates the logic for determining which ZoneData (single or multi-aquarium)
applies to the currently active video/project context.  Extracted from
``ApplicationGUI._get_zone_data_for_active_context`` during Phase 10 shim-layer
removal so that UI components can receive this service via DI instead of calling
back into the GUI object.

Phase 10 — gui.py shim-layer removal (Audit-2 Phase 3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union

import structlog

from zebtrack.core.detection import MultiAquariumZoneData, ZoneData

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager

log = structlog.get_logger()


class ZoneContextService:
    """Resolve the active ``ZoneData`` for the current project/video context.

    Args:
        project_manager: The shared ``ProjectManager`` instance (injected from
            Composition Root).
    """

    def __init__(self, project_manager: ProjectManager | None = None) -> None:
        self._project_manager = project_manager

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def project_manager(self) -> Any:
        """Return the project manager (may be ``None`` before a project is opened)."""
        return self._project_manager

    @project_manager.setter
    def project_manager(self, value: Any) -> None:
        self._project_manager = value

    # ------------------------------------------------------------------
    # Core resolution
    # ------------------------------------------------------------------

    def get_zone_data_for_active_context(
        self,
        *,
        pending_single_video_path: str | None = None,
    ) -> Union[ZoneData, MultiAquariumZoneData]:  # noqa: UP007
        """Return the ``ZoneData`` (or ``MultiAquariumZoneData``) for the active context.

        Resolution order:

        1. If a multi-aquarium configuration exists for the active video, return
           the ``MultiAquariumZoneData``.
        2. Otherwise return the per-video ``ZoneData`` (with Live-project global
           fallback when applicable).
        3. If nothing matched, fall back to the global ``ZoneData``.

        Args:
            pending_single_video_path: An optional video path that has been
                selected by the user but not yet persisted as the "active zone
                video" in ``ProjectManager``.  Used by the single-video workflow.

        Returns:
            ``ZoneData`` or ``MultiAquariumZoneData``.  Never ``None`` — returns
            an empty ``ZoneData()`` as the ultimate fallback.
        """
        pm = self._project_manager
        if pm is None:
            return ZoneData()

        active_video = pm.get_active_zone_video()
        if not active_video:
            active_video = pending_single_video_path

        # v2.3.1: For Live projects, always fallback to global detection_zones
        # since zones are defined once for the entire project, not per-video
        is_live_project = pm.get_project_type() == "live"

        if active_video:
            try:
                # Check for multi-aquarium data first
                if hasattr(pm, "is_multi_aquarium_video") and pm.is_multi_aquarium_video(
                    active_video
                ):
                    multi_data = pm.get_multi_aquarium_zone_data(active_video)
                    if multi_data:
                        return multi_data

                zone_data = pm.get_zone_data(
                    video_path=active_video,
                    fallback_to_global=is_live_project,
                )
            except (KeyError, ValueError, TypeError, FileNotFoundError):
                zone_data = ZoneData()

            if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                return zone_data

        return pm.get_zone_data()

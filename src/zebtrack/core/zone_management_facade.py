"""
ZoneManagementFacade: Isola lógica de zonas e ROIs do MainViewModel.

Responsabilidades:
- Desenho de zonas (arena, ROIs)
- Templates de ROI (save/load/apply)
- Validação de coordenadas
- Escalonamento para diferentes resoluções
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog
from shapely.geometry import Polygon

if TYPE_CHECKING:
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager

log = structlog.get_logger()


class ZoneManagementFacade:
    """Facade for zone management."""

    def __init__(
        self,
        project_manager: ProjectManager,
        state_manager: StateManager,
    ):
        """
        Initialize ZoneManagementFacade.

        Args:
            project_manager: ProjectManager for zone persistence
            state_manager: StateManager for zone state tracking
        """
        self.project_manager = project_manager
        self.state_manager = state_manager

        log.info("zone_management_facade.initialized")

    def start_arena_drawing(self, video_path: Path) -> bool:
        """
        Initiate arena drawing mode.

        Args:
            video_path: Video for which to draw arena

        Returns:
            True if drawing mode started
        """
        try:
            # Update state to drawing mode
            self.state_manager.update_ui_state(
                source="zone_facade.start_arena_drawing",
                canvas_view_mode="arena_drawing",
            )

            # Update project state to track active video
            self.state_manager.update_project_state(
                source="zone_facade.start_arena_drawing",
                active_zone_video=str(video_path),
            )

            log.info("zone_facade.arena_drawing.started", video=str(video_path))
            return True

        except Exception as e:
            log.error("zone_facade.arena_drawing.failed", error=str(e), exc_info=True)
            return False

    def save_arena(self, polygon: list[tuple[float, float]], video_path: Path) -> bool:
        """
        Save arena polygon for video.

        Args:
            polygon: List of (x, y) coordinates
            video_path: Video associated with arena

        Returns:
            True if saved successfully
        """
        try:
            # Validate polygon structure
            if len(polygon) < 3:
                raise ValueError("Arena must have at least 3 points")

            polygon_geom = Polygon(polygon)
            if not polygon_geom.is_valid or polygon_geom.area <= 0:
                raise ValueError("Arena polygon must be valid and enclose non-zero area")

            # Save to project
            self.project_manager.set_arena_for_video(  # type: ignore[attr-defined]
                video_path=str(video_path),
                polygon=polygon,
            )

            # Update state
            self.state_manager.update_ui_state(
                source="zone_facade.save_arena",
                canvas_view_mode="zones",
            )

            log.info(
                "zone_facade.arena.saved",
                video=str(video_path),
                points=len(polygon),
            )
            return True

        except Exception as e:
            log.error("zone_facade.save_arena.failed", error=str(e), exc_info=True)
            return False

    def load_roi_template(self, template_name: str) -> dict[str, Any]:
        """
        Load ROI template from library.

        Args:
            template_name: Name of template to load

        Returns:
            Template data dict
        """
        try:
            template_data = self.project_manager.roi_template_manager.load_template(  # type: ignore[attr-defined]
                template_name
            )

            log.info("zone_facade.template.loaded", name=template_name)
            return cast(dict[str, Any], template_data)

        except Exception as e:
            log.error("zone_facade.load_template.failed", error=str(e), exc_info=True)
            return {}

    def apply_template_to_video(
        self,
        template_name: str,
        video_path: Path,
        scale_to_arena: bool = True,
    ) -> bool:
        """
        Apply ROI template to video.

        Args:
            template_name: Template to apply
            video_path: Target video
            scale_to_arena: Whether to scale ROIs to fit arena

        Returns:
            True if applied successfully
        """
        try:
            template = self.load_roi_template(template_name)

            if not template:
                raise ValueError(f"Template '{template_name}' not found")

            # Extract data handling both dict and ZoneData object
            if isinstance(template, dict):
                roi_polygons = template.get("roi_polygons", [])
                roi_names = template.get("roi_names", [])
                roi_colors = template.get("roi_colors", [])
                source_arena = template.get("polygon")
            else:
                # Assume object (ZoneData)
                roi_polygons = getattr(template, "roi_polygons", [])
                roi_names = getattr(template, "roi_names", [])
                roi_colors = getattr(template, "roi_colors", [])
                source_arena = getattr(template, "polygon", None)

            # Get arena for scaling
            target_arena = self.project_manager.get_arena_for_video(str(video_path))  # type: ignore[attr-defined]

            # Scale ROIs if needed
            if scale_to_arena and target_arena and source_arena:
                scaled_rois = self._scale_rois_to_arena(
                    roi_polygons,
                    target_arena,
                    source_arena,
                )
            else:
                scaled_rois = roi_polygons

            # Save to project
            self.project_manager.set_rois_for_video(  # type: ignore[attr-defined]
                video_path=str(video_path),
                roi_polygons=scaled_rois,
                roi_names=roi_names,
                roi_colors=roi_colors,
            )

            log.info(
                "zone_facade.template.applied",
                template=template_name,
                video=str(video_path),
                roi_count=len(scaled_rois),
            )
            return True

        except Exception as e:
            log.error("zone_facade.apply_template.failed", error=str(e), exc_info=True)
            return False

    def get_arena_for_video(self, video_path: Path) -> list[tuple[float, float]] | None:
        """
        Get arena polygon for a video.

        Args:
            video_path: Path to video

        Returns:
            Arena polygon or None if not set
        """
        try:
            arena = self.project_manager.get_arena_for_video(str(video_path))  # type: ignore[attr-defined]
            return arena
        except Exception as e:
            log.error("zone_facade.get_arena.failed", error=str(e), exc_info=True)
            return None

    def get_rois_for_video(self, video_path: Path) -> dict[str, Any]:
        """
        Get ROI data for a video.

        Args:
            video_path: Path to video

        Returns:
            Dict with roi_polygons, roi_names, roi_colors
        """
        try:
            rois = self.project_manager.get_rois_for_video(str(video_path))  # type: ignore[attr-defined]
            return rois if rois else {}
        except Exception as e:
            log.error("zone_facade.get_rois.failed", error=str(e), exc_info=True)
            return {}

    def clear_arena(self, video_path: Path) -> bool:
        """
        Clear arena for a video.

        Args:
            video_path: Path to video

        Returns:
            True if cleared successfully
        """
        try:
            self.project_manager.set_arena_for_video(  # type: ignore[attr-defined]
                video_path=str(video_path),
                polygon=None,
            )
            log.info("zone_facade.arena.cleared", video=str(video_path))
            return True
        except Exception as e:
            log.error("zone_facade.clear_arena.failed", error=str(e), exc_info=True)
            return False

    def clear_rois(self, video_path: Path) -> bool:
        """
        Clear ROIs for a video.

        Args:
            video_path: Path to video

        Returns:
            True if cleared successfully
        """
        try:
            self.project_manager.set_rois_for_video(  # type: ignore[attr-defined]
                video_path=str(video_path),
                roi_polygons=[],
                roi_names=[],
                roi_colors=[],
            )
            log.info("zone_facade.rois.cleared", video=str(video_path))
            return True
        except Exception as e:
            log.error("zone_facade.clear_rois.failed", error=str(e), exc_info=True)
            return False

    def list_available_templates(self) -> list[str]:
        """
        List available ROI templates.

        Returns:
            List of template names
        """
        try:
            templates = self.project_manager.roi_template_manager.list_templates()  # type: ignore[attr-defined]
            return templates
        except Exception as e:
            log.error("zone_facade.list_templates.failed", error=str(e), exc_info=True)
            return []

    def _scale_rois_to_arena(
        self,
        rois: list[Any],
        target_arena: list[tuple[float, float]],
        source_arena: list[tuple[float, float]] | None = None,
    ) -> list[Any]:
        """
        Scale ROIs to fit within target arena bounds relative to source arena.

        Args:
            rois: List of ROI polygons
            target_arena: Target arena polygon
            source_arena: Source arena polygon (optional)

        Returns:
            Scaled ROI polygons
        """
        if not source_arena or len(source_arena) < 3 or not rois:
            return rois

        if not target_arena or len(target_arena) < 3:
            return rois

        try:
            # Calculate bounds manually to avoid shapely dependency overhead
            s_xs = [p[0] for p in source_arena]
            s_ys = [p[1] for p in source_arena]
            minx_s, miny_s, maxx_s, maxy_s = min(s_xs), min(s_ys), max(s_xs), max(s_ys)

            t_xs = [p[0] for p in target_arena]
            t_ys = [p[1] for p in target_arena]
            minx_t, miny_t, maxx_t, maxy_t = min(t_xs), min(t_ys), max(t_xs), max(t_ys)

            w_s, h_s = maxx_s - minx_s, maxy_s - miny_s
            w_t, h_t = maxx_t - minx_t, maxy_t - miny_t

            if w_s <= 0 or h_s <= 0:
                return rois

            scale_x = w_t / w_s
            scale_y = h_t / h_s

            scaled_rois = []
            for roi in rois:
                scaled_points = []
                for point in roi:
                    # Handle both tuple and list points
                    x, y = point[0], point[1]
                    new_x = minx_t + (x - minx_s) * scale_x
                    new_y = miny_t + (y - miny_s) * scale_y
                    scaled_points.append((new_x, new_y))
                scaled_rois.append(scaled_points)

            return scaled_rois

        except Exception as e:
            log.warning("zone_facade.scaling_failed", error=str(e))
            return rois

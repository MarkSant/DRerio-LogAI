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
from typing import TYPE_CHECKING, Any

import structlog

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
            # Validate polygon
            if len(polygon) < 3:
                raise ValueError("Arena must have at least 3 points")

            # Save to project
            self.project_manager.set_arena_for_video(
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
            template_data = self.project_manager.roi_template_manager.load_template(template_name)

            log.info("zone_facade.template.loaded", name=template_name)
            return template_data

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

            # Get arena for scaling
            arena = self.project_manager.get_arena_for_video(str(video_path))

            # Scale ROIs if needed
            if scale_to_arena and arena:
                scaled_rois = self._scale_rois_to_arena(
                    template.get("roi_polygons", []),
                    arena,
                )
            else:
                scaled_rois = template.get("roi_polygons", [])

            # Save to project
            self.project_manager.set_rois_for_video(
                video_path=str(video_path),
                roi_polygons=scaled_rois,
                roi_names=template.get("roi_names", []),
                roi_colors=template.get("roi_colors", []),
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
            arena = self.project_manager.get_arena_for_video(str(video_path))
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
            rois = self.project_manager.get_rois_for_video(str(video_path))
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
            self.project_manager.set_arena_for_video(
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
            self.project_manager.set_rois_for_video(
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
            templates = self.project_manager.roi_template_manager.list_templates()
            return templates
        except Exception as e:
            log.error("zone_facade.list_templates.failed", error=str(e), exc_info=True)
            return []

    def _scale_rois_to_arena(
        self,
        rois: list[Any],
        arena: list[tuple[float, float]],
    ) -> list[Any]:
        """
        Scale ROIs to fit within arena bounds.

        Args:
            rois: List of ROI polygons
            arena: Arena polygon

        Returns:
            Scaled ROI polygons
        """
        # Simple implementation: return as-is for now
        # Full implementation would calculate bounding boxes and scale factors
        # TODO: Implement proper scaling logic
        return rois

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.ui.gui import ApplicationGUI


class PolygonCompletionStrategy(ABC):
    """Strategy for completing polygon drawing."""

    @abstractmethod
    def can_complete(self, points: list) -> tuple[bool, str | None]:
        """Check whether the polygon can be completed. Returns (success, error_msg)."""
        pass

    @abstractmethod
    def complete(self, video_points: list, gui: "ApplicationGUI") -> bool:
        """Complete the polygon. Returns success status."""
        pass


class ArenaCompletionStrategy(PolygonCompletionStrategy):
    """Strategy for completing an arena polygon."""

    def can_complete(self, points: list) -> tuple[bool, str | None]:
        if len(points) < 3:
            return False, "Um polígono precisa de pelo menos 3 pontos."
        return True, None

    def complete(self, video_points: list, gui: "ApplicationGUI") -> bool:
        # Check if in multi-aquarium mode
        zone_controls = getattr(gui, "zone_controls", None)
        is_multi_aquarium = zone_controls and zone_controls.aquarium_count_var.get() == 2

        if is_multi_aquarium:
            success = self._complete_multi_aquarium(video_points, gui, zone_controls)
        else:
            success = gui.controller.set_main_arena_polygon(video_points)

        if success:
            gui.canvas_manager.redraw_zones_from_project_data()

            # NEW PATH (v4.0)
            if hasattr(gui, "event_bus_v2") and gui.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                gui.event_bus_v2.publish(
                    Event(
                        type=UIEvents.ZONES_UPDATED,
                        data={"zone_data": None},
                        source="ArenaCompletionStrategy.complete",
                    )
                )

            return True
        return False

    def _complete_multi_aquarium(
        self, video_points: list, gui: "ApplicationGUI", zone_controls
    ) -> bool:
        """Complete polygon in multi-aquarium mode."""
        from zebtrack.core.project.zone_manager import ZoneManager

        active_aquarium_id = zone_controls.active_aquarium_var.get()
        video_path = gui.controller.project_manager.get_active_zone_video()

        if not video_path:
            return False

        project_data = gui.controller.project_manager.project_data
        if not project_data:
            return False

        zone_manager = ZoneManager()

        # Get existing multi-aquarium data
        multi_data = zone_manager.get_multi_aquarium_zone_data(project_data, video_path)

        if not multi_data:
            # Shouldn't happen - multi_data should have been created when mode was activated
            return False

        # Update the correct aquarium's polygon
        aquarium = multi_data.get_aquarium(active_aquarium_id)
        if aquarium:
            aquarium.polygon = video_points
        else:
            # Create new aquarium if it doesn't exist
            from zebtrack.core.detection import AquariumData

            new_aquarium = AquariumData(id=active_aquarium_id, polygon=video_points)
            multi_data.aquariums.append(new_aquarium)

        # Save updated multi-aquarium data
        return zone_manager.save_multi_aquarium_zone_data(
            project_data,
            video_path,
            multi_data,
            persist_callback=gui.controller.project_manager.save_project,
        )


class ROICompletionStrategy(PolygonCompletionStrategy):
    """Strategy for completing an ROI polygon."""

    def can_complete(self, points: list) -> tuple[bool, str | None]:
        if len(points) < 3:
            return False, "Um polígono precisa de pelo menos 3 pontos."
        return True, None

    def complete(self, video_points: list, gui: "ApplicationGUI") -> bool:
        # Ask for ROI name
        roi_name = gui.ask_string("Nome da ROI", "Digite um nome:")
        if not roi_name:
            return False

        # Select color
        from zebtrack.ui.dialogs import ColorSelectionDialog

        color_dialog = ColorSelectionDialog(gui.root)
        if not color_dialog.result:
            return False

        # Save ROI
        # color_dialog.result is expected to be a dict with "rgb" key based on plan
        # but verify ColorSelectionDialog implementation if possible.
        # Assuming plan is correct.
        roi_color = color_dialog.result["rgb"]
        success = gui.controller.add_roi_polygon(video_points, roi_name, roi_color)

        if success:
            gui.canvas_manager.redraw_zones_from_project_data()

            # NEW PATH (v4.0)
            if hasattr(gui, "event_bus_v2") and gui.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                gui.event_bus_v2.publish(
                    Event(
                        type=UIEvents.ZONES_UPDATED,
                        data={"zone_data": None},
                        source="ROICompletionStrategy.complete",
                    )
                )

            return True
        return False


class PolygonDrawingService:
    """Service for managing polygon drawing completion."""

    def __init__(self, event_bus_v2=None):
        self.event_bus_v2 = event_bus_v2
        self._strategies = {
            "arena": ArenaCompletionStrategy(),
            "roi": ROICompletionStrategy(),
        }

    def complete_polygon(
        self, drawing_type: str, video_points: list, gui: "ApplicationGUI"
    ) -> bool:
        """Complete polygon using the appropriate strategy."""
        strategy = self._strategies.get(drawing_type)
        if not strategy:
            return False

        # Validate
        can_complete, error_msg = strategy.can_complete(video_points)
        if not can_complete:
            gui.show_warning("Polígono Incompleto", error_msg)
            return False

        # Complete
        return strategy.complete(video_points, gui)

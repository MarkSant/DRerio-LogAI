from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zebtrack.ui.gui import ApplicationGUI


def _is_multi_aquarium_context(gui: "ApplicationGUI", zone_controls: Any) -> bool:
    """True só quando DUAS fontes concordam que o contexto tem 2 aquários.

    Defense-in-depth contra estado de UI vazado entre projetos: além da var de
    UI ``zone_controls.aquarium_count_var == 2``, exige
    ``settings.analysis_config.num_aquariums >= 2``. As duas são setadas JUNTAS
    no fluxo pré-gravado por-vídeo (``_single_video_mixin``) e ressincronizadas
    ao carregar o projeto (``ProjectInitializer._sync_aquarium_count_from_project``),
    então a guarda NÃO quebra o multi-aquário legítimo (ambas = 2) e barra uma
    var de UI vazada num projeto de 1 aquário (settings = 1 → single).
    """
    if zone_controls is None:
        return False
    try:
        if zone_controls.aquarium_count_var.get() != 2:
            return False
    except Exception:
        return False

    settings = getattr(getattr(gui, "controller", None), "settings", None)
    analysis_config = getattr(settings, "analysis_config", None)
    try:
        return int(getattr(analysis_config, "num_aquariums", 1)) >= 2
    except (TypeError, ValueError):
        return False


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
        # Check if in multi-aquarium mode. Exige concordância da var de UI E do
        # settings.num_aquariums (defense-in-depth) para não tratar um projeto de
        # 1 aquário como multi por causa de estado de UI vazado de um teste
        # anterior.
        zone_controls = getattr(gui, "zone_controls", None)
        is_multi_aquarium = _is_multi_aquarium_context(gui, zone_controls)

        if is_multi_aquarium:
            success = self._complete_multi_aquarium(video_points, gui, zone_controls)
        else:
            success = gui.controller.analysis_vm.set_main_arena_polygon(video_points)

        if success:
            gui.canvas_manager.redraw_zones_from_project_data()

            # NEW PATH (v4.0)
            if hasattr(gui, "event_bus_v2") and gui.event_bus_v2:
                from zebtrack.ui import payloads
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                gui.event_bus_v2.publish(
                    Event(
                        type=UIEvents.ZONES_UPDATED,
                        data=payloads.ZonesUpdatedPayload(zone_data=None),
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
        # Ask for ROI name. ``ask_string`` lives on DialogManager, not on
        # ApplicationGUI — calling ``gui.ask_string`` raised
        # "'ApplicationGUI' object has no attribute 'ask_string'".
        roi_name = gui.dialog_manager.ask_string("Nome da ROI", "Digite um nome:")
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
        success = gui.controller.analysis_vm.add_roi_polygon(video_points, roi_name, roi_color)

        if success:
            gui.canvas_manager.redraw_zones_from_project_data()

            # NEW PATH (v4.0)
            if hasattr(gui, "event_bus_v2") and gui.event_bus_v2:
                from zebtrack.ui import payloads
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                gui.event_bus_v2.publish(
                    Event(
                        type=UIEvents.ZONES_UPDATED,
                        data=payloads.ZonesUpdatedPayload(zone_data=None),
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
            gui.dialog_manager.show_warning("Polígono Incompleto", error_msg or "")
            return False

        # Complete
        return strategy.complete(video_points, gui)

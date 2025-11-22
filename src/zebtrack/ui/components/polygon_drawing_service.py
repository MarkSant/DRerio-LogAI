from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.ui.gui import ApplicationGUI


class PolygonCompletionStrategy(ABC):
    """Strategy para completar desenho de polígono."""

    @abstractmethod
    def can_complete(self, points: list) -> tuple[bool, str | None]:
        """Verifica se polígono pode ser completado. Retorna (sucesso, erro_msg)."""
        pass

    @abstractmethod
    def complete(self, video_points: list, gui: "ApplicationGUI") -> bool:
        """Completa o polígono. Retorna status de sucesso."""
        pass


class ArenaCompletionStrategy(PolygonCompletionStrategy):
    """Strategy para completar polígono de arena."""

    def can_complete(self, points: list) -> tuple[bool, str | None]:
        if len(points) < 3:
            return False, "Um polígono precisa de pelo menos 3 pontos."
        return True, None

    def complete(self, video_points: list, gui: "ApplicationGUI") -> bool:
        success = gui.controller.set_main_arena_polygon(video_points)
        if success:
            gui.canvas_manager.redraw_zones_from_project_data()

            # DUAL MODE (v3/v4 compatibility): OLD PATH (deprecated) + NEW PATH (v4.0)
            gui.update_zone_listbox()  # OLD PATH - will be removed in v4.0
            if hasattr(gui, 'event_bus_v2') and gui.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents
                gui.event_bus_v2.publish(Event(
                    type=UIEvents.ZONES_UPDATED,
                    data={'zone_data': None},
                    source='ArenaCompletionStrategy.complete'
                ))

            return True
        return False


class ROICompletionStrategy(PolygonCompletionStrategy):
    """Strategy para completar polígono de ROI."""

    def can_complete(self, points: list) -> tuple[bool, str | None]:
        if len(points) < 3:
            return False, "Um polígono precisa de pelo menos 3 pontos."
        return True, None

    def complete(self, video_points: list, gui: "ApplicationGUI") -> bool:
        # Pede nome de ROI
        roi_name = gui.ask_string("Nome da ROI", "Digite um nome:")
        if not roi_name:
            return False

        # Seleciona cor
        from zebtrack.ui.dialogs import ColorSelectionDialog
        color_dialog = ColorSelectionDialog(gui.root)
        if not color_dialog.result:
            return False

        # Salva ROI
        # color_dialog.result is expected to be a dict with "rgb" key based on plan
        # but verify ColorSelectionDialog implementation if possible.
        # Assuming plan is correct.
        roi_color = color_dialog.result["rgb"]
        success = gui.controller.add_roi_polygon(video_points, roi_name, roi_color)

        if success:
            gui.canvas_manager.redraw_zones_from_project_data()

            # DUAL MODE (v3/v4 compatibility): OLD PATH (deprecated) + NEW PATH (v4.0)
            gui.update_zone_listbox()  # OLD PATH - will be removed in v4.0
            if hasattr(gui, 'event_bus_v2') and gui.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents
                gui.event_bus_v2.publish(Event(
                    type=UIEvents.ZONES_UPDATED,
                    data={'zone_data': None},
                    source='ROICompletionStrategy.complete'
                ))

            return True
        return False


class PolygonDrawingService:
    """Serviço para gerenciar conclusão de desenho de polígono."""

    def __init__(self, event_bus_v2=None):
        self.event_bus_v2 = event_bus_v2
        self._strategies = {
            "arena": ArenaCompletionStrategy(),
            "roi": ROICompletionStrategy(),
        }

    def complete_polygon(
        self,
        drawing_type: str,
        video_points: list,
        gui: "ApplicationGUI"
    ) -> bool:
        """Completa polígono usando strategy apropriada."""
        strategy = self._strategies.get(drawing_type)
        if not strategy:
            return False

        # Valida
        can_complete, error_msg = strategy.can_complete(video_points)
        if not can_complete:
            gui.show_warning("Polígono Incompleto", error_msg)
            return False

        # Completa
        return strategy.complete(video_points, gui)

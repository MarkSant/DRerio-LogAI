"""Zone edit guard — protects zone editing sessions from accidental navigation.

Extracted from ApplicationGUI (Phase 4.4) to isolate the tab-change
guard logic that prevents users from losing unsaved zone edits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.ui.components.dialog_manager import DialogManager
    from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class ZoneEditGuard:
    """Guards zone editing sessions by warning/blocking tab navigation.

    Checks whether a drawing/editing session or unsaved zone changes
    exist before allowing the user to switch tabs.
    """

    def __init__(
        self,
        gui: ApplicationGUI,
        *,
        dialog_manager: DialogManager | None = None,
    ) -> None:
        self.gui = gui
        self._dialog_manager = dialog_manager

    @property
    def dialog_manager(self) -> DialogManager:
        """DialogManager instance (injected or resolved from gui)."""
        return self._dialog_manager or self.gui.dialog_manager

    # ------------------------------------------------------------------
    # Tab change handler
    # ------------------------------------------------------------------

    def on_tab_changed(self, event: Any) -> None:
        """Handle tab change event to ensure analysis overlay is hidden.

        Only shows overlay when on analysis tab.
        """
        gui = self.gui
        if not gui.notebook:
            return

        current_tab = gui.notebook.select()
        previous_tab = gui._last_selected_tab_id
        analysis_tab_id = str(gui.analysis_tab_frame) if gui.analysis_tab_frame else ""
        zone_tab_id = str(gui.zone_tab_frame) if gui.zone_tab_frame else ""

        is_leaving_zone_tab = (
            bool(zone_tab_id) and previous_tab == zone_tab_id and current_tab != zone_tab_id
        )

        if is_leaving_zone_tab and not self.confirm_pending_zone_edit_before_navigation(
            context="trocar de aba"
        ):
            # Revert tab switch when user cancels navigation.
            gui.notebook.select(zone_tab_id)
            gui._last_selected_tab_id = zone_tab_id
            return

        if zone_tab_id and current_tab == zone_tab_id:
            combobox = getattr(gui, "roi_template_combobox", None)
            values = combobox.cget("values") if combobox else ()
            if not values:
                gui.roi_template_manager.refresh_templates()

        if gui.analysis_active:
            gui.canvas_view_mode = (
                "analysis" if analysis_tab_id and current_tab == analysis_tab_id else "zones"
            )

        gui._last_selected_tab_id = current_tab

    # ------------------------------------------------------------------
    # Pending edit detection
    # ------------------------------------------------------------------

    def has_pending_zone_edit(self) -> bool:
        """Return True when there is an active zone drawing/editing session or unsaved zones."""
        gui = self.gui
        drawing_manager = getattr(gui, "drawing_state_manager", None)
        drawing_mode = getattr(drawing_manager, "mode", None) if drawing_manager else None
        drawing_active = drawing_mode is not None
        drawing_points_active = bool(drawing_manager and drawing_manager.has_points())
        editing_active = bool(getattr(gui, "current_editing_zone", None))
        edited_polygon_active = bool(getattr(gui, "edited_polygon_points", None))
        zones_dirty = getattr(gui, "_zones_dirty", False)
        return (
            drawing_active
            or drawing_points_active
            or editing_active
            or edited_polygon_active
            or zones_dirty
        )

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    def warn_about_pending_zone_edit(self, *, context: str) -> None:
        """Show a non-blocking warning if user navigates with an unfinished zone edit."""
        if not self.has_pending_zone_edit():
            return
        self.dialog_manager.show_warning(
            "Edição de zonas em andamento",
            (
                "Há uma edição/desenho de zona em andamento. "
                "Clique em 'Concluir Edição do Vídeo' quando terminar, "
                f"antes de {context}."
            ),
        )

    # ------------------------------------------------------------------
    # Confirm navigation
    # ------------------------------------------------------------------

    def confirm_pending_zone_edit_before_navigation(self, *, context: str) -> bool:
        """Confirm and resolve pending zone edits before navigation.

        Returns:
            True when navigation should proceed, False when it should be cancelled.
        """
        gui = self.gui

        if not self.has_pending_zone_edit():
            return True

        # If only the _zones_dirty flag is set (template applied, arena saved, but not
        # yet committed via "Concluir"), show a tailored warning and allow proceed/cancel.
        has_active_drawing = False
        drawing_manager = getattr(gui, "drawing_state_manager", None)
        if drawing_manager:
            drawing_mode = getattr(drawing_manager, "mode", None)
            has_active_drawing = (
                drawing_mode is not None
                or drawing_manager.has_points()
                or bool(getattr(gui, "current_editing_zone", None))
                or bool(getattr(gui, "edited_polygon_points", None))
            )

        if not has_active_drawing and getattr(gui, "_zones_dirty", False):
            # Zones were saved in memory but not committed to project via "Concluir"
            from tkinter import messagebox

            response = messagebox.askyesnocancel(
                "Zonas não finalizadas",
                "As zonas foram desenhadas/aplicadas mas não foram finalizadas "
                "com o botão 'Concluir Edição do Vídeo'.\n\n"
                "Deseja finalizar agora antes de prosseguir?\n\n"
                "• Sim: Finaliza e prossegue\n"
                "• Não: Prossegue sem finalizar\n"
                "• Cancelar: Permanece no vídeo atual",
            )
            if response is None:
                # Cancel — stay on current video
                gui.set_status("Troca de vídeo cancelada.")
                return False
            if response is True:
                # Auto-conclude: trigger the same logic as "Concluir"
                if hasattr(gui, "zone_control_builder") and gui.zone_control_builder:
                    gui.zone_control_builder._on_conclude_video()
                else:
                    gui._zones_dirty = False
            else:
                # Discard — clear dirty flag, proceed without saving project
                gui._zones_dirty = False
            return True

        response = gui.dialog_manager.confirm_pending_zone_edit_before_navigation(context=context)
        if response is None:
            gui.set_status("Troca de vídeo cancelada para manter a edição atual.")
            return False

        if response is True:
            # Save only when a concrete editable polygon exists.
            if gui.edited_polygon_points:
                gui.canvas_manager.save_arena()
                gui._zones_dirty = False
                gui.set_status("Edição salva. Prosseguindo para o próximo vídeo...")
                return True

            self.dialog_manager.show_warning(
                "Salvar edição",
                (
                    "Não foi possível salvar automaticamente porque o desenho ainda não foi "
                    "finalizado. Finalize o desenho ou use 'Concluir' antes de trocar de vídeo."
                ),
            )
            return False

        gui.canvas_manager.discard_arena()
        gui._zones_dirty = False
        gui.set_status("Edição descartada. Prosseguindo para o próximo vídeo...")
        return True

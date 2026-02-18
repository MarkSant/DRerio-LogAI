"""Zone editing and management for CanvasManager.

Extracted from canvas_manager.py (Phase 4.5) to reduce God Object complexity.
Handles zone CRUD operations (save/discard/remove/edit), drawing lifecycle
(polygon and circle modes), zone clipboard operations, color mapping, and
zone listbox management.

All methods access the parent CanvasManager via self.canvas_manager back-reference.
"""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

import numpy as np
import structlog
import ttkbootstrap as ttk

from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.ui.components.canvas_manager import CanvasManager

log = structlog.get_logger()


class ZoneEditor:
    """Manages zone editing and CRUD operations for CanvasManager.

    Handles:
    - Zone listbox updates and processing mode toggling
    - Arena/ROI save, discard, and clear operations
    - Interactive polygon editing lifecycle
    - Polygon and circle drawing initiation and events
    - ROI removal with confirmation
    - Zone copy/paste/delete clipboard operations
    - Color mapping (BGR to Portuguese color names)
    - Geotaxis visualization toggling
    """

    # BGR to color name mapping (matches color_selection_dialog.py)
    _BGR_COLOR_MAP: typing.ClassVar = {
        (0, 128, 0): "Verde",
        (255, 0, 0): "Azul",
        (0, 0, 255): "Vermelho",
        (0, 204, 204): "Amarelo",
        (255, 0, 255): "Magenta",
        (255, 255, 0): "Ciano",
    }

    def __init__(self, canvas_manager: CanvasManager) -> None:
        """Initialize ZoneEditor.

        Args:
            canvas_manager: Reference to the parent CanvasManager instance.
        """
        self.canvas_manager = canvas_manager

        # Zone clipboard (for copy/paste operations)
        self._zone_clipboard: dict | None = None

    @property
    def gui(self):
        """Shortcut to parent CanvasManager's gui reference."""
        return self.canvas_manager.gui

    # -------------------------------------------------------------------------
    # Zone Listbox & Processing Mode
    # -------------------------------------------------------------------------

    def update_zone_listbox(self, zone_data=None) -> None:
        """Update zone listbox. Delegates to Renderer and ZoneControls."""
        self.canvas_manager.renderer.redraw_zones(zone_data)

        # Update the listbox widget via ZoneControls (Restored Logic)
        if zone_data is None:
            zone_data = self.gui._get_zone_data_for_active_context()

        controls = getattr(self.gui, "zone_controls", None)

        # Handle Multi-Aquarium Data for Listbox
        from zebtrack.core.detector import MultiAquariumZoneData

        if isinstance(zone_data, MultiAquariumZoneData):
            if controls:
                active_id = controls.active_aquarium_var.get()
                zone_data = zone_data.to_zone_data(active_id)
            else:
                # Fallback to first aquarium if controls not available
                zone_data = zone_data.to_zone_data(0)

        if controls:
            controls.clear_zone_list()
            # Add Arena with dark teal color (matching the overlay drawing)
            if zone_data.polygon:
                controls.add_zone_to_list(
                    "arena", "🏟 Arena Principal", "Polígono", "Teal", "#008B8B"
                )
            # Add ROIs
            if zone_data.roi_names:
                for i, name in enumerate(zone_data.roi_names):
                    color_bgr = (
                        zone_data.roi_colors[i] if i < len(zone_data.roi_colors) else (0, 128, 0)
                    )
                    # BGR to Hex for tag styling
                    color_hex = f"#{color_bgr[2]:02x}{color_bgr[1]:02x}{color_bgr[0]:02x}"
                    # Get color name from BGR value
                    color_name = self._get_color_name_from_bgr(color_bgr)
                    controls.add_zone_to_list(
                        f"roi_{i}", f"📍 {name}", "ROI", color_name, color_hex
                    )

        self.update_roi_button_state()

    def update_processing_mode(self, sequential: bool) -> None:
        """Update the processing mode (parallel vs sequential) for multi-aquarium.

        Args:
            sequential: If True, process each aquarium separately (2 video passes).
                       If False, process both aquariums simultaneously (1 video pass).
        """
        zone_data = self.gui._get_zone_data_for_active_context()

        from zebtrack.core.detector import MultiAquariumZoneData

        if isinstance(zone_data, MultiAquariumZoneData):
            zone_data.sequential_processing = sequential

            # Persist change to disk so it survives for batch processing
            video_path = self.gui.controller.project_manager.get_active_zone_video()
            if video_path:
                should_persist = bool(self.gui.controller.project_manager.project_path)
                self.gui.controller.project_manager.save_multi_aquarium_zone_data(
                    video_path, zone_data, persist=should_persist
                )

            log.info(
                "canvas_manager.processing_mode_updated",
                sequential=sequential,
                mode="sequential" if sequential else "parallel",
                persisted=bool(video_path),
            )
        else:
            log.debug(
                "canvas_manager.processing_mode_ignored",
                reason="not_multi_aquarium",
            )

    # -------------------------------------------------------------------------
    # Drawing Lifecycle (Polygon & Circle)
    # -------------------------------------------------------------------------

    def start_polygon_drawing(self):
        """Activates polygon drawing mode."""
        # Garante que há frame no canvas
        if self.canvas_manager._canvas_bg_image is None:
            self.gui.set_status("Carregando frame para desenho...")
            if not self.canvas_manager.load_video_frame_to_canvas():
                self.gui.show_error(
                    "Erro",
                    "Não foi possível carregar um frame. "
                    "Por favor, carregue um vídeo ou use 'Detectar Aquário (Auto)' "
                    "primeiro.",
                )
                return False

        # Preserve drawing type before cleaning
        preserved_drawing_type = self.gui.drawing_state_manager.drawing_type
        self.stop_drawing()  # Ensure clean state
        self.gui.drawing_state_manager.drawing_type = preserved_drawing_type  # Restore

        self.gui.drawing_state_manager.start_polygon_drawing()
        self.canvas_manager.event_handler.bind_drawing_events()

        # Add a persistent instruction label
        # Use zone_controls_frame
        # (Phase 6 fix: use zone_controls.zone_controls_frame)
        zc_frame = self.gui.zone_controls.zone_controls_frame if self.gui.zone_controls else None
        zc_listbox = self.gui.zone_controls.zone_listbox if self.gui.zone_controls else None

        if not self.gui.drawing_instruction_label and zc_frame and zc_listbox:
            self.gui.drawing_instruction_label = ttk.Label(
                zc_frame,
                text="Clique para adicionar pontos.\nClique duplo para finalizar.\n"
                "Ctrl+Z: Desfazer | Ctrl+Y: Refazer",
                justify="center",
                relief="solid",
                padding=5,
            )
            self.gui.drawing_instruction_label.pack(pady=5, before=zc_listbox.master)

        # Create floating undo/redo buttons over canvas
        self.gui._create_drawing_buttons()

        self.gui.set_status(
            "Modo de Desenho (Polígono): Clique para adicionar pontos, "
            "clique duplo para finalizar. Ctrl+Z para desfazer."
        )

    def stop_drawing(self) -> None:
        """Deactivates any drawing mode and unbinds all associated events."""
        # Destroy the instruction label if it exists
        if self.gui.drawing_instruction_label:
            self.gui.drawing_instruction_label.destroy()
            self.gui.drawing_instruction_label = None

        # Destroy floating drawing buttons if they exist
        if self.gui._drawing_buttons_frame:
            self.gui._drawing_buttons_frame.destroy()
            self.gui._drawing_buttons_frame = None

        self.gui.drawing_state_manager.mode = None
        self.gui.drawing_state_manager.drawing_type = None

        self.canvas_manager.event_handler.unbind_drawing_events()

        canvas = self.canvas_manager._get_canvas()
        if canvas:
            canvas.delete("elastic_line")
            canvas.delete("drawing_aid")  # Deletes both vertices and fixed lines
            canvas.delete("snap_indicator")  # Clear snap indicators

        # Clear coordinate lists
        self.gui.drawing_state_manager.clear_points()

        self.gui.set_status("Pronto.")

    def handle_vertex_drag(self, event):
        """Pass-through for event handling (API compatibility)."""
        return self.canvas_manager.event_handler.on_handle_drag(event)

    def handle_canvas_click(self, event):
        """Pass-through for event handling (API compatibility)."""
        return self.canvas_manager.event_handler.on_canvas_click(event)

    def start_main_arena_drawing(self) -> None:
        """Start drawing the main arena polygon."""
        if self.gui.analysis_active:
            self.gui.show_warning(
                "Análise em Progresso",
                "Não é possível editar zonas durante a análise de vídeo.",
            )
            return

        self.gui.drawing_state_manager.drawing_type = "arena"
        self.start_polygon_drawing()

        # Show aquarium indicator if in multi-aquarium mode
        zone_controls = self.gui.zone_controls
        if zone_controls and zone_controls.aquarium_count_var.get() == 2:
            active_id = zone_controls.active_aquarium_var.get()
            self.canvas_manager.multi_aquarium._show_aquarium_indicator(
                f"Desenhando: Aquário {active_id + 1} de 2"
            )

    def start_roi_drawing(self) -> None:
        """Start drawing an ROI polygon."""
        if self.gui.analysis_active:
            self.gui.show_warning(
                "Análise em Progresso",
                "Não é possível editar zonas durante a análise de vídeo.",
            )
            return

        main_arena = self.gui._get_zone_data_for_active_context().polygon
        if not main_arena:
            self.gui.show_error(
                "Erro",
                "Por favor, defina o 'Polígono Principal' primeiro antes de "
                "adicionar Áreas de Interesse.",
            )
            return
        self.gui.drawing_state_manager.drawing_type = "roi"
        self.start_polygon_drawing()

    def start_circle_drawing(self) -> None:
        """Activates circle drawing mode."""
        self.stop_drawing()
        self.gui.drawing_state_manager.mode = "circle"
        self.gui.current_circle_center = None
        canvas = self.canvas_manager._get_canvas()
        if canvas:
            canvas.config(cursor="crosshair")

            canvas.bind("<ButtonPress-1>", self.on_canvas_press_circle)
            canvas.bind("<B1-Motion>", self.on_canvas_drag_circle)
            canvas.bind("<ButtonRelease-1>", self.on_canvas_release_circle)
        self.gui.set_status("Modo de Desenho (Círculo): Clique e arraste para definir o raio.")

    def on_canvas_press_circle(self, event) -> None:
        """Handle mouse press during circle drawing."""
        if self.gui.drawing_state_manager.mode != "circle":
            return
        self.gui.current_circle_center = (event.x, event.y)

    def on_canvas_drag_circle(self, event) -> None:
        """Handle mouse drag during circle drawing."""
        if self.gui.drawing_state_manager.mode != "circle" or not self.gui.current_circle_center:
            return

        canvas = self.canvas_manager._get_canvas()
        if canvas:
            canvas.delete("elastic_line")
            cx, cy = self.gui.current_circle_center
            radius = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5
            canvas.create_oval(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                outline="#DAA520",
                dash=(4, 4),
                tags="elastic_line",
            )

    def on_canvas_release_circle(self, event) -> None:
        """Handle mouse release to finalize circle drawing."""
        if self.gui.drawing_state_manager.mode != "circle" or not self.gui.current_circle_center:
            return

        cx, cy = self.gui.current_circle_center
        radius = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5

        if radius < 2:
            self.stop_drawing()
            return

        roi_name = self.gui.ask_string(
            "Nome da ROI",
            "Digite um nome para esta nova Região de Interesse (Círculo):",
        )
        if not roi_name:
            self.stop_drawing()
            return

        # Fallback for arena selector if not present
        current_arena_id = "arena_1"
        if hasattr(self.gui, "arena_selector_var"):
            current_arena_id = self.gui.arena_selector_var.get() or "arena_1"

        new_roi = {
            "name": roi_name,
            "type": "circle",
            "coords": (cx, cy, radius),
        }
        self.gui.roi_data.setdefault(current_arena_id, []).append(new_roi)

        canvas = self.canvas_manager._get_canvas()
        if canvas:
            canvas.create_oval(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                outline="blue",
                fill="#008B8B",
                stipple="gray25",
                width=2,
            )

        if (
            hasattr(self.gui, "zone_controls")
            and self.gui.zone_controls
            and self.gui.zone_controls.zone_listbox
        ):
            self.gui.zone_controls.zone_listbox.insert("", "end", values=(roi_name,))
        elif hasattr(self.gui, "roi_listbox") and self.gui.roi_listbox:
            self.gui.roi_listbox.insert("", "end", values=(roi_name,))

        self.stop_drawing()

    # -------------------------------------------------------------------------
    # Arena/ROI Save, Discard, Clear, Edit
    # -------------------------------------------------------------------------

    def edit_selected_zone_vertices(self) -> None:
        """Enable interactive editing of the selected zone's vertices.

        Note: This involves business logic AND UI interaction, so it stays in
        ZoneEditor but delegates drawing to Renderer and events to EventHandler.
        """
        listbox = self.gui.zone_controls.zone_listbox if self.gui.zone_controls else None
        if not listbox:
            return

        selected = listbox.selection()
        if not selected:
            return

        item = listbox.item(selected[0])
        zone_name = item["values"][0]

        # Check if we are already in drawing mode
        if self.gui.drawing_state_manager.mode is not None:
            self.gui.show_warning(
                "Modo de Desenho Ativo",
                "Finalize o desenho atual antes de editar vértices de outra zona.",
            )
            return

        zone_data = self.gui._get_zone_data_for_active_context()

        if "Arena Principal" in zone_name:
            # Edit main arena
            if not zone_data.polygon:
                self.gui.show_warning("Erro", "Arena principal não encontrada.")
                return

            # Convert polygon to the format expected by setup_interactive_polygon
            polygon_points = np.array(zone_data.polygon)

            # NEW PATH - Event-Driven Architecture v4.0
            if self.canvas_manager.event_bus_v2:
                self.canvas_manager.event_bus_v2.publish(
                    Event(
                        type=UIEvents.POLYGON_EDIT_REQUESTED,
                        data={"polygon": polygon_points},
                        source="CanvasManager.edit_selected_zone_vertices.arena",
                    )
                )
            else:
                # Fallback
                self.canvas_manager.setup_interactive_polygon(polygon_points)

            self.gui.current_editing_zone = "arena"
            self.gui.set_status("Editando vértices da arena principal. Arraste os pontos amarelos.")

            # Explicitly show buttons
            if hasattr(self.gui, "zone_controls") and self.gui.zone_controls:
                self.gui.zone_controls.show_interactive_buttons()

        else:
            # Edit ROI
            roi_name = zone_name.replace("📍 ", "")
            try:
                roi_index = zone_data.roi_names.index(roi_name)
                roi_polygon = zone_data.roi_polygons[roi_index]

                # Convert polygon to the format expected by
                # setup_interactive_polygon
                polygon_points = np.array(roi_polygon)

                # NEW PATH - Event-Driven Architecture v4.0
                if self.canvas_manager.event_bus_v2:
                    self.canvas_manager.event_bus_v2.publish(
                        Event(
                            type=UIEvents.POLYGON_EDIT_REQUESTED,
                            data={"polygon": polygon_points},
                            source=(f"CanvasManager.edit_selected_zone_vertices.roi.{roi_name}"),
                        )
                    )
                else:
                    # Fallback
                    self.canvas_manager.setup_interactive_polygon(polygon_points)

                self.gui.current_editing_zone = ("roi", roi_index, roi_name)
                self.gui.set_status(
                    f"Editando vértices da ROI '{roi_name}'. Arraste os pontos amarelos."
                )

                # Explicitly show buttons
                if hasattr(self.gui, "zone_controls") and self.gui.zone_controls:
                    self.gui.zone_controls.show_interactive_buttons()

            except (ValueError, IndexError):
                self.gui.show_error("Erro", f"ROI '{roi_name}' não encontrada.")
                return

    def save_arena(self) -> None:
        """Save the edited polygon."""
        # Check for multi-aquarium mode first
        zone_controls = getattr(self.gui, "zone_controls", None)
        if (
            self.canvas_manager.current_editing_zone == "arena"
            and zone_controls
            and zone_controls.aquarium_count_var.get() == 2
        ):
            active_id = zone_controls.active_aquarium_var.get()
            video_path = self.gui.controller.project_manager.get_active_zone_video()

            # Get existing multi-aquarium data
            pm = self.gui.controller.project_manager
            multi_data = pm.get_multi_aquarium_zone_data(video_path)

            if multi_data:
                # Update specific aquarium
                aquarium = multi_data.get_aquarium(active_id)
                if aquarium:
                    aquarium.polygon = self.gui.edited_polygon_points

                    # Save updated multi-aquarium data
                    self.gui.controller.project_manager.save_multi_aquarium_zone_data(
                        video_path, multi_data
                    )

                    status_message = f"Arena do Aquário {active_id + 1} salva com sucesso."
                    self.gui.set_status(status_message)

                    # Auto-advance to next aquarium if available
                    next_id = active_id + 1
                    if next_id < zone_controls.aquarium_count_var.get():
                        self.gui.show_info(
                            "Próximo Aquário",
                            f"Arena do Aquário {active_id + 1} salva.\n"
                            f"Agora desenhe a arena do Aquário {next_id + 1}.",
                        )
                        zone_controls.set_active_aquarium(next_id)
                        self.start_main_arena_drawing()
                    else:
                        self.gui.show_info("Concluído", "Todas as arenas foram definidas.")

                    # Refresh UI
                    self.clear_interactive_polygon()
                    self.canvas_manager.redraw_zones_from_project_data()

                    if self.canvas_manager.event_bus_v2:
                        # Emit ZONES_UPDATED for zone listbox refresh
                        self.canvas_manager.event_bus_v2.publish(
                            Event(
                                type=UIEvents.ZONES_UPDATED,
                                data={"zone_data": None},
                                source="CanvasManager.save_arena.multi_aquarium",
                            )
                        )
                        # Emit PROJECT_VIEWS_REFRESH to update VideoTree badges
                        self.canvas_manager.event_bus_v2.publish(
                            Event(
                                type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                                data={
                                    "reason": status_message,
                                    "append_summary": True,
                                },
                                source="CanvasManager.save_arena.multi_aquarium",
                            )
                        )
                        # Also emit VIDEO_TREE_REFRESH for immediate tree update
                        self.canvas_manager.event_bus_v2.publish(
                            Event(
                                type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                                data={"filter_text": None},
                                source="CanvasManager.save_arena.multi_aquarium",
                            )
                        )
                    return

        if self.canvas_manager.current_editing_zone == "arena":
            # Save main arena (Single Aquarium)
            self.gui.event_dispatcher.publish_event(
                Events.ZONE_SAVE_MANUAL_ARENA,
                {"polygon_points": self.gui.edited_polygon_points},
            )
            status_message = "Arena principal salva com sucesso."
            self.gui.set_status(status_message)
            self.update_roi_button_state()

            if self.canvas_manager.event_bus_v2:
                self.canvas_manager.event_bus_v2.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data={
                            "reason": status_message,
                            "append_summary": True,
                        },
                        source="CanvasManager.save_arena",
                    )
                )

        elif (
            isinstance(self.canvas_manager.current_editing_zone, tuple)
            and self.canvas_manager.current_editing_zone[0] == "roi"
        ):
            # Save ROI
            _, roi_index, roi_name = self.canvas_manager.current_editing_zone
            zone_data = self.gui._get_zone_data_for_active_context()

            # Update the ROI polygon
            zone_data.roi_polygons[roi_index] = self.gui.edited_polygon_points

            # Save to project
            self.gui.controller.project_manager.save_zone_data(zone_data)

            status_message = f"ROI '{roi_name}' salva com sucesso."
            self.gui.set_status(status_message)

            if self.canvas_manager.event_bus_v2:
                self.canvas_manager.event_bus_v2.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data={
                            "reason": status_message,
                            "append_summary": True,
                        },
                        source="CanvasManager.save_arena",
                    )
                )
        else:
            # Fallback
            self.gui.controller.save_manual_arena(self.gui.edited_polygon_points)
            status_message = "Zona salva com sucesso."
            self.gui.set_status(status_message)
            self.update_roi_button_state()

            if self.canvas_manager.event_bus_v2:
                self.canvas_manager.event_bus_v2.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data={
                            "reason": status_message,
                            "append_summary": True,
                        },
                        source="CanvasManager.save_arena",
                    )
                )

        self.clear_interactive_polygon()
        self.canvas_manager.redraw_zones_from_project_data()

        if self.canvas_manager.event_bus_v2:
            self.canvas_manager.event_bus_v2.publish(
                Event(
                    type=UIEvents.ZONES_UPDATED,
                    data={"zone_data": None},
                    source="CanvasManager.save_arena",
                )
            )

        # Check if we should prompt to add a second aquarium
        self.gui.root.after(
            100,
            self.canvas_manager.multi_aquarium._check_prompt_second_aquarium,
        )

    def discard_arena(self) -> None:
        """Discard the interactive polygon."""
        self.clear_interactive_polygon()
        if self.canvas_manager.current_editing_zone == "arena":
            self.gui.set_status("Edição da arena descartada.")
        elif (
            isinstance(self.canvas_manager.current_editing_zone, tuple)
            and self.canvas_manager.current_editing_zone[0] == "roi"
        ):
            _, _, roi_name = self.canvas_manager.current_editing_zone
            self.gui.set_status(f"Edição da ROI '{roi_name}' descartada.")
        else:
            self.gui.set_status("Edição descartada.")

        self.canvas_manager.redraw_zones_from_project_data()

    def clear_interactive_polygon(self) -> None:
        """Clear all interactive elements."""
        canvas = self.canvas_manager._get_canvas()
        if canvas:
            canvas.delete("interactive_polygon", "handle", "suggested_polygon")

        if hasattr(self.gui, "zone_controls") and self.gui.zone_controls:
            self.gui.zone_controls.hide_interactive_buttons()

        self.gui.interactive_polygon_item = None
        self.gui.polygon_handles = []
        self.gui.edited_polygon_points = []
        self.canvas_manager.dragged_handle_index = None
        self.canvas_manager.drag_offset = (0, 0)
        self.canvas_manager.current_editing_zone = None

    def update_roi_button_state(self) -> None:
        """Enable ROI button if arena exists."""
        zone_data = self.gui._get_zone_data_for_active_context()

        # Handle Multi-Aquarium Data
        from zebtrack.core.detector import MultiAquariumZoneData

        if isinstance(zone_data, MultiAquariumZoneData):
            zone_controls = getattr(self.gui, "zone_controls", None)
            if zone_controls:
                active_id = zone_controls.active_aquarium_var.get()
                zone_data = zone_data.to_zone_data(active_id)
            else:
                zone_data = zone_data.to_zone_data(0)

        widget = getattr(self.gui, "zone_controls", None)
        if widget:
            widget.set_draw_roi_enabled(bool(zone_data and zone_data.polygon))

    def remove_selected_roi(self) -> None:
        """Remove the currently selected ROI with confirmation."""
        controls = getattr(self.gui, "zone_controls", None)
        if not controls or not controls.zone_listbox:
            return

        selected = controls.zone_listbox.selection()
        if not selected:
            return

        iid = selected[0]

        # Check if it's an ROI based on ID pattern "roi_{index}"
        if not iid.startswith("roi_"):
            return

        zone_data = self.gui._get_zone_data_for_active_context()

        try:
            # Extract index from IID (e.g. "roi_0" -> 0)
            idx = int(iid.split("_")[1])

            # Verify index validity
            if idx < 0 or idx >= len(zone_data.roi_names):
                self.gui.show_error("Erro", "Índice da ROI inválido ou desincronizado.")
                return

            roi_name = zone_data.roi_names[idx]

            # Confirmation
            confirm = self.gui.dialog_manager.confirm_remove_roi(roi_name)

            if confirm:
                # Remove from all lists using the index
                zone_data.roi_names.pop(idx)
                if idx < len(zone_data.roi_polygons):
                    zone_data.roi_polygons.pop(idx)
                if idx < len(zone_data.roi_colors):
                    zone_data.roi_colors.pop(idx)

                # Persist removals
                # Fix for single video workflow: do not persist if no project
                should_persist = bool(self.gui.controller.project_manager.project_path)
                self.gui.controller.project_manager.save_zone_data(
                    zone_data, persist=should_persist
                )

                # Update view
                self.canvas_manager.redraw_zones_from_project_data()

                status_message = f"ROI '{roi_name}' removida com sucesso."
                self.gui.set_status(status_message)
                self.gui.show_info("Sucesso", status_message)

                # Refresh project views
                if self.canvas_manager.event_bus_v2:
                    self.canvas_manager.event_bus_v2.publish(
                        Event(
                            type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                            data={
                                "reason": status_message,
                                "append_summary": True,
                            },
                            source="CanvasManager.remove_selected_roi",
                        )
                    )
                    self.canvas_manager.event_bus_v2.publish(
                        Event(
                            type=UIEvents.ZONES_UPDATED,
                            data={"zone_data": None},
                            source="CanvasManager.remove_selected_roi",
                        )
                    )

        except (ValueError, IndexError, AttributeError) as e:
            log.error("canvas_manager.remove_roi.error", error=str(e))
            self.gui.show_error("Erro", f"Falha ao remover ROI: {e}")

    # -------------------------------------------------------------------------
    # Color Mapping Utilities
    # -------------------------------------------------------------------------

    def _get_color_name_from_bgr(self, bgr: tuple) -> str:
        """Convert BGR tuple to Portuguese color name.

        Args:
            bgr: BGR color tuple (B, G, R)

        Returns:
            Portuguese color name or hex code if not found
        """
        # Normalize to tuple of ints
        # Explicitly construct tuple of length 3 to satisfy dict key type
        bgr_tuple: tuple[int, int, int] = (
            int(bgr[0]),
            int(bgr[1]),
            int(bgr[2]),
        )
        if bgr_tuple in self._BGR_COLOR_MAP:
            return self._BGR_COLOR_MAP[bgr_tuple]
        # Fallback to hex code if color not in standard palette
        return f"#{bgr_tuple[2]:02x}{bgr_tuple[1]:02x}{bgr_tuple[0]:02x}"

    # -------------------------------------------------------------------------
    # Zone Copy/Paste/Delete Operations
    # -------------------------------------------------------------------------

    def copy_zones_from_video(self, video_path: str | None) -> None:
        """Copy zones from the specified video to clipboard.

        Args:
            video_path: Path to the video to copy zones from
        """
        if not video_path:
            self.gui.set_status("Nenhum vídeo selecionado para copiar zonas.")
            return

        # Get project manager
        project_manager = getattr(self.gui, "project_manager", None)
        if not project_manager:
            self.gui.set_status("Gerenciador de projeto não disponível.")
            return

        # Get zone data for the video
        zone_data = project_manager.get_zone_data(video_path)
        if not zone_data or not zone_data.polygon:
            self.gui.set_status("Nenhuma zona encontrada para copiar.")
            return

        # Store in clipboard
        self._zone_clipboard = {
            "polygon": zone_data.polygon,
            "roi_polygons": zone_data.roi_polygons,
            "roi_colors": zone_data.roi_colors,
            "roi_names": zone_data.roi_names,
        }

        roi_count = len(zone_data.roi_polygons) if zone_data.roi_polygons else 0
        self.gui.set_status(f"Zonas copiadas: 1 arena + {roi_count} ROI(s).")
        log.info(
            "canvas_manager.copy_zones.success",
            video_path=video_path,
            roi_count=roi_count,
        )

    def paste_zones_to_video(self, video_path: str | None) -> None:
        """Paste zones from clipboard to the specified video.

        Args:
            video_path: Path to the video to paste zones to
        """
        if not video_path:
            self.gui.set_status("Nenhum vídeo selecionado para colar zonas.")
            return

        if not self._zone_clipboard:
            self.gui.set_status("Nenhuma zona na área de transferência.")
            return

        # Get project manager
        project_manager = getattr(self.gui, "project_manager", None)
        if not project_manager:
            self.gui.set_status("Gerenciador de projeto não disponível.")
            return

        # Get or create zone data for target video
        zone_data = project_manager.get_zone_data(video_path)
        if zone_data is None:
            from zebtrack.core.project_manager import ZoneData

            zone_data = ZoneData()

        # Paste the zones
        zone_data.polygon = self._zone_clipboard.get("polygon", [])
        zone_data.roi_polygons = self._zone_clipboard.get("roi_polygons", [])
        zone_data.roi_colors = self._zone_clipboard.get("roi_colors", [])
        zone_data.roi_names = self._zone_clipboard.get("roi_names", [])

        # Save to project
        project_manager.save_zone_data(zone_data, video_path)

        roi_count = len(zone_data.roi_polygons) if zone_data.roi_polygons else 0
        self.gui.set_status(f"Zonas coladas: 1 arena + {roi_count} ROI(s).")
        log.info(
            "canvas_manager.paste_zones.success",
            video_path=video_path,
            roi_count=roi_count,
        )

        # Refresh display if this is the current video
        self.canvas_manager.redraw_zones_from_project_data()
        self.update_zone_listbox()

        # Refresh video tree to update status icons
        if self.canvas_manager.event_bus_v2:
            self.canvas_manager.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data={"filter_text": None},
                    source="CanvasManager.paste_zones_to_video",
                )
            )

    def delete_zones_from_video(self, video_path: str | None) -> None:
        """Delete all zones from the specified video.

        Args:
            video_path: Path to the video to delete zones from
        """
        if not video_path:
            self.gui.set_status("Nenhum vídeo selecionado para excluir zonas.")
            return

        # Get project manager
        project_manager = getattr(self.gui, "project_manager", None)
        if not project_manager:
            self.gui.set_status("Gerenciador de projeto não disponível.")
            return

        # Get zone data
        zone_data = project_manager.get_zone_data(video_path)
        if not zone_data or not zone_data.polygon:
            self.gui.set_status("Nenhuma zona para excluir.")
            return

        # Clear the zones
        from zebtrack.core.project_manager import ZoneData

        project_manager.save_zone_data(ZoneData(), video_path)

        self.gui.set_status("Zonas excluídas com sucesso.")
        log.info("canvas_manager.delete_zones.success", video_path=video_path)

        # Refresh display
        self.canvas_manager.redraw_zones_from_project_data()
        self.update_zone_listbox()

        # Refresh video tree to update status icons
        if self.canvas_manager.event_bus_v2:
            self.canvas_manager.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data={"filter_text": None},
                    source="CanvasManager.delete_zones_from_video",
                )
            )

    # -------------------------------------------------------------------------
    # Geotaxis Visualization
    # -------------------------------------------------------------------------

    def toggle_geotaxis_visualization(self, show: bool) -> None:
        """Toggle visualization of geotaxis zones."""
        self.canvas_manager.show_geotaxis_zones = show
        self.canvas_manager.redraw_zones_from_project_data()
        log.info("canvas_manager.geotaxis_viz.toggled", show=show)

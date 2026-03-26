"""Zone and canvas widget builders."""

from __future__ import annotations

import tkinter as tk
from tkinter import Canvas, ttk

import structlog

from zebtrack.ui.builders.button_factory import ButtonFactory
from zebtrack.ui.builders.panel_builder import PanelBuilder
from zebtrack.ui.builders.zone_control_builder import ZoneControlBuilder

log = structlog.get_logger()


class ZoneWidgetsBuilder:
    """Builder for zone, canvas, and drawing-related widgets."""

    def __init__(self, gui, common_builder) -> None:
        self.gui = gui
        self.common = common_builder

    def create_zone_summary_cards_section(self) -> None:
        """Renderiza os cartões com indicadores numéricos da etapa de zonas."""
        if not getattr(self.gui, "zone_controls_frame", None):
            return

        if self.gui.zone_summary_frame and self.gui.zone_summary_frame.winfo_exists():
            try:
                self.gui.zone_summary_frame.destroy()
            except tk.TclError:
                log.debug("widget_factory.zone_summary_destroy.suppressed", exc_info=True)

        self.gui.zone_summary_frame, self.gui.zone_summary_cards = (
            PanelBuilder.create_zone_summary_cards(
                self.gui.zone_controls_frame, self.common.get_zone_summary_helper_text()
            )
        )

        if hasattr(self.gui, "video_selector_manager"):
            self.gui.video_selector_manager.update_zone_summary_cards()

    def create_drawing_buttons(self) -> None:
        """Create floating undo/redo buttons over the canvas."""
        if self.gui._drawing_buttons_frame:
            self.gui._drawing_buttons_frame.destroy()

        def _perform_undo():
            if self.gui.drawing_state_manager.undo():
                self.gui.canvas_manager.renderer.redraw_polygon_in_progress()

        def _perform_redo():
            if self.gui.drawing_state_manager.redo():
                self.gui.canvas_manager.renderer.redraw_polygon_in_progress()

        commands = {
            "undo": _perform_undo,
            "redo": _perform_redo,
        }

        parent = (
            self.gui.video_display if hasattr(self.gui, "video_display") else self.gui.viz_frame
        )

        self.gui._drawing_buttons_frame = ButtonFactory.create_floating_drawing_buttons(
            parent, commands
        )

        self.gui._drawing_buttons_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def on_frame_configure(self, event=None) -> None:
        """Update scroll region when frame size changes."""
        self.gui.controls_canvas.configure(scrollregion=self.gui.controls_canvas.bbox("all"))

    def on_canvas_configure_scroll(self, event=None) -> None:
        """Update frame width when canvas size changes."""
        canvas_width = event.width if event else self.gui.controls_canvas.winfo_width()
        self.gui.controls_canvas.itemconfig(self.gui.controls_canvas_window, width=canvas_width)

    def on_canvas_configure(self, event=None) -> None:
        """Handle canvas resize events to properly scale and center the image."""
        if event and event.widget != self.gui.video_display.canvas:
            return

        if not hasattr(self.gui, "_raw_bg_image") or not self.gui._raw_bg_image:
            if hasattr(self.gui, "_original_image") and self.gui._original_image:
                self.gui._raw_bg_image = self.gui._original_image
            else:
                return

        canvas_width = self.gui.video_display.canvas.winfo_width()
        canvas_height = self.gui.video_display.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            return

        try:
            self.gui.canvas_manager._draw_bg_image_to_canvas()
            if hasattr(self.gui, "controller") and self.gui.controller:
                self.gui.canvas_manager.redraw_zones_from_project_data()
        except (tk.TclError, AttributeError) as e:
            log.warning("gui.canvas.configure_error", error=str(e))

    def create_scrollable_controls_frame(self, parent) -> None:
        """Create a scrollable frame for the zone controls."""
        self.gui.controls_canvas = Canvas(parent, highlightthickness=0)
        self.gui.controls_scrollbar = ttk.Scrollbar(
            parent, orient="vertical", command=self.gui.controls_canvas.yview
        )

        self.gui.zone_controls_frame = ttk.Frame(self.gui.controls_canvas)
        self.gui.fixed_button_frame = ttk.Frame(parent)

        self.gui.controls_canvas.configure(yscrollcommand=self.gui.controls_scrollbar.set)

        self.gui.controls_scrollbar.pack(side="right", fill="y")
        self.gui.fixed_button_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        self.gui.controls_canvas.pack(side="left", fill="both", expand=True)

        self.gui.controls_canvas_window = self.gui.controls_canvas.create_window(
            0, 0, anchor="nw", window=self.gui.zone_controls_frame
        )

        self.gui.zone_controls_frame.bind("<Configure>", self.on_frame_configure)
        self.gui.controls_canvas.bind("<Configure>", self.on_canvas_configure_scroll)

    # ------------------------------------------------------------------
    # Zone controls
    # ------------------------------------------------------------------

    def create_zone_control_widgets(self) -> None:
        """Create all zone control widgets in the scrollable frame."""
        builder = ZoneControlBuilder(self.gui)
        builder.create_zone_control_widgets()

    def create_template_rois(self) -> None:
        """Open a dialog to create ROIs from a template."""
        import numpy as np

        from zebtrack.ui.dialogs.template_dialog import TemplateDialog

        current_arena_id = self.gui.arena_selector_var.get()
        if not current_arena_id:
            self.gui.dialog_manager.show_error("Erro", "Selecione um aquário ativo primeiro.")
            return

        arena_data = self.gui.controller.project_manager.get_zone_data()
        if not arena_data or not arena_data.polygon:
            self.gui.dialog_manager.show_error(
                "Erro", "Não foi possível obter os dados do polígono do aquário."
            )
            return

        poly_points = np.array(arena_data.polygon)
        x_min, y_min = poly_points.min(axis=0)
        x_max, y_max = poly_points.max(axis=0)
        width = x_max - x_min
        height = y_max - y_min

        dialog = TemplateDialog(self.gui.root)
        if not dialog.result:
            return

        rois_to_add = []
        template = dialog.result
        if template["type"] == "vertical":
            lanes_value = template.get("lanes")
            lanes = int(lanes_value) if isinstance(lanes_value, int | float | str) else 0
            lane_width = width / lanes if lanes else width
            for i in range(lanes):
                x1 = x_min + i * lane_width
                x2 = x1 + lane_width
                coords = [(x1, y_min), (x2, y_min), (x2, y_max), (x1, y_max)]
                rois_to_add.append({"name": f"V_Lane_{i + 1}", "type": "polygon", "coords": coords})
        elif template["type"] == "horizontal":
            lanes_value = template.get("lanes")
            lanes = int(lanes_value) if isinstance(lanes_value, int | float | str) else 0
            lane_height = height / lanes if lanes else height
            for i in range(lanes):
                y1 = y_min + i * lane_height
                y2 = y1 + lane_height
                coords = [(x_min, y1), (x_max, y1), (x_max, y2), (x_min, y2)]
                rois_to_add.append({"name": f"H_Lane_{i + 1}", "type": "polygon", "coords": coords})
        elif template["type"] == "grid":
            cols_value = template.get("cols")
            rows_value = template.get("rows")
            cols = int(cols_value) if isinstance(cols_value, int | float | str) else 0
            rows = int(rows_value) if isinstance(rows_value, int | float | str) else 0
            col_width = width / cols if cols else width
            row_height = height / rows if rows else height
            for r in range(rows):
                for c in range(cols):
                    x1 = x_min + c * col_width
                    y1 = y_min + r * row_height
                    x2 = x1 + col_width
                    y2 = y1 + row_height
                    coords = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                    rois_to_add.append(
                        {"name": f"Grid_{r + 1}-{c + 1}", "type": "polygon", "coords": coords}
                    )

        self.gui.roi_data.setdefault(current_arena_id, []).extend(rois_to_add)
        self.gui.canvas_manager.update_zone_listbox()

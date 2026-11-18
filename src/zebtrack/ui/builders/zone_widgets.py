"""Zone and canvas widget builders."""

from __future__ import annotations

import tkinter as tk

import structlog

from zebtrack.ui.builders.button_factory import ButtonFactory

log = structlog.get_logger()


class ZoneWidgetsBuilder:
    """Builder for zone, canvas, and drawing-related widgets."""

    def __init__(self, gui, common_builder) -> None:
        self.gui = gui
        self.common = common_builder

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

    # ------------------------------------------------------------------
    # Zone controls
    # ------------------------------------------------------------------

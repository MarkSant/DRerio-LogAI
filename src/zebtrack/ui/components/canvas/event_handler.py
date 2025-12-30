"""
Canvas Event Handler Component.

Handles mouse and keyboard events on the canvas, including drawing interactions,
polygon editing, and navigation.
"""

import structlog

from zebtrack.utils.geometry_service import GeometryService

log = structlog.get_logger()


class CanvasEventHandler:
    """Handles canvas input events."""

    # Debounce interval in milliseconds for motion events to reduce flickering
    MOTION_DEBOUNCE_MS = 16  # ~60fps

    def __init__(self, canvas_manager):
        """Initialize CanvasEventHandler.

        Args:
            canvas_manager: Reference to parent CanvasManager
        """
        self.manager = canvas_manager
        self.gui = canvas_manager.gui
        self._motion_debounce_id = None

    def bind_drawing_events(self):
        """Bind events for polygon drawing."""
        canvas = self.gui.video_display.canvas
        canvas.config(cursor="crosshair")
        canvas.bind("<Button-1>", self.on_canvas_click)
        canvas.bind("<B1-Motion>", self.on_vertex_drag_motion)
        canvas.bind("<ButtonRelease-1>", self.on_vertex_drag_end)
        canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        canvas.bind("<Motion>", self.on_canvas_motion)

        # Keyboard shortcuts
        canvas.bind("<Control-z>", self.on_drawing_undo)
        canvas.bind("<Control-y>", self.on_drawing_redo)
        canvas.bind("<Control-Shift-Z>", self.on_drawing_redo)
        canvas.focus_set()

    def unbind_drawing_events(self):
        """Unbind drawing events."""
        canvas = self.gui.video_display.canvas
        canvas.config(cursor="")
        canvas.unbind("<Button-1>")
        canvas.unbind("<Double-Button-1>")
        canvas.unbind("<Motion>")
        canvas.unbind("<ButtonPress-1>")
        canvas.unbind("<B1-Motion>")
        canvas.unbind("<ButtonRelease-1>")
        canvas.unbind("<Control-z>")
        canvas.unbind("<Control-y>")
        canvas.unbind("<Control-Shift-Z>")

    def on_handle_press(self, event, handle_index):
        """Record which handle is being dragged and initial offset."""
        self.gui._dragged_handle_index = handle_index
        self.gui._drag_start_mouse = (float(event.x), float(event.y))

        video_point = self.gui.edited_polygon_points[handle_index]
        canvas_point = self.manager._video_to_canvas(video_point[0], video_point[1])
        self.gui._drag_start_handle = canvas_point

        self.gui._drag_offset = (canvas_point[0] - event.x, canvas_point[1] - event.y)

        self.gui.video_display.canvas.bind("<B1-Motion>", self.on_handle_drag_global)
        self.gui.video_display.canvas.bind("<ButtonRelease-1>", self.on_handle_release_global)

    def on_handle_drag(self, event):
        """Update polygon point and redraw."""
        if self.gui._dragged_handle_index is None:
            return

        canvas_x = float(event.x) + self.gui._drag_offset[0]
        canvas_y = float(event.y) + self.gui._drag_offset[1]

        snapped_point = self.manager.apply_snapping(
            canvas_x, canvas_y, exclude_current_polygon=True
        )
        if snapped_point:
            canvas_x, canvas_y = snapped_point

        if (
            isinstance(self.gui.current_editing_zone, tuple)
            and self.gui.current_editing_zone[0] == "roi"
        ):
            main_arena_poly = self.gui._get_zone_data_for_active_context().polygon
            if main_arena_poly:
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self.manager._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                canvas_x, canvas_y = GeometryService.clamp_point_to_polygon(
                    (canvas_x, canvas_y), canvas_arena_poly
                )

        canvas_width = self.gui.video_display.canvas.winfo_width() or 800
        canvas_height = self.gui.video_display.canvas.winfo_height() or 600
        canvas_x = max(0, min(canvas_x, canvas_width))
        canvas_y = max(0, min(canvas_y, canvas_height))

        video_point = self.manager._canvas_to_video(canvas_x, canvas_y)
        self.gui.edited_polygon_points[self.gui._dragged_handle_index] = [
            video_point[0],
            video_point[1],
        ]

        self.manager.renderer.draw_interactive_polygon()

    def on_handle_drag_global(self, event):
        """Global drag handler."""
        self.on_handle_drag(event)

    def on_handle_release(self, event):
        """Finalize drag operation."""
        self._handle_release_common()

    def on_handle_release_global(self, event):
        """Global release handler."""
        self.gui.video_display.canvas.unbind("<B1-Motion>")
        self.gui.video_display.canvas.unbind("<ButtonRelease-1>")
        self._handle_release_common()

    def _handle_release_common(self):
        """Execute common release logic."""
        self.gui._dragged_handle_index = None
        self.gui._drag_offset = (0, 0)

    def on_canvas_click(self, event):
        """Handle single clicks during polygon drawing."""
        if self.gui.drawing_state_manager.mode != "polygon":
            return

        canvas_x = float(event.x)
        canvas_y = float(event.y)

        if self.gui.drawing_state_manager.has_points():
            for i, (vx, vy) in enumerate(self.gui.drawing_state_manager.current_points):
                dist = ((canvas_x - vx) ** 2 + (canvas_y - vy) ** 2) ** 0.5
                if dist <= self.gui.drawing_state_manager.vertex_hover_tolerance:
                    self.gui.drawing_state_manager.dragging_vertex_index = i
                    self.gui.video_display.canvas.config(cursor="hand2")
                    return

        snapped_point = self.manager.apply_snapping(canvas_x, canvas_y)
        if snapped_point:
            canvas_x, canvas_y = snapped_point

        if self.gui.drawing_state_manager.drawing_type == "roi":
            main_arena_poly = self.gui._get_zone_data_for_active_context().polygon
            if main_arena_poly:
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self.manager._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                canvas_x, canvas_y = GeometryService.clamp_point_to_polygon(
                    (canvas_x, canvas_y), canvas_arena_poly
                )

        canvas_point = (canvas_x, canvas_y)
        video_point = self.manager._canvas_to_video(canvas_x, canvas_y)

        self.gui.drawing_state_manager.add_point(canvas_point, video_point, canvas_point)

        self.gui.video_display.canvas.create_oval(
            canvas_x - 2,
            canvas_y - 2,
            canvas_x + 2,
            canvas_y + 2,
            fill="red",
            outline="red",
            tags=("temp_vertex", "drawing_aid"),
        )

        current_points = self.gui.drawing_state_manager.current_points
        if len(current_points) > 1:
            p1 = current_points[-2]
            p2 = current_points[-1]
            self.gui.video_display.canvas.create_line(
                p1[0], p1[1], p2[0], p2[1], fill="#008B8B", width=2, tags="drawing_aid"
            )

    def on_vertex_drag_motion(self, event):
        """Handle mouse motion while dragging a vertex."""
        if self.gui.drawing_state_manager.dragging_vertex_index is None:
            return

        canvas_x = float(event.x)
        canvas_y = float(event.y)

        if self.gui.drawing_state_manager.drawing_type == "roi":
            main_arena_poly = self.gui._get_zone_data_for_active_context().polygon
            if main_arena_poly:
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self.manager._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                canvas_x, canvas_y = GeometryService.clamp_point_to_polygon(
                    (canvas_x, canvas_y), canvas_arena_poly
                )

        idx = self.gui.drawing_state_manager.dragging_vertex_index
        video_pt = self.manager._canvas_to_video(canvas_x, canvas_y)

        self.gui.drawing_state_manager.current_points[idx] = (canvas_x, canvas_y)
        self.gui.drawing_state_manager.canvas_points[idx] = (canvas_x, canvas_y)
        self.gui.drawing_state_manager.video_points[idx] = video_pt

        self.manager.renderer.redraw_polygon_in_progress()

    def on_vertex_drag_end(self, event):
        """Handle mouse release after dragging a vertex."""
        if self.gui.drawing_state_manager.dragging_vertex_index is not None:
            self.gui.drawing_state_manager.dragging_vertex_index = None
            self.gui.video_display.canvas.config(cursor="crosshair")

    def on_canvas_motion(self, event):
        """Handle mouse movement for drawing elastic lines with debounce to reduce flickering."""
        if self.gui.drawing_state_manager.mode != "polygon":
            return

        # Cancel any pending debounced motion update
        if self._motion_debounce_id is not None:
            try:
                self.gui.video_display.canvas.after_cancel(self._motion_debounce_id)
            except Exception:
                pass
            self._motion_debounce_id = None

        # Schedule the actual motion handling with debounce
        self._motion_debounce_id = self.gui.video_display.canvas.after(
            self.MOTION_DEBOUNCE_MS, lambda: self._handle_canvas_motion(event)
        )

    def _handle_canvas_motion(self, event):
        """Internal handler for canvas motion after debounce."""
        self._motion_debounce_id = None

        if self.gui.drawing_state_manager.mode != "polygon":
            return

        canvas = self.gui.video_display.canvas
        canvas.delete("elastic_line")
        canvas.delete("snap_indicator")

        # Check for snapping
        canvas_x = float(event.x)
        canvas_y = float(event.y)
        snapped_point = self.manager.apply_snapping(canvas_x, canvas_y)

        # Check if mouse is hovering over an existing vertex
        vertex_hover_index = None
        hover_color = "#008B8B"

        current_points = self.gui.drawing_state_manager.current_points

        if current_points:
            for i, (vx, vy) in enumerate(current_points):
                dist = ((canvas_x - vx) ** 2 + (canvas_y - vy) ** 2) ** 0.5
                if dist <= 10:
                    vertex_hover_index = i
                    hover_color = "orange"
                    display_x, display_y = vx, vy
                    break

        if vertex_hover_index is None:
            display_x = snapped_point[0] if snapped_point else canvas_x
            display_y = snapped_point[1] if snapped_point else canvas_y
        elif current_points:
            display_x, display_y = current_points[vertex_hover_index]
        else:
            display_x, display_y = canvas_x, canvas_y

        # When drawing ROI, clamp the display indicator within the arena
        if self.gui.drawing_state_manager.drawing_type == "roi":
            main_arena_poly = self.gui._get_zone_data_for_active_context().polygon
            if main_arena_poly:
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self.manager._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                canvas_x, canvas_y = GeometryService.clamp_point_to_polygon(
                    (display_x, display_y), canvas_arena_poly
                )
                display_x, display_y = canvas_x, canvas_y

        should_show_indicator = (
            snapped_point is not None
            or vertex_hover_index is not None
            or (
                self.gui.drawing_state_manager.drawing_type == "roi"
                and self.gui._get_zone_data_for_active_context().polygon
            )
        )

        if should_show_indicator:
            canvas.create_oval(
                display_x - 5,
                display_y - 5,
                display_x + 5,
                display_y + 5,
                outline=hover_color,
                width=2,
                tags="snap_indicator",
            )

        if not current_points:
            return

        last_point = current_points[-1]
        first_point = current_points[0]

        canvas.create_line(
            last_point[0],
            last_point[1],
            display_x,
            display_y,
            fill="#DAA520",
            dash=(4, 4),
            tags="elastic_line",
        )
        if len(current_points) > 1:
            canvas.create_line(
                display_x,
                display_y,
                first_point[0],
                first_point[1],
                fill="#DAA520",
                dash=(4, 4),
                tags="elastic_line",
            )

    def on_canvas_double_click(self, event):
        """Finalize the drawing of the polygon."""
        if (
            self.gui.drawing_state_manager.drawing_type is None
            and self.gui.drawing_state_manager.mode == "polygon"
        ):
            zone_data = self.gui._get_zone_data_for_active_context()
            if not zone_data.polygon:
                self.gui.drawing_state_manager.drawing_type = "arena"
            else:
                self.gui.drawing_state_manager.drawing_type = "roi"

        if self.gui.drawing_state_manager.mode != "polygon":
            return

        try:
            self.gui.video_display.canvas.delete("elastic_line")
            self.gui.video_display.canvas.delete("drawing_aid")

            video_points = self.gui.drawing_state_manager.video_points

            success = self.gui.polygon_drawing_service.complete_polygon(
                self.gui.drawing_state_manager.drawing_type, video_points, self.gui
            )

            if success:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                drawing_type = self.gui.drawing_state_manager.drawing_type
                status_message = f"✓ {drawing_type.title()} definida com sucesso!"
                self.gui.set_status(status_message)
                self.gui.show_info(
                    "Sucesso",
                    f"Zona criada com {len(video_points)} pontos.",
                )

                if self.manager.event_bus_v2:
                    self.manager.event_bus_v2.publish(
                        Event(
                            type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                            data={"reason": status_message, "append_summary": True},
                            source="CanvasEventHandler.on_canvas_double_click",
                        )
                    )

                self.manager.stop_drawing()

                # Prompt for second aquarium if drawing arena in single-aquarium mode
                if drawing_type == "arena":
                    self.gui.root.after(100, self.manager._check_prompt_second_aquarium)
            else:
                self.gui.set_status("❌ Erro ao salvar zona.")
                self.gui.show_error("Erro", "Não foi possível salvar a zona.")
                self.manager.stop_drawing()

        except Exception as e:
            self.gui.set_status("❌ Erro durante salvamento.")
            self.gui.show_error("Erro", str(e))
            self.manager.stop_drawing()

    def on_drawing_undo(self, event):
        """Undo last point added to polygon."""
        if (
            self.gui.drawing_state_manager.mode != "polygon"
            or not self.gui.drawing_state_manager.has_points()
        ):
            return "break"

        success = self.gui.drawing_state_manager.undo()

        if success:
            self.manager._redraw_polygon_in_progress()
            self.gui.set_status(
                f"Último ponto desfeito. Pontos atuais: {self.gui.drawing_state_manager.point_count()}"
            )

        return "break"

    def on_drawing_redo(self, event):
        """Redo last undone point."""
        if self.gui.drawing_state_manager.mode != "polygon":
            return "break"

        success = self.gui.drawing_state_manager.redo()

        if success:
            self.manager._redraw_polygon_in_progress()
            self.gui.set_status(
                f"Ponto restaurado. Pontos atuais: {self.gui.drawing_state_manager.point_count()}"
            )

        return "break"

"""Canvas management for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles canvas drawing, coordinate transformations, overlays, and rendering.
Delegates specific responsibilities to CanvasRenderer and CanvasEventHandler.
"""

import os

import cv2
import numpy as np
import structlog
import ttkbootstrap as ttk
from PIL import Image

from zebtrack.ui.components.canvas.event_handler import CanvasEventHandler
from zebtrack.ui.components.canvas.renderer import CanvasRenderer
from zebtrack.ui.events import Events
from zebtrack.utils.geometry_service import GeometryService

log = structlog.get_logger()


class CanvasManager:
    """Manages canvas operations, drawing, and coordinate transformations."""

    def __init__(self, gui, event_bus_v2=None):
        """Initialize CanvasManager.

        Args:
            gui: Reference to ApplicationGUI instance
            event_bus_v2: EventBusV2 instance for v4.0 Event-Driven Architecture (optional)
        """
        self.gui = gui
        self.event_bus_v2 = event_bus_v2
        # Transformation attributes
        self._bg_scale = None
        self._bg_offset = None
        self._bg_img_size = None
        self._raw_bg_image = None
        self._canvas_bg_image = None
        self._canvas_bg_position = None

        # Interactive editing state
        self.dragged_handle_index = None
        self.drag_offset = (0, 0)
        self.drag_start_mouse = (0, 0)
        self.drag_start_handle = (0, 0)
        self.current_editing_zone = None

        # Initialize sub-components
        self.renderer = CanvasRenderer(self)
        self.event_handler = CanvasEventHandler(self)

        # Subscribe to events if event bus is available
        if self.event_bus_v2:
            self._setup_event_subscriptions()

    def _setup_event_subscriptions(self):
        """Subscribe to Event Bus V2 events for v4.0 Event-Driven Architecture."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        # Subscribe to ZONES_UPDATED event (replaces direct gui.update_zone_listbox calls)
        self.event_bus_v2.subscribe(UIEvents.ZONES_UPDATED, self._on_zones_updated)

        # Subscribe to POLYGON_EDIT_REQUESTED event
        # (replaces direct gui.setup_interactive_polygon calls)
        self.event_bus_v2.subscribe(
            UIEvents.POLYGON_EDIT_REQUESTED, self._on_polygon_edit_requested
        )

        log.debug(
            "canvas_manager.event_subscriptions_setup",
            events=["ZONES_UPDATED", "POLYGON_EDIT_REQUESTED"],
        )

    def _on_zones_updated(self, data: dict):
        """Handle ZONES_UPDATED event.

        Args:
            data: Event payload containing zone_data
        """
        if not isinstance(data, dict):
            log.warning("canvas_manager._on_zones_updated.invalid_data_type",
                       data_type=type(data).__name__)
            return
        zone_data = data.get("zone_data")
        log.debug(
            "canvas_manager.zones_updated_event_received", has_zone_data=zone_data is not None
        )
        self.update_zone_listbox(zone_data)

    def _on_polygon_edit_requested(self, data: dict):
        """Handle POLYGON_EDIT_REQUESTED event.

        Args:
            data: Event payload containing:
                - polygon: np.ndarray of polygon points
        """
        if not isinstance(data, dict):
            log.warning("canvas_manager._on_polygon_edit_requested.invalid_data_type",
                       data_type=type(data).__name__)
            return
        polygon = data.get("polygon")
        if polygon is not None:
            self.setup_interactive_polygon(polygon)

    def setup_interactive_polygon(self, polygon: np.ndarray | list) -> None:
        """Set up interactive polygon editing.

        Args:
            polygon: Polygon points as numpy array or list of lists
        """
        # Convert numpy array to list of lists if needed
        if isinstance(polygon, np.ndarray):
            polygon_list = polygon.tolist()
        else:
            polygon_list = polygon

        # Populate gui.edited_polygon_points
        self.gui.edited_polygon_points = polygon_list

        # Draw the interactive polygon with handles
        self.renderer.draw_interactive_polygon()

        # Force a redraw after a short delay to ensure handles appear even if
        # conflicting events (like Treeview focus) clear the canvas or interfere
        self.gui.root.after(50, self.renderer.draw_interactive_polygon)

        # Show interactive buttons in ZoneControls
        if hasattr(self.gui, "zone_controls") and self.gui.zone_controls:
            self.gui.zone_controls.show_interactive_buttons()

        log.debug("canvas_manager.setup_interactive_polygon.complete", num_points=len(polygon_list))

    # ========== Coordinate Transformation Methods ==========

    def _canvas_to_video(self, canvas_x, canvas_y):
        """Convert canvas coordinates to video frame coordinates.

        Args:
            canvas_x: X coordinate in canvas space
            canvas_y: Y coordinate in canvas space

        Returns:
            tuple: (video_x, video_y) in video frame coordinates
        """
        if (
            not hasattr(self, "_bg_scale")
            or not hasattr(self, "_bg_offset")
            or self._bg_scale is None
            or self._bg_offset is None
            or self._bg_scale == 0
        ):
            # Fallback: return canvas coordinates if scaling info not available or scale is zero
            return (float(canvas_x), float(canvas_y))

        scale = self._bg_scale
        offset_x, offset_y = self._bg_offset

        # Convert canvas coordinates to video coordinates
        video_x = (canvas_x - offset_x) / scale
        video_y = (canvas_y - offset_y) / scale

        return (float(video_x), float(video_y))

    def _video_to_canvas(self, video_x, video_y):
        """Convert video frame coordinates to canvas coordinates.

        Args:
            video_x: X coordinate in video frame space
            video_y: Y coordinate in video frame space

        Returns:
            tuple: (canvas_x, canvas_y) in canvas coordinates
        """
        if (
            not hasattr(self, "_bg_scale")
            or not hasattr(self, "_bg_offset")
            or self._bg_scale is None
            or self._bg_offset is None
        ):
            # Fallback: return video coordinates if scaling info not available
            return (float(video_x), float(video_y))

        scale = self._bg_scale
        offset_x, offset_y = self._bg_offset

        # Convert video coordinates to canvas coordinates
        canvas_x = video_x * scale + offset_x
        canvas_y = video_y * scale + offset_y

        return (float(canvas_x), float(canvas_y))

    def _point_to_segment_distance(self, px, py, x1, y1, x2, y2):
        """Calculate the shortest distance from point to line segment.

        Calculates the shortest distance from point (px, py) to line segment
        (x1,y1)-(x2,y2).

        Args:
            px: X coordinate of point
            py: Y coordinate of point
            x1: X coordinate of segment start
            y1: Y coordinate of segment start
            x2: X coordinate of segment end
            y2: Y coordinate of segment end

        Returns:
            dict or None: {'distance': float, 'x': float, 'y': float} with the
                         closest point on segment, or None if projection falls
                         outside segment
        """
        # Vector from p1 to p2
        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            # Degenerate segment (single point)
            dist = np.sqrt((px - x1) ** 2 + (py - y1) ** 2)
            return {"distance": dist, "x": x1, "y": y1}

        # Parameter t for projection of point onto line
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)

        # Clamp t to [0, 1] to stay on segment
        t = max(0, min(1, t))

        # Closest point on segment
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        # Distance to closest point
        dist = np.sqrt((px - closest_x) ** 2 + (py - closest_y) ** 2)

        return {"distance": dist, "x": closest_x, "y": closest_y}

    # ========== Delegated Methods ==========

    def _draw_bg_image_to_canvas(self):
        """Draw the background image to canvas. Delegates to renderer."""
        self.renderer.draw_bg_image()

    def on_canvas_configure(self, event=None):
        """Handle canvas resize events. Delegates to renderer logic."""
        self.renderer.draw_bg_image()
        if hasattr(self.gui, "controller") and self.gui.controller:
            self.redraw_zones_from_project_data()

    def display_roi_video_frame(self, video_path):
        """Load the first frame of a video, display it on the canvas, and adjust window size.

        Args:
            video_path: Path to the video file

        This method:
        - Loads the first frame from the video
        - Adjusts the main window size proportionally
        - Displays the frame on the canvas with proper scaling
        """
        try:
            if not video_path or not os.path.exists(video_path):
                log.error(
                    "gui.display_roi_frame.invalid_path",
                    path=video_path,
                )
                self.gui.controller.project_manager.set_active_zone_video(None)
                self.gui.show_error(
                    "Erro",
                    "O vídeo selecionado não foi encontrado ou está inacessível.",
                )
                return

            self.gui.controller.project_manager.set_active_zone_video(video_path)
            self.gui._refresh_roi_templates()

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.gui.show_error("Erro", "Não foi possível abrir o vídeo.")
                return
            ret, frame = cap.read()
            cap.release()
            if not ret:
                self.gui.show_error("Erro", "Não foi possível ler um frame do vídeo.")
                return

            # Logic to display on the canvas
            h, w, _ = frame.shape
            # Adjust the main window to a proportional size
            screen_w = self.gui.root.winfo_screenwidth()
            screen_h = self.gui.root.winfo_screenheight()
            win_w = min(int(screen_w * 0.8), w + 400)  # Account for controls space
            win_h = min(int(screen_h * 0.8), h + 150)  # Account for window decorations

            # Import the utility function
            from zebtrack.ui.window_utils import set_geometry_if_not_maximized

            set_geometry_if_not_maximized(self.gui.root, f"{win_w}x{win_h}")
            self.gui.root.update_idletasks()

            # Convert the frame for display
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.gui._original_image = Image.fromarray(frame_rgb)
            # Also store as _raw_bg_image as mentioned in requirements
            self._raw_bg_image = self.gui._original_image

            # Wait for the canvas to be properly sized after geometry update
            self.gui.root.after(10, lambda: self._draw_bg_image_to_canvas())

        except Exception as e:
            self.gui.show_error("Erro ao Exibir Frame", str(e))

    def update_video_frame(self, frame: np.ndarray, detections: list | None = None) -> None:
        """Update the canvas with a raw video frame (numpy array).

        This method is called during video analysis to display frames.
        The frame already has overlays (arena, ROIs, bboxes) drawn by detector.draw_overlay().

        IMPORTANT: This should only display on the analysis tab widget, NOT on the zone canvas.
        The zone canvas should remain unchanged during analysis.

        Args:
            frame: The video frame as a numpy array (BGR format from OpenCV).
            detections: List of detections (not used - overlays already drawn on frame).
        """
        if frame is None:
            return

        try:
            # Convert the frame for display (BGR -> RGB)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)

            # ONLY display on Analysis Tab widget during analysis
            # Do NOT update zone canvas - it should remain showing the static zone drawing
            if self.gui.analysis_active and self.gui.analysis_display_widget:
                # Dynamic sizing
                target_w = 1280
                target_h = 720

                # Try to get current container size if available
                if self.gui.analysis_display_widget.video_container:
                    w = self.gui.analysis_display_widget.video_container.winfo_width()
                    h = self.gui.analysis_display_widget.video_container.winfo_height()
                    if w > 100 and h > 100:
                        target_w, target_h = w, h

                pil_image.thumbnail((target_w, target_h), Image.LANCZOS)
                self.gui.analysis_display_widget.update_frame(pil_image)
            # NOTE: We intentionally do NOT update the zone canvas here.
            # During analysis, the zone canvas should keep its static state.

        except Exception as e:
            log.error("canvas_manager.update_video_frame.error", error=str(e))

    def load_video_frame_to_canvas(self, video_path: str | None = None, frame_number: int = 0):
        """Load a video frame to the canvas.

        Args:
            video_path: Path to the video file (optional, will use pending/project video if None)
            frame_number: Frame number to load (default: 0)

        Returns:
            bool: True if frame was loaded successfully, False otherwise
        """
        if video_path is None:
            # Try to use pending video or from project
            has_pending = hasattr(self.gui, "pending_single_video_path")
            if has_pending and self.gui.pending_single_video_path:
                video_path = self.gui.pending_single_video_path
            elif self.gui.controller.project_manager.project_path:
                videos = self.gui.controller.project_manager.get_all_videos()
                if videos:
                    video_path = videos[0].get("path")

        if not video_path or not os.path.exists(video_path):
            log.error("gui.load_frame.no_video")
            self.gui.controller.project_manager.set_active_zone_video(None)
            return False

        try:
            self.gui.controller.project_manager.set_active_zone_video(video_path)

            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                return False

            # Convert frame and store original
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.gui._original_image = Image.fromarray(frame_rgb)
            # Also store as _raw_bg_image as mentioned in requirements
            self._raw_bg_image = self.gui._original_image

            # Display the image using proper canvas scaling
            self._draw_bg_image_to_canvas()

            log.info("gui.canvas.frame_loaded", video=video_path)
            return True

        except Exception as e:
            log.error("gui.load_frame.error", error=str(e))
            return False

    def _redraw_polygon_in_progress(self):
        """Redraw the polygon vertices and edges after undo/redo. Delegates to renderer."""
        self.renderer.redraw_polygon_in_progress()

    def redraw_zones_from_project_data(self, zone_data=None):
        """Redraw zones preserving the background. Delegates to renderer."""
        self.renderer.redraw_zones(zone_data)

    def start_polygon_drawing(self):
        """Activates polygon drawing mode."""
        # Garante que há frame no canvas
        if self._canvas_bg_image is None:
            self.gui.set_status("Carregando frame para desenho...")
            if not self.load_video_frame_to_canvas():
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
        self.event_handler.bind_drawing_events()

        # Add a persistent instruction label
        # Use zone_controls_frame (Phase 6 fix: use zone_controls.zone_controls_frame)
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
            "Modo de Desenho (Polígono): Clique para adicionar pontos, clique duplo para "
            "finalizar. Ctrl+Z para desfazer."
        )

    def stop_drawing(self):
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

        self.event_handler.unbind_drawing_events()

        if self.gui.video_display and self.gui.video_display.canvas:
            self.gui.video_display.canvas.delete("elastic_line")
            self.gui.video_display.canvas.delete(
                "drawing_aid"
            )  # Deletes both vertices and fixed lines
            self.gui.video_display.canvas.delete("snap_indicator")  # Clear snap indicators

        # Clear coordinate lists
        self.gui.drawing_state_manager.clear_points()

        self.gui.set_status("Pronto.")

    # Pass-through methods for event handling (to maintain API compatibility if needed)
    def handle_vertex_drag(self, event):
        return self.event_handler.on_handle_drag(event)

    def handle_canvas_click(self, event):
        return self.event_handler.on_canvas_click(event)

    def edit_selected_zone_vertices(self):
        """Enable interactive editing of the selected zone's vertices.

        Note: This involves business logic AND UI interaction, so it stays in Manager
        but delegates drawing to Renderer and events to EventHandler.
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
            if self.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.POLYGON_EDIT_REQUESTED,
                        data={"polygon": polygon_points},
                        source="CanvasManager.edit_selected_zone_vertices.arena",
                    )
                )
            else:
                # Fallback
                self.setup_interactive_polygon(polygon_points)

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

                # Convert polygon to the format expected by setup_interactive_polygon
                polygon_points = np.array(roi_polygon)

                # NEW PATH - Event-Driven Architecture v4.0
                if self.event_bus_v2:
                    from zebtrack.ui.event_bus_v2 import Event, UIEvents

                    self.event_bus_v2.publish(
                        Event(
                            type=UIEvents.POLYGON_EDIT_REQUESTED,
                            data={"polygon": polygon_points},
                            source=f"CanvasManager.edit_selected_zone_vertices.roi.{roi_name}",
                        )
                    )
                else:
                    # Fallback
                    self.setup_interactive_polygon(polygon_points)

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

    def load_selected_video_frame(self, event=None):
        """Load the frame from the selected video to the main canvas."""
        import os

        tree = self.gui.zone_controls.video_selector_tree if self.gui.zone_controls else None
        if not tree:
            return

        selection = tree.selection()
        if not selection:
            self.gui.show_warning(
                "Nenhum Vídeo Selecionado",
                "Por favor, selecione um vídeo da lista para carregar.",
            )
            return

        item_id = selection[0]
        tags = tree.item(item_id, "tags")

        if not tags or not tags[0]:
            self.gui.show_info(
                "Selecione um Vídeo",
                ("Por favor, escolha um item com ícone de peixe (🐟) para carregar o frame."),
            )
            return

        video_path = tags[0]
        success = self.load_video_frame_to_canvas(video_path, frame_number=0)

        if success:
            self.gui._maybe_offer_zone_reuse(video_path)
            self.redraw_zones_from_project_data()
            filename = os.path.basename(video_path)
            self.gui.set_status(f"✓ Frame carregado: {filename}")
            log.info("gui.video_selector.frame_loaded", path=video_path)
        else:
            self.gui.show_error(
                "Erro ao Carregar",
                f"Não foi possível carregar o vídeo selecionado.\n{video_path}",
            )

    def update_zone_listbox(self, zone_data=None):
        """Update zone listbox. Delegates to Renderer and ZoneControls."""
        self.renderer.redraw_zones(zone_data)

        # Update the listbox widget via ZoneControls (Restored Logic)
        if zone_data is None:
            zone_data = self.gui._get_zone_data_for_active_context()

        controls = getattr(self.gui, "zone_controls", None)
        if controls:
            controls.clear_zone_list()
            # Add Arena with cyan color (matching the overlay drawing)
            if zone_data.polygon:
                controls.add_zone_to_list(
                    "arena", "🏟 Arena Principal", "Polígono", "Ciano", "#00FFFF"
                )
            # Add ROIs
            if zone_data.roi_names:
                for i, name in enumerate(zone_data.roi_names):
                    color_bgr = (
                        zone_data.roi_colors[i] if i < len(zone_data.roi_colors) else (0, 255, 0)
                    )
                    # BGR to Hex for tag styling
                    color_hex = f"#{color_bgr[2]:02x}{color_bgr[1]:02x}{color_bgr[0]:02x}"
                    # Get color name from BGR value
                    color_name = self._get_color_name_from_bgr(color_bgr)
                    controls.add_zone_to_list(f"roi_{i}", f"📍 {name}", "ROI", color_name, color_hex)

    def apply_snapping(self, canvas_x, canvas_y, exclude_current_polygon=False, snap_threshold=10):
        """Apply snapping to nearby vertices or edges of existing polygons."""
        zone_data = self.gui._get_zone_data_for_active_context()
        all_polygons = []

        # Add main arena polygon if it exists
        if zone_data.polygon:
            # Convert to canvas coordinates
            canvas_polygon = []
            for point in zone_data.polygon:
                canvas_pt = self._video_to_canvas(point[0], point[1])
                canvas_polygon.append(canvas_pt)

            # Only add if not editing this polygon
            if not (exclude_current_polygon and self.current_editing_zone == "arena"):
                all_polygons.append(canvas_polygon)

        # Add all ROI polygons
        for idx, roi_polygon in enumerate(zone_data.roi_polygons):
            canvas_polygon = []
            for point in roi_polygon:
                canvas_pt = self._video_to_canvas(point[0], point[1])
                canvas_polygon.append(canvas_pt)

            # Only add if not editing this specific ROI
            skip_this_roi = (
                exclude_current_polygon
                and isinstance(self.current_editing_zone, tuple)
                and self.current_editing_zone[0] == "roi"
                and self.current_editing_zone[1] == idx
            )
            if not skip_this_roi:
                all_polygons.append(canvas_polygon)

        return GeometryService.apply_snapping(
            canvas_x, canvas_y, all_polygons, threshold=snap_threshold
        )

    def start_main_arena_drawing(self):
        """Start drawing the main arena polygon."""
        if self.gui.analysis_active:
            self.gui.show_warning(
                "Análise em Progresso",
                "Não é possível editar zonas durante a análise de vídeo.",
            )
            return

        self.gui.drawing_state_manager.drawing_type = "arena"
        self.start_polygon_drawing()

    def start_roi_drawing(self):
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

    def save_arena(self):
        """Save the edited polygon."""
        if self.current_editing_zone == "arena":
            # Save main arena
            self.gui.event_dispatcher.publish_event(
                Events.ZONE_SAVE_MANUAL_ARENA,
                {"polygon_points": self.gui.edited_polygon_points},
            )
            status_message = "Arena principal salva com sucesso."
            self.gui.set_status(status_message)
            self.update_roi_button_state()

            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            if self.event_bus_v2:
                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data={"reason": status_message, "append_summary": True},
                        source="CanvasManager.save_arena",
                    )
                )

        elif isinstance(self.current_editing_zone, tuple) and self.current_editing_zone[0] == "roi":
            # Save ROI
            _, roi_index, roi_name = self.current_editing_zone
            zone_data = self.gui._get_zone_data_for_active_context()

            # Update the ROI polygon
            zone_data.roi_polygons[roi_index] = self.gui.edited_polygon_points

            # Save to project
            self.gui.controller.project_manager.save_zone_data(zone_data)

            status_message = f"ROI '{roi_name}' salva com sucesso."
            self.gui.set_status(status_message)

            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            if self.event_bus_v2:
                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data={"reason": status_message, "append_summary": True},
                        source="CanvasManager.save_arena",
                    )
                )
        else:
            # Fallback
            self.gui.controller.save_manual_arena(self.gui.edited_polygon_points)
            status_message = "Zona salva com sucesso."
            self.gui.set_status(status_message)
            self.update_roi_button_state()

            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            if self.event_bus_v2:
                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data={"reason": status_message, "append_summary": True},
                        source="CanvasManager.save_arena",
                    )
                )

        self.clear_interactive_polygon()
        self.redraw_zones_from_project_data()

        from zebtrack.ui.event_bus_v2 import Event, UIEvents

        if self.event_bus_v2:
            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.ZONES_UPDATED,
                    data={"zone_data": None},
                    source="CanvasManager.save_arena",
                )
            )

    def discard_arena(self):
        """Discard the interactive polygon."""
        self.clear_interactive_polygon()
        if self.current_editing_zone == "arena":
            self.gui.set_status("Edição da arena descartada.")
        elif isinstance(self.current_editing_zone, tuple) and self.current_editing_zone[0] == "roi":
            _, _, roi_name = self.current_editing_zone
            self.gui.set_status(f"Edição da ROI '{roi_name}' descartada.")
        else:
            self.gui.set_status("Edição descartada.")

        self.redraw_zones_from_project_data()

    def clear_interactive_polygon(self):
        """Clear all interactive elements."""
        if self.gui.video_display and self.gui.video_display.canvas:
            self.gui.video_display.canvas.delete(
                "interactive_polygon", "handle", "suggested_polygon"
            )

        if hasattr(self.gui, "zone_controls") and self.gui.zone_controls:
            self.gui.zone_controls.hide_interactive_buttons()

        self.gui.interactive_polygon_item = None
        self.gui.polygon_handles = []
        self.gui.edited_polygon_points = []
        self.dragged_handle_index = None
        self.drag_offset = (0, 0)
        self.current_editing_zone = None

    def update_roi_button_state(self):
        """Enable ROI button if arena exists."""
        zone_data = self.gui._get_zone_data_for_active_context()
        widget = getattr(self.gui, "zone_controls", None)
        if widget:
            widget.set_draw_roi_enabled(bool(zone_data and zone_data.polygon))

    def start_circle_drawing(self):
        """Activates circle drawing mode."""
        self.stop_drawing()
        self.gui.drawing_state_manager.mode = "circle"
        self.gui.current_circle_center = None
        if self.gui.video_display and self.gui.video_display.canvas:
            self.gui.video_display.canvas.config(cursor="crosshair")

            self.gui.video_display.canvas.bind("<ButtonPress-1>", self.on_canvas_press_circle)
            self.gui.video_display.canvas.bind("<B1-Motion>", self.on_canvas_drag_circle)
            self.gui.video_display.canvas.bind("<ButtonRelease-1>", self.on_canvas_release_circle)
        self.gui.set_status("Modo de Desenho (Círculo): Clique e arraste para definir o raio.")

    def on_canvas_press_circle(self, event):
        if self.gui.drawing_state_manager.mode != "circle":
            return
        self.gui.current_circle_center = (event.x, event.y)

    def on_canvas_drag_circle(self, event):
        if self.gui.drawing_state_manager.mode != "circle" or not self.gui.current_circle_center:
            return

        if self.gui.video_display and self.gui.video_display.canvas:
            self.gui.video_display.canvas.delete("elastic_line")
            cx, cy = self.gui.current_circle_center
            radius = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5
            self.gui.video_display.canvas.create_oval(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                outline="yellow",
                dash=(4, 4),
                tags="elastic_line",
            )

    def on_canvas_release_circle(self, event):
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

        new_roi = {"name": roi_name, "type": "circle", "coords": (cx, cy, radius)}
        self.gui.roi_data.setdefault(current_arena_id, []).append(new_roi)

        if self.gui.video_display and self.gui.video_display.canvas:
            self.gui.video_display.canvas.create_oval(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                outline="blue",
                fill="cyan",
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

    def remove_selected_roi(self):
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
                # Fix for single video workflow: do not persist if no project path
                should_persist = bool(self.gui.controller.project_manager.project_path)
                self.gui.controller.project_manager.save_zone_data(
                    zone_data, persist=should_persist
                )

                # Update view
                self.redraw_zones_from_project_data()

                status_message = f"ROI '{roi_name}' removida com sucesso."
                self.gui.set_status(status_message)
                self.gui.show_info("Sucesso", status_message)

                # Refresh project views
                if self.event_bus_v2:
                    from zebtrack.ui.event_bus_v2 import Event, UIEvents

                    self.event_bus_v2.publish(
                        Event(
                            type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                            data={"reason": status_message, "append_summary": True},
                            source="CanvasManager.remove_selected_roi",
                        )
                    )
                    self.event_bus_v2.publish(
                        Event(
                            type=UIEvents.ZONES_UPDATED,
                            data={"zone_data": None},
                            source="CanvasManager.remove_selected_roi",
                        )
                    )

        except (ValueError, IndexError, AttributeError) as e:
            log.error("canvas_manager.remove_roi.error", error=str(e))
            self.gui.show_error("Erro", f"Falha ao remover ROI: {e}")

    # BGR to color name mapping (matches color_selection_dialog.py)
    _BGR_COLOR_MAP = {
        (0, 255, 0): "Verde",
        (255, 0, 0): "Azul",
        (0, 0, 255): "Vermelho",
        (0, 255, 255): "Amarelo",
        (255, 0, 255): "Magenta",
        (255, 255, 0): "Ciano",
    }

    def _get_color_name_from_bgr(self, bgr: tuple) -> str:
        """Convert BGR tuple to Portuguese color name.

        Args:
            bgr: BGR color tuple (B, G, R)

        Returns:
            Portuguese color name or hex code if not found
        """
        # Normalize to tuple of ints
        bgr_tuple = tuple(int(c) for c in bgr)
        if bgr_tuple in self._BGR_COLOR_MAP:
            return self._BGR_COLOR_MAP[bgr_tuple]
        # Fallback to hex code if color not in standard palette
        return f"#{bgr_tuple[2]:02x}{bgr_tuple[1]:02x}{bgr_tuple[0]:02x}"

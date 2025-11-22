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

from zebtrack.ui.components.canvas.renderer import CanvasRenderer
from zebtrack.ui.components.canvas.event_handler import CanvasEventHandler

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

        # Subscribe to POLYGON_EDIT_REQUESTED event (replaces direct gui.setup_interactive_polygon calls)
        self.event_bus_v2.subscribe(UIEvents.POLYGON_EDIT_REQUESTED, self._on_polygon_edit_requested)

        log.debug("canvas_manager.event_subscriptions_setup",
                  events=["ZONES_UPDATED", "POLYGON_EDIT_REQUESTED"])

    def _on_zones_updated(self, data: dict):
        """Handle ZONES_UPDATED event.

        Args:
            data: Event payload containing zone_data
        """
        zone_data = data.get("zone_data")
        log.debug("canvas_manager.zones_updated_event_received", has_zone_data=zone_data is not None)
        self.update_zone_listbox(zone_data)

    def _on_polygon_edit_requested(self, data: dict):
        """Handle POLYGON_EDIT_REQUESTED event.

        Sets up interactive polygon editing mode by populating gui.edited_polygon_points
        and drawing the polygon with interactive handles.

        Args:
            data: Event payload containing:
                - polygon: np.ndarray of polygon points [[x1, y1], [x2, y2], ...]
        """
        polygon = data.get("polygon")
        if polygon is None:
            log.warning("canvas_manager.polygon_edit_requested.missing_polygon")
            return

        # Convert numpy array to list of lists if needed
        if isinstance(polygon, np.ndarray):
            polygon_list = polygon.tolist()
        else:
            polygon_list = polygon

        # Populate gui.edited_polygon_points (THIS IS THE MISSING LOGIC!)
        self.gui.edited_polygon_points = polygon_list

        # Draw the interactive polygon with handles
        self.renderer.draw_interactive_polygon()

        log.debug("canvas_manager.polygon_edit_requested.complete",
                  num_points=len(polygon_list))

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
            from zebtrack.ui.utils import set_geometry_if_not_maximized

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
        self.gui._stop_drawing()  # Ensure clean state
        self.gui.drawing_state_manager.drawing_type = preserved_drawing_type  # Restore

        self.gui.drawing_state_manager.start_polygon_drawing()
        self.event_handler.bind_drawing_events()

        # Add a persistent instruction label
        # Use zone_controls_frame (Phase 6 fix: use zone_controls.zone_controls_frame)
        zc_frame = (
            self.gui.zone_controls.zone_controls_frame if self.gui.zone_controls else None
        )
        zc_listbox = (
            self.gui.zone_controls.zone_listbox if self.gui.zone_controls else None
        )

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

        self.gui.video_display.canvas.delete("elastic_line")
        self.gui.video_display.canvas.delete("drawing_aid")  # Deletes both vertices and fixed lines
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
        if self.gui.drawing_mode is not None:
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

            # DUAL MODE (v3/v4 compatibility): OLD PATH (deprecated) + NEW PATH (v4.0)
            self.gui.setup_interactive_polygon(polygon_points)  # OLD PATH - will be removed in v4.0

            if self.event_bus_v2:  # NEW PATH - Event-Driven Architecture v4.0
                from zebtrack.ui.event_bus_v2 import Event, UIEvents
                self.event_bus_v2.publish(Event(
                    type=UIEvents.POLYGON_EDIT_REQUESTED,
                    data={'polygon': polygon_points},
                    source='CanvasManager.edit_selected_zone_vertices.arena'
                ))

            self.gui.current_editing_zone = "arena"
            self.gui.set_status("Editando vértices da arena principal. Arraste os pontos amarelos.")

        else:
            # Edit ROI
            roi_name = zone_name.replace("📍 ", "")
            try:
                roi_index = zone_data.roi_names.index(roi_name)
                roi_polygon = zone_data.roi_polygons[roi_index]

                # Convert polygon to the format expected by setup_interactive_polygon
                polygon_points = np.array(roi_polygon)

                # DUAL MODE (v3/v4 compatibility): OLD PATH (deprecated) + NEW PATH (v4.0)
                self.gui.setup_interactive_polygon(polygon_points)  # OLD PATH - will be removed in v4.0

                if self.event_bus_v2:  # NEW PATH - Event-Driven Architecture v4.0
                    from zebtrack.ui.event_bus_v2 import Event, UIEvents
                    self.event_bus_v2.publish(Event(
                        type=UIEvents.POLYGON_EDIT_REQUESTED,
                        data={'polygon': polygon_points},
                        source=f'CanvasManager.edit_selected_zone_vertices.roi.{roi_name}'
                    ))

                self.gui.current_editing_zone = ("roi", roi_index, roi_name)
                self.gui.set_status(
                    f"Editando vértices da ROI '{roi_name}'. Arraste os pontos amarelos."
                )

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
        """Update zone listbox. Delegates to Renderer."""
        self.renderer.redraw_zones(zone_data)
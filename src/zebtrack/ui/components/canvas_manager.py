"""Canvas management for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles canvas drawing, coordinate transformations, overlays, and rendering.
Delegates specific responsibilities to CanvasRenderer and CanvasEventHandler.
"""

import os
import typing

import cv2
import numpy as np
import structlog
import ttkbootstrap as ttk
from PIL import Image

from zebtrack.core.zone_manager import MultiAquariumZoneData
from zebtrack.ui.components.canvas.event_handler import CanvasEventHandler
from zebtrack.ui.components.canvas.renderer import CanvasRenderer
from zebtrack.ui.event_bus_v2 import Event, UIEvents
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

        # Visualization settings
        self.show_geotaxis_zones = False

        # Live session tracking
        self._live_frame_subscription = None  # Track subscription for cleanup

        # Initialize sub-components
        self.renderer = CanvasRenderer(self)
        self.event_handler = CanvasEventHandler(self)

        # Subscribe to events if event bus is available
        if self.event_bus_v2:
            self._setup_event_subscriptions()

    def _get_canvas(self):
        """Get the canvas safely, returning None if video_display doesn't exist or is destroyed.

        This is needed because CanvasManager is created during ApplicationGUI.__init__
        but video_display is only created later when build_zone_tab() is called.
        Also handles the case where the canvas has been destroyed (e.g., project close).
        """
        if not hasattr(self.gui, "video_display") or not self.gui.video_display:
            return None
        canvas = self.gui.video_display.canvas
        if canvas is None:
            return None
        # Check if the canvas widget still exists (not destroyed)
        try:
            if not canvas.winfo_exists():
                return None
        except Exception:
            return None
        return canvas

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

        # Subscribe to legacy UI events (Live Camera Stream)
        if hasattr(self.gui, "event_bus") and self.gui.event_bus:
            self._live_frame_subscription = self.gui.event_bus.subscribe(
                Events.UI_UPDATE_LIVE_FRAME, self._on_live_frame_update
            )
            # Note: _live_session_active remains False until a live session actually starts
            log.debug("canvas_manager.subscribed_to_live_frame_updates")

    def _on_zones_updated(self, data: dict):
        """Handle ZONES_UPDATED event.

        Args:
            data: Event payload containing zone_data
        """
        if not isinstance(data, dict):
            log.warning(
                "canvas_manager._on_zones_updated.invalid_data_type", data_type=type(data).__name__
            )
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
            log.warning(
                "canvas_manager._on_polygon_edit_requested.invalid_data_type",
                data_type=type(data).__name__,
            )
            return
        polygon = data.get("polygon")
        if polygon is not None:
            self.setup_interactive_polygon(polygon)

    def _on_live_frame_update(self, data: dict):
        """Handle UI_UPDATE_LIVE_FRAME event from LiveCameraService.

        Args:
            data: Payload with 'frame' (np.ndarray) and 'detections'.
        """
        log.debug(
            "canvas_manager._on_live_frame_update.called",
            has_data=isinstance(data, dict),
            has_frame=isinstance(data, dict) and "frame" in data,
        )

        if not isinstance(data, dict):
            return

        frame = data.get("frame")
        detections = data.get("detections")

        if frame is not None:
            # We are already on the main thread here via EventDispatcher polling
            self.update_video_frame(frame, detections)

    def unsubscribe_from_live_frames(self):
        """Unsubscribe from live frame updates to stop receiving events."""
        log.info(
            "canvas_manager.unsubscribe_from_live_frames.called",
            has_subscription=hasattr(self, "_live_frame_subscription"),
            has_event_bus=hasattr(self.gui, "event_bus") and self.gui.event_bus is not None,
        )

        if hasattr(self.gui, "event_bus") and self.gui.event_bus:
            try:
                self.gui.event_bus.unsubscribe(
                    Events.UI_UPDATE_LIVE_FRAME, self._on_live_frame_update
                )
                if hasattr(self, "_live_frame_subscription"):
                    self._live_frame_subscription = None
                log.info("canvas_manager.unsubscribed_from_live_frames.success")
            except Exception as e:
                log.warning("canvas_manager.unsubscribe_failed", error=str(e), exc_info=True)

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

    def on_multi_auto_detect_success(self, data: dict):
        """Handle successful multi-aquarium detection.

        Args:
            data: Payload with "polygons" (list of lists) and "video_path".
        """
        polygons = data.get("polygons")
        video_path = data.get("video_path")

        if not polygons or not video_path:
            log.warning("canvas_manager.multi_success.missing_data", data=data)
            return

        log.info("canvas_manager.multi_success.called", count=len(polygons))

        # 1. Create MultiAquariumZoneData - PRESERVE EXISTING METADATA
        from zebtrack.core.detector import AquariumData, MultiAquariumZoneData

        pm = self.gui.controller.project_manager

        # CRITICAL FIX: Get existing zone data to preserve metadata (group, subject_id, day)
        existing_data = pm.get_multi_aquarium_zone_data(video_path=video_path)
        existing_aquariums = {}
        if existing_data and hasattr(existing_data, "aquariums"):
            for aq in existing_data.aquariums:
                existing_aquariums[aq.id] = aq
            log.debug(
                "canvas_manager.multi_success.preserving_metadata",
                existing_count=len(existing_aquariums),
                video_path=video_path,
            )

        # Create new aquariums, MERGING new polygons with existing metadata
        aquariums_list = []
        for i, p in enumerate(polygons):
            if i in existing_aquariums:
                # PRESERVE existing metadata, only update polygon
                existing_aq = existing_aquariums[i]
                new_aq = AquariumData(
                    id=i,
                    polygon=p,
                    group=existing_aq.group,
                    subject_id=existing_aq.subject_id,
                    day=existing_aq.day,
                    roi_mode=existing_aq.roi_mode,
                    roi_data=existing_aq.roi_data,
                )
                log.debug(
                    "canvas_manager.multi_success.metadata_preserved",
                    aquarium_id=i,
                    subject_id=existing_aq.subject_id,
                    group=existing_aq.group,
                )
            else:
                # New aquarium - no existing metadata
                new_aq = AquariumData(id=i, polygon=p)
            aquariums_list.append(new_aq)

        multi_data = MultiAquariumZoneData(aquariums=aquariums_list)

        # Copy sequential_processing flag from existing data if available
        if existing_data and hasattr(existing_data, "sequential_processing"):
            multi_data.sequential_processing = existing_data.sequential_processing

        # 2. Save via ProjectManager (pm já foi obtido acima)
        pm.save_multi_aquarium_zone_data(video_path, multi_data)

        # 3. Update UI
        # Ensure we are viewing this video
        pm.set_active_zone_video(video_path)

        # If ZoneControls exist, ensure the aquarium selector is set to 2 (or N)
        if self.gui.zone_controls:
            # Update UI state for N aquariums
            self.gui.zone_controls.update_aquarium_count(len(polygons))

        # Redraw
        self.redraw_zones_from_project_data(multi_data)
        self.update_zone_listbox(multi_data)

        self.gui.show_info(
            "Sucesso",
            f"Detectados {len(polygons)} aquários com sucesso!\n"
            "Verifique se as marcações estão corretas.",
        )

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

            # Check if file is an image or video
            lower_path = video_path.lower()
            if lower_path.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff")):
                # It's an image - Use robust loading for Windows paths (unicode support)
                try:
                    # np.fromfile handles paths with special chars better than cv2.imread on Windows
                    file_data = np.fromfile(video_path, dtype=np.uint8)
                    frame = cv2.imdecode(file_data, cv2.IMREAD_COLOR)
                except Exception as e:
                    log.error(
                        "gui.display_roi_frame.image_load_failed", error=str(e), path=video_path
                    )
                    frame = None

                if frame is None:
                    # Fallback to standard imread just in case
                    frame = cv2.imread(video_path)

                if frame is None:
                    self.gui.show_error("Erro", "Não foi possível ler a imagem.")
                    return
                ret = True
            else:
                # Assume it's a video
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

            # Wait for the canvas to be properly sized after geometry update, then draw
            # Force canvas update before drawing to ensure proper sizing
            self.gui.root.update_idletasks()

            # Draw immediately to prevent black canvas warnings
            self._draw_bg_image_to_canvas()

            # Schedule another redraw after 10ms to ensure canvas is fully ready
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
        log.debug(
            "canvas_manager.update_video_frame.called",
            has_frame=frame is not None,
            analysis_active=self.gui.analysis_active
            if hasattr(self.gui, "analysis_active")
            else None,
            has_widget=bool(self.gui.analysis_display_widget)
            if hasattr(self.gui, "analysis_display_widget")
            else None,
        )

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
                target_w, target_h = 640, 480

                # Try to get current container size if available
                if self.gui.analysis_display_widget.video_container:
                    w = self.gui.analysis_display_widget.video_container.winfo_width()
                    h = self.gui.analysis_display_widget.video_container.winfo_height()
                    if w > 100 and h > 100:
                        target_w, target_h = w, h

                pil_image.thumbnail((target_w, target_h), Image.LANCZOS)
                self.gui.analysis_display_widget.update_frame(pil_image)
            else:
                log.debug(
                    "canvas_manager.update_video_frame.skipped",
                    analysis_active=self.gui.analysis_active,
                    has_widget=bool(self.gui.analysis_display_widget),
                )
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
            # 1. Try to use currently active zone video (e.g. just set by display_roi_video_frame)
            active_video = self.gui.controller.project_manager.get_active_zone_video()
            if active_video and os.path.exists(active_video):
                video_path = active_video

            # 2. Try to use pending video (e.g. from wizard)
            elif (
                hasattr(self.gui, "pending_single_video_path")
                and self.gui.pending_single_video_path
            ):
                video_path = self.gui.pending_single_video_path

            # 3. Fallback to first video in project
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

            # Check if file is an image or video
            lower_path = video_path.lower()
            if lower_path.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff")):
                # Handle image files (e.g., live camera reference frame)
                try:
                    # Robust loading for Windows paths
                    file_data = np.fromfile(video_path, dtype=np.uint8)
                    frame = cv2.imdecode(file_data, cv2.IMREAD_COLOR)

                    if frame is None:
                        # Fallback
                        frame = cv2.imread(video_path)

                    ret = frame is not None
                    if not ret:
                        log.error("gui.load_frame.image_load_failed", path=video_path)
                except Exception as e:
                    log.error("gui.load_frame.image_exception", error=str(e), path=video_path)
                    ret = False
                    frame = None
            else:
                # Handle video files
                cap = cv2.VideoCapture(video_path)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                ret, frame = cap.read()
                cap.release()

            if not ret or frame is None:
                log.warning(
                    "gui.load_frame.failed_to_read",
                    path=video_path,
                    is_image=lower_path.endswith((".png", ".jpg")),
                )
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

        canvas = self._get_canvas()
        if canvas:
            canvas.delete("elastic_line")
            canvas.delete("drawing_aid")  # Deletes both vertices and fixed lines
            canvas.delete("snap_indicator")  # Clear snap indicators

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

    def apply_snapping(self, canvas_x, canvas_y, exclude_current_polygon=False, snap_threshold=10):
        """Apply snapping to nearby vertices or edges of existing polygons."""
        zone_data = self.gui._get_zone_data_for_active_context()
        all_polygons = []

        from zebtrack.core.detector import MultiAquariumZoneData

        # Normalize to a list of (ZoneData, is_active) tuples
        targets = []
        if isinstance(zone_data, MultiAquariumZoneData):
            zone_controls = getattr(self.gui, "zone_controls", None)
            active_id = zone_controls.active_aquarium_var.get() if zone_controls else 0
            for aq in zone_data.aquariums:
                targets.append((aq.to_zone_data(), aq.id == active_id))
        else:
            targets.append((zone_data, True))

        for zd, is_active in targets:
            # Arena
            if zd.polygon:
                canvas_polygon = []
                for point in zd.polygon:
                    canvas_pt = self._video_to_canvas(point[0], point[1])
                    canvas_polygon.append(canvas_pt)

                # Exclude if it's the one we are editing
                if not (
                    is_active and exclude_current_polygon and self.current_editing_zone == "arena"
                ):
                    all_polygons.append(canvas_polygon)

            # ROIs
            for idx, roi_polygon in enumerate(zd.roi_polygons):
                canvas_polygon = []
                for point in roi_polygon:
                    canvas_pt = self._video_to_canvas(point[0], point[1])
                    canvas_polygon.append(canvas_pt)

                skip = (
                    is_active
                    and exclude_current_polygon
                    and isinstance(self.current_editing_zone, tuple)
                    and self.current_editing_zone[0] == "roi"
                    and self.current_editing_zone[1] == idx
                )
                if not skip:
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

        # Show aquarium indicator if in multi-aquarium mode
        zone_controls = self.gui.zone_controls
        if zone_controls and zone_controls.aquarium_count_var.get() == 2:
            active_id = zone_controls.active_aquarium_var.get()
            self._show_aquarium_indicator(f"Desenhando: Aquário {active_id + 1} de 2")

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
        # Check for multi-aquarium mode first
        zone_controls = getattr(self.gui, "zone_controls", None)
        if (
            self.current_editing_zone == "arena"
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
                    self.redraw_zones_from_project_data()

                    from zebtrack.ui.event_bus_v2 import Event, UIEvents

                    if self.event_bus_v2:
                        # Emit ZONES_UPDATED for zone listbox refresh
                        self.event_bus_v2.publish(
                            Event(
                                type=UIEvents.ZONES_UPDATED,
                                data={"zone_data": None},
                                source="CanvasManager.save_arena.multi_aquarium",
                            )
                        )
                        # Emit PROJECT_VIEWS_REFRESH to update VideoTree badges
                        self.event_bus_v2.publish(
                            Event(
                                type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                                data={"reason": status_message, "append_summary": True},
                                source="CanvasManager.save_arena.multi_aquarium",
                            )
                        )
                        # Also emit VIDEO_TREE_REFRESH for immediate tree update
                        self.event_bus_v2.publish(
                            Event(
                                type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                                data={"filter_text": None},
                                source="CanvasManager.save_arena.multi_aquarium",
                            )
                        )
                    return

        if self.current_editing_zone == "arena":
            # Save main arena (Single Aquarium)
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

        # Check if we should prompt to add a second aquarium
        self.gui.root.after(100, self._check_prompt_second_aquarium)

    def _check_prompt_second_aquarium(self) -> None:
        """Check if we should prompt to add a second aquarium."""
        zone_controls = self.gui.zone_controls
        if not zone_controls:
            return

        # Only prompt if still in single-aquarium mode
        if zone_controls.aquarium_count_var.get() != 1:
            return

        # Check explicit setting from configuration/project
        # If user explicitly set num_aquariums=1, do NOT prompt
        if self.gui.controller.settings.analysis_config.num_aquariums == 1:
            return

        # Only prompt if saving the first aquarium
        if zone_controls.active_aquarium_var.get() != 0:
            return

        self._prompt_add_second_aquarium()

    def _prompt_add_second_aquarium(self) -> None:
        """Ask user if they want to add a second aquarium."""
        from tkinter import messagebox

        result = messagebox.askyesno(
            "Adicionar Segundo Aquário",
            "Polígono salvo com sucesso!\n\n"
            "Este vídeo possui dois aquários?\n"
            "Se sim, você poderá desenhar o polígono do segundo.",
            icon="question",
        )

        if result:
            # Convert existing zone data to multi-aquarium format
            self._convert_to_multi_aquarium_format()

            # Activate multi-aquarium mode in UI
            self.gui.zone_controls.set_aquarium_count(2)
            # Select aquarium 2
            self.gui.zone_controls.active_aquarium_var.set(1)
            self.gui.zone_controls._on_aquarium_selected()
            # Start drawing after delay
            self.gui.root.after(200, self._start_second_aquarium_drawing)

    def _convert_to_multi_aquarium_format(self) -> None:
        """Convert current zone data to multi-aquarium format."""
        from zebtrack.core.detector import AquariumData, MultiAquariumZoneData

        video_path = self.gui.controller.project_manager.get_active_zone_video()
        if not video_path:
            return

        # Get current zone data with first polygon
        zone_data = self.gui.controller.project_manager.get_zone_data(video_path)
        if not zone_data or not zone_data.polygon:
            return

        # Create AquariumData for first aquarium
        aquarium_0 = AquariumData(
            id=0,
            polygon=zone_data.polygon,
            roi_polygons=zone_data.roi_polygons,
            roi_names=zone_data.roi_names,
            roi_colors=zone_data.roi_colors,
        )

        # Create empty AquariumData for second aquarium
        aquarium_1 = AquariumData(id=1)

        # Create MultiAquariumZoneData
        multi_data = MultiAquariumZoneData(
            aquariums=[aquarium_0, aquarium_1],
        )

        # Save multi-aquarium data via ProjectManager to ensure parquet export
        # and validation flags are updated correctly.
        self.gui.controller.project_manager.save_multi_aquarium_zone_data(
            video_path,
            multi_data,
            persist=True,
        )

    def _start_second_aquarium_drawing(self) -> None:
        """Start drawing the second aquarium polygon."""
        self.gui.show_info(
            "Informação",
            "Desenhe o polígono do Aquário 2.\n"
            "O polígono do Aquário 1 será mostrado como referência.",
        )
        self.start_main_arena_drawing()

    def get_other_aquarium_polygon(self) -> list[list[int]] | None:
        """Get the polygon of the OTHER aquarium for ghost rendering.

        Returns:
            The polygon points of the other aquarium, or None if not available.
        """
        zone_controls = self.gui.zone_controls
        if not zone_controls or zone_controls.aquarium_count_var.get() != 2:
            return None

        active_id = zone_controls.active_aquarium_var.get()
        other_id = 1 - active_id  # 0 -> 1, 1 -> 0

        video_path = self.gui.controller.project_manager.get_active_zone_video()
        if not video_path:
            return None

        project_data = self.gui.controller.project_manager.project_data
        if not project_data:
            return None

        # Try to get from multi-aquarium data structure
        from zebtrack.core.zone_manager import ZoneManager

        zone_manager = ZoneManager()
        multi_data = zone_manager.get_multi_aquarium_zone_data(project_data, video_path)

        if multi_data:
            aquarium = multi_data.get_aquarium(other_id)
            if aquarium and aquarium.polygon:
                return aquarium.polygon

        # Fallback: if other_id=0, try regular zone data
        if other_id == 0:
            zone_data = self.gui.controller.project_manager.get_zone_data(video_path)
            if zone_data and hasattr(zone_data, "polygon") and zone_data.polygon:
                return zone_data.polygon

        return None

    def _show_aquarium_indicator(self, text: str) -> None:
        """Show indicator of which aquarium is being drawn."""
        canvas = self._get_canvas()
        if not canvas:
            return
        canvas.delete("aquarium_indicator")
        canvas.create_text(
            canvas.winfo_width() // 2,
            30,
            text=text,
            fill="#0066CC",
            font=("Segoe UI", 12, "bold"),
            tags="aquarium_indicator",
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
        canvas = self._get_canvas()
        if canvas:
            canvas.delete("interactive_polygon", "handle", "suggested_polygon")

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

    def start_circle_drawing(self):
        """Activates circle drawing mode."""
        self.stop_drawing()
        self.gui.drawing_state_manager.mode = "circle"
        self.gui.current_circle_center = None
        canvas = self._get_canvas()
        if canvas:
            canvas.config(cursor="crosshair")

            canvas.bind("<ButtonPress-1>", self.on_canvas_press_circle)
            canvas.bind("<B1-Motion>", self.on_canvas_drag_circle)
            canvas.bind("<ButtonRelease-1>", self.on_canvas_release_circle)
        self.gui.set_status("Modo de Desenho (Círculo): Clique e arraste para definir o raio.")

    def on_canvas_press_circle(self, event):
        if self.gui.drawing_state_manager.mode != "circle":
            return
        self.gui.current_circle_center = (event.x, event.y)

    def on_canvas_drag_circle(self, event):
        if self.gui.drawing_state_manager.mode != "circle" or not self.gui.current_circle_center:
            return

        canvas = self._get_canvas()
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

        canvas = self._get_canvas()
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
    _BGR_COLOR_MAP: typing.ClassVar = {
        (0, 128, 0): "Verde",
        (255, 0, 0): "Azul",
        (0, 0, 255): "Vermelho",
        (0, 204, 204): "Amarelo",
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

        if not hasattr(self, "_zone_clipboard") or not self._zone_clipboard:
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
        self.redraw_zones_from_project_data()
        self.update_zone_listbox()

        # Refresh video tree to update status icons
        if self.event_bus_v2:
            self.event_bus_v2.publish(
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
        self.redraw_zones_from_project_data()
        self.update_zone_listbox()

        # Refresh video tree to update status icons
        if self.event_bus_v2:
            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data={"filter_text": None},
                    source="CanvasManager.delete_zones_from_video",
                )
            )

    # -------------------------------------------------------------------------
    # Multi-Aquarium Overlay Methods (Phase 11)
    # -------------------------------------------------------------------------

    # Distinct colors for each aquarium
    AQUARIUM_COLORS: typing.ClassVar = {
        0: {"border": (0, 102, 204), "fill": (0, 102, 204, 51), "text": "Aquário 1"},
        1: {"border": (0, 204, 102), "fill": (0, 204, 102, 51), "text": "Aquário 2"},
    }

    def draw_multi_aquarium_overlay(
        self,
        frame: np.ndarray,
        zone_data: "MultiAquariumZoneData",
        detections_by_aquarium: dict[int, list] | None = None,
        show_labels: bool = True,
        show_rois: bool = True,
    ) -> np.ndarray:
        """
        Draw overlay with multiple aquariums on a video frame.

        Each aquarium is drawn with a distinct border color, and optionally
        includes labels indicating the aquarium number and experimental group.
        Detections (bounding boxes) are drawn with the corresponding aquarium color.

        Args:
            frame: The video frame as a numpy array (BGR format from OpenCV).
            zone_data: MultiAquariumZoneData containing aquarium configurations.
            detections_by_aquarium: Optional dict mapping aquarium_id to list of
                detections. Each detection is a tuple (x1, y1, x2, y2, conf, track_id, class_id).
            show_labels: Whether to show aquarium labels (default True).
            show_rois: Whether to show ROI polygons (default True).

        Returns:
            The frame with overlay drawn (modified in place but also returned).

        Example:
            >>> overlay_frame = canvas_manager.draw_multi_aquarium_overlay(
            ...     frame=current_frame,
            ...     zone_data=multi_aquarium_zone_data,
            ...     detections_by_aquarium={0: [...], 1: [...]},
            ... )
        """
        from zebtrack.core.detector import MultiAquariumZoneData

        if not isinstance(zone_data, MultiAquariumZoneData):
            log.warning(
                "canvas_manager.draw_multi_aquarium_overlay.invalid_zone_data",
                zone_data_type=type(zone_data).__name__,
            )
            return frame

        overlay = frame.copy()

        for aq in zone_data.aquariums:
            colors = self.AQUARIUM_COLORS.get(aq.id, self.AQUARIUM_COLORS[0])
            border_color = colors["border"]  # BGR tuple

            # Draw aquarium polygon border
            if aq.polygon:
                polygon_np = np.array(aq.polygon, dtype=np.int32)
                cv2.polylines(overlay, [polygon_np], True, border_color, 2)

                # Draw label in top-left corner of aquarium
                if show_labels and len(polygon_np) > 0:
                    # Find top-left corner (minimum x, y)
                    min_x = int(np.min(polygon_np[:, 0]))
                    min_y = int(np.min(polygon_np[:, 1]))

                    label = f"{colors['text']}"
                    if aq.group:
                        label += f" - {aq.group}"

                    # Draw background rectangle for label
                    (text_w, text_h), _baseline = cv2.getTextSize(
                        label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
                    )
                    cv2.rectangle(
                        overlay,
                        (min_x, min_y),
                        (min_x + text_w + 10, min_y + text_h + 10),
                        border_color,
                        -1,  # Filled
                    )
                    cv2.putText(
                        overlay,
                        label,
                        (min_x + 5, min_y + text_h + 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (255, 255, 255),  # White text
                        2,
                    )

            # Draw ROIs for this aquarium
            if show_rois and aq.roi_polygons:
                for i, roi_polygon in enumerate(aq.roi_polygons):
                    roi_np = np.array(roi_polygon, dtype=np.int32)
                    # Use ROI color if available, otherwise use aquarium border color
                    roi_color = aq.roi_colors[i] if i < len(aq.roi_colors) else border_color
                    cv2.polylines(overlay, [roi_np], True, roi_color, 1)

                    # Draw ROI name at centroid
                    if i < len(aq.roi_names) and len(roi_np) > 0:
                        centroid = np.mean(roi_np, axis=0).astype(int)
                        cv2.putText(
                            overlay,
                            aq.roi_names[i],
                            (centroid[0] - 20, centroid[1]),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.4,
                            roi_color,
                            1,
                        )

            # Draw detections for this aquarium
            if detections_by_aquarium and aq.id in detections_by_aquarium:
                for det in detections_by_aquarium[aq.id]:
                    if len(det) >= 6:
                        x1, y1, x2, y2, _conf, track_id = det[:6]
                        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                        # Draw bounding box
                        cv2.rectangle(overlay, (x1, y1), (x2, y2), border_color, 2)

                        # Draw track ID (local ID without offset)
                        if track_id is not None:
                            local_id = int(track_id) % 1000
                            id_label = f"ID:{local_id}"
                            cv2.putText(
                                overlay,
                                id_label,
                                (x1, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                border_color,
                                2,
                            )

        return overlay

    @staticmethod
    def hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
        """Convert hex color string to BGR tuple for OpenCV.

        Args:
            hex_color: Hex color string (e.g., "#0066CC").

        Returns:
            BGR tuple (e.g., (204, 102, 0) for "#0066CC").
        """
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return (b, g, r)  # OpenCV uses BGR

    def create_side_by_side_preview(
        self,
        frame: np.ndarray,
        zone_data: "MultiAquariumZoneData",
        detections_by_aquarium: dict[int, list] | None = None,
        target_width: int = 1280,
        show_labels: bool = True,
        padding: int = 10,
    ) -> np.ndarray:
        """Create side-by-side preview of each aquarium cropped from the frame.

        Phase 3.1: Creates a composite image showing each aquarium region
        side by side for easier comparison during analysis review.

        Args:
            frame: Input BGR frame.
            zone_data: MultiAquariumZoneData containing aquarium configurations.
            detections_by_aquarium: Optional dict mapping aquarium_id to detections.
            target_width: Target width for the composite image.
            show_labels: Whether to show aquarium labels.
            padding: Pixels between aquarium previews.

        Returns:
            Composite image with aquariums displayed side by side.

        Example:
            >>> preview = canvas_manager.create_side_by_side_preview(
            ...     frame, zone_data, detections
            ... )
            >>> cv2.imshow("Side-by-Side", preview)
        """
        if not zone_data or not zone_data.aquariums:
            return frame

        num_aquariums = len(zone_data.aquariums)
        if num_aquariums == 0:
            return frame

        # Calculate dimensions for each aquarium panel
        panel_width = (target_width - padding * (num_aquariums + 1)) // num_aquariums
        crops = []

        for aq in zone_data.aquariums:
            # Get bounding box of aquarium polygon
            aq_np = np.array(aq.polygon, dtype=np.int32)
            x, y, w, h = cv2.boundingRect(aq_np)

            # Clamp to frame bounds
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(frame.shape[1], x + w)
            y2 = min(frame.shape[0], y + h)

            # Crop aquarium region
            crop = frame[y1:y2, x1:x2].copy()

            # Draw detections on crop (adjusting coordinates)
            if detections_by_aquarium and aq.id in detections_by_aquarium:
                border_color = self.AQUARIUM_COLORS.get(aq.id, ("#AAAAAA", f"Aq{aq.id}"))
                border_color = self.hex_to_bgr(border_color[0])
                for det in detections_by_aquarium[aq.id]:
                    if len(det) >= 6:
                        dx1, dy1, dx2, dy2, _conf, track_id = det[:6]
                        # Adjust to crop coordinates
                        dx1, dy1 = int(dx1 - x1), int(dy1 - y1)
                        dx2, dy2 = int(dx2 - x1), int(dy2 - y1)
                        if dx1 >= 0 and dy1 >= 0:
                            cv2.rectangle(crop, (dx1, dy1), (dx2, dy2), border_color, 2)
                            if track_id is not None:
                                local_id = int(track_id) % 1000
                                cv2.putText(
                                    crop,
                                    f"ID:{local_id}",
                                    (dx1, dy1 - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.5,
                                    border_color,
                                    2,
                                )

            # Add label
            if show_labels:
                colors = self.AQUARIUM_COLORS.get(aq.id, ("#AAAAAA", f"Aq{aq.id}"))
                label = colors[1]
                if aq.group:
                    label += f" ({aq.group})"
                cv2.putText(
                    crop, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
                )
                cv2.putText(
                    crop,
                    label,
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    self.hex_to_bgr(colors[0]),
                    1,
                )

            # Resize to panel width maintaining aspect ratio
            aspect = crop.shape[0] / crop.shape[1] if crop.shape[1] > 0 else 1
            panel_height = int(panel_width * aspect)
            resized = cv2.resize(crop, (panel_width, panel_height))
            crops.append(resized)

        # Find max height for uniform composite
        max_height = max(c.shape[0] for c in crops) if crops else 100

        # Create composite image
        composite_width = target_width
        composite = np.zeros((max_height + padding * 2, composite_width, 3), dtype=np.uint8)
        composite[:] = (40, 40, 40)  # Dark gray background

        # Place each crop
        x_offset = padding
        for crop in crops:
            h, w = crop.shape[:2]
            y_offset = padding + (max_height - h) // 2  # Center vertically
            composite[y_offset : y_offset + h, x_offset : x_offset + w] = crop
            x_offset += w + padding

        return composite

    def toggle_geotaxis_visualization(self, show: bool):
        """Toggle visualization of geotaxis zones."""
        self.show_geotaxis_zones = show
        self.redraw_zones_from_project_data()
        log.info("canvas_manager.geotaxis_viz.toggled", show=show)

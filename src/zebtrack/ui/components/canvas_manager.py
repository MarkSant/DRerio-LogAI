"""Canvas management for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles canvas drawing, coordinate transformations, overlays, and rendering.
"""

import os

import cv2
import numpy as np
import structlog
import ttkbootstrap as ttk
from PIL import Image, ImageTk

from zebtrack.utils.geometry_service import GeometryService

log = structlog.get_logger()


class CanvasManager:
    """Manages canvas operations, drawing, and coordinate transformations."""

    def __init__(self, gui):
        """Initialize CanvasManager.

        Args:
            gui: Reference to ApplicationGUI instance
        """
        self.gui = gui
        # Transformation attributes
        self._bg_scale = None
        self._bg_offset = None
        self._bg_img_size = None
        self._raw_bg_image = None
        self._canvas_bg_image = None
        self._canvas_bg_position = None

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

    # ========== Background Image Drawing Methods ==========

    def _draw_bg_image_to_canvas(self):
        """Draw the background image to canvas with proper scaling and centering.

        This method handles:
        - Loading the raw background image
        - Calculating proper scaling to fit canvas while maintaining aspect ratio
        - Centering the image on the canvas
        - Storing scaling information for coordinate transformations
        """
        if not hasattr(self, "_raw_bg_image") or not self._raw_bg_image:
            if hasattr(self, "_original_image") and self.gui._original_image:
                self._raw_bg_image = self.gui._original_image
            else:
                return

        # Get actual canvas dimensions after layout
        canvas_width = self.gui.video_display.canvas.winfo_width()
        canvas_height = self.gui.video_display.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            # Canvas not ready yet, try again
            self.gui.root.after(10, self._draw_bg_image_to_canvas)
            return

        # Calculate scaling to fit image while maintaining aspect ratio
        img_w, img_h = self._raw_bg_image.size
        scale = min(canvas_width / img_w, canvas_height / img_h, 1.0)
        new_width = int(img_w * scale)
        new_height = int(img_h * scale)

        # Store scaling information for coordinate conversion
        self._bg_scale = scale
        self._bg_img_size = (img_w, img_h)  # Original image size

        # Calculate offset (top-left position of scaled image in canvas)
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        offset_x = center_x - new_width // 2
        offset_y = center_y - new_height // 2
        self._bg_offset = (offset_x, offset_y)

        # Scale the image
        image = self._raw_bg_image.resize((new_width, new_height), Image.LANCZOS)

        # Clear canvas and display centered image
        self.gui.video_display.canvas.delete("all")
        self._canvas_bg_image = ImageTk.PhotoImage(image)

        # Store positioning for later restoration in redraw_zones_from_project_data
        self._canvas_bg_position = (center_x, center_y, "center")

        self.gui.video_display.canvas.create_image(
            center_x,
            center_y,
            anchor="center",
            image=self._canvas_bg_image,
            tags="background_image",
        )

    def on_canvas_configure(self, event=None):
        """Handle canvas resize events to properly scale and center the image."""
        # Skip if this is not the main roi_canvas being resized
        # NOTE: roi_canvas was removed from gui, using video_display.canvas
        if (
            event
            and hasattr(self.gui, "video_display")
            and self.gui.video_display
            and event.widget != self.gui.video_display.canvas
        ):
            return

        if not hasattr(self, "_raw_bg_image") or not self._raw_bg_image:
            if hasattr(self, "_original_image") and self.gui._original_image:
                self._raw_bg_image = self.gui._original_image
            else:
                return

        # Get the current canvas dimensions
        if not hasattr(self.gui, "video_display") or not self.gui.video_display:
            return
        canvas_width = self.gui.video_display.canvas.winfo_width()
        canvas_height = self.gui.video_display.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            return

        # Re-scale and center the background image using the new method
        try:
            self._draw_bg_image_to_canvas()
            # After updating the background, redraw any zones that exist
            if hasattr(self.gui, "controller") and self.gui.controller:
                self.redraw_zones_from_project_data()
        except Exception as e:
            log.warning("canvas_manager.canvas_configure_error", error=str(e))

    def _display_image_on_canvas(self):
        """Display the original image on the canvas with proper scaling.

        Similar to _draw_bg_image_to_canvas but uses _original_image attribute.
        """
        if not hasattr(self.gui, "_original_image") or not self.gui._original_image:
            return

        # Get actual canvas dimensions after layout
        canvas_width = self.gui.video_display.canvas.winfo_width()
        canvas_height = self.gui.video_display.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            # Canvas not ready yet, try again
            self.gui.root.after(10, self._display_image_on_canvas)
            return

        # Calculate scaling to fit image while maintaining aspect ratio
        img_w, img_h = self.gui._original_image.size
        scale = min(canvas_width / img_w, canvas_height / img_h, 1.0)
        new_width = int(img_w * scale)
        new_height = int(img_h * scale)

        # Scale the image
        image = self.gui._original_image.resize((new_width, new_height), Image.LANCZOS)

        # Clear canvas and display centered image
        self.gui.video_display.canvas.delete("all")
        self._canvas_bg_image = ImageTk.PhotoImage(image)

        # Center the image within the canvas
        center_x = canvas_width // 2
        center_y = canvas_height // 2

        # Store positioning for later restoration in redraw_zones_from_project_data
        self._canvas_bg_position = (center_x, center_y, "center")

        self.gui.video_display.canvas.create_image(
            center_x,
            center_y,
            anchor="center",
            image=self._canvas_bg_image,
            tags="background_image",
        )

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

    # ========== Interactive Polygon Drawing Methods ==========

    def _draw_interactive_polygon(self):
        """Redraw the polygon and its handles based on current points.

        This method:
        - Clears previous interactive drawings
        - Converts video coordinates to canvas coordinates
        - Draws the polygon outline
        - Draws handles (vertices) with appropriate colors
        - Binds mouse events to each handle for dragging
        - Shows visual feedback for vertices on arena boundary (ROI editing)
        """
        # Clear previous drawings
        self.gui.video_display.canvas.delete(
            "interactive_polygon", "handle", "edit_clamp_indicator"
        )

        # Convert video coordinates to canvas coordinates for display
        canvas_points = []
        for point in self.gui.edited_polygon_points:
            canvas_point = self._video_to_canvas(point[0], point[1])
            canvas_points.append([canvas_point[0], canvas_point[1]])

        # Draw the polygon itself using canvas coordinates
        flat_points = [coord for point in canvas_points for coord in point]
        self.gui.interactive_polygon_item = self.gui.video_display.canvas.create_polygon(
            flat_points,
            fill="",
            outline="yellow",
            width=2,
            tags="interactive_polygon",
        )

        # Draw the handles using canvas coordinates
        self.gui.polygon_handles = []
        for i, canvas_point in enumerate(canvas_points):
            x, y = canvas_point[0], canvas_point[1]

            # Check if this vertex is on the arena boundary (for visual feedback)
            is_on_boundary = False
            if (
                isinstance(self.gui.current_editing_zone, tuple)
                and self.gui.current_editing_zone[0] == "roi"
            ):
                zone_data = self.gui._get_zone_data_for_active_context()
                main_arena_poly = zone_data.polygon if zone_data else None
                if main_arena_poly:
                    canvas_arena_poly = []
                    for point in main_arena_poly:
                        canvas_pt = self._video_to_canvas(point[0], point[1])
                        canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                    arena_array = np.array(canvas_arena_poly, dtype=np.float32)
                    result = cv2.pointPolygonTest(arena_array, (x, y), True)

                    # Consider point on boundary if very close to edge (distance ~0)
                    is_on_boundary = abs(result) < 1.0

            # Choose handle color based on whether it's clamped to boundary
            handle_fill = "orange" if is_on_boundary else "darkgoldenrod"
            handle_outline = "red" if is_on_boundary else "yellow"

            handle = self.gui.video_display.canvas.create_rectangle(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill=handle_fill,
                outline=handle_outline,
                tags=("handle", f"handle-{i}"),
            )
            self.gui.polygon_handles.append(handle)

            # Draw an additional indicator circle for clamped vertices
            if is_on_boundary:
                self.gui.video_display.canvas.create_oval(
                    x - 8,
                    y - 8,
                    x + 8,
                    y + 8,
                    outline="orange",
                    width=2,
                    tags="edit_clamp_indicator",
                )

            # Bind events to each handle
            self.gui.video_display.canvas.tag_bind(
                handle, "<ButtonPress-1>", lambda e, i=i: self.gui._on_handle_press(e, i)
            )
            self.gui.video_display.canvas.tag_bind(
                handle, "<B1-Motion>", self.gui._on_handle_drag
            )
            self.gui.video_display.canvas.tag_bind(
                handle, "<ButtonRelease-1>", self.gui._on_handle_release
            )

    def _redraw_polygon_in_progress(self):
        """Redraw the polygon vertices and edges after undo/redo.

        This method is used during polygon drawing mode to update the display
        when points are added, removed (undo), or restored (redo).
        """
        # Clear existing drawing aids
        self.gui.video_display.canvas.delete("drawing_aid")

        current_points = self.gui.drawing_state_manager.current_points

        # Redraw all vertices
        for canvas_x, canvas_y in current_points:
            self.gui.video_display.canvas.create_oval(
                canvas_x - 2,
                canvas_y - 2,
                canvas_x + 2,
                canvas_y + 2,
                fill="red",
                outline="red",
                tags=("temp_vertex", "drawing_aid"),
            )

        # Redraw all edges
        for i in range(len(current_points) - 1):
            p1 = current_points[i]
            p2 = current_points[i + 1]
            self.gui.video_display.canvas.create_line(
                p1[0], p1[1], p2[0], p2[1], fill="cyan", width=2, tags="drawing_aid"
            )

    # ========== Zone Drawing Methods ==========

    def _draw_zones_on_frame(self, frame):
        """Draw the arena and saved ROIs on the video frame.

        Args:
            frame: OpenCV frame (BGR format)

        Returns:
            frame: Frame with zones drawn on it
        """
        zone_data = self.gui._get_zone_data_for_active_context()
        if zone_data.polygon:
            pts = np.array(zone_data.polygon, np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(
                frame, [pts], isClosed=True, color=(0, 255, 255), thickness=2
            )  # Yellow for the main arena

        for i, polygon in enumerate(zone_data.roi_polygons):
            color = (
                zone_data.roi_colors[i] if i < len(zone_data.roi_colors) else (0, 255, 0)
            )  # Default to green
            pts = np.array(polygon, np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
        return frame

    def redraw_zones_from_project_data(self, zone_data=None):
        """Redraw zones preserving the background.

        This is a key method for updating the canvas display after zone changes.
        It:
        - Clears old zone drawings (but preserves background)
        - Restores background image if needed
        - Draws main arena polygon
        - Draws all ROI polygons with labels
        - Updates the zone listbox

        Args:
            zone_data: ZoneData object (optional, will fetch from context if None)
        """
        log.info("gui.redraw_zones.start")

        # Use video_display.canvas (Phase 6 fix)
        canvas = self.gui.video_display.canvas if self.gui.video_display else None
        if canvas is None:
            log.warning("gui.redraw_zones.no_canvas")
            return

        # Phase 4: Stop if zone_data is None (don't pull from controller)
        if zone_data is None:
            zone_data = self.gui._get_zone_data_for_active_context()
            if zone_data is None:
                log.warning("gui.redraw_zones.no_zone_data")
                return

        # Clear only zone elements, preserve background
        for tag in [
            "main_polygon",
            "roi_polygon",
            "roi_label",
            "roi_label_bg",
            "elastic_line",
            "drawing_aid",
            "temp_vertex",
        ]:
            canvas.delete(tag)

        # Background should already be present, if not, try to restore
        if self._canvas_bg_image:
            # Check if the image is still on canvas
            bg_items = canvas.find_withtag("background_image")
            if not bg_items:
                # Use stored positioning if available, otherwise default to center
                if hasattr(self, "_canvas_bg_position"):
                    x, y, anchor = self._canvas_bg_position
                else:
                    # Fallback to center of current canvas
                    canvas_width = canvas.winfo_width() or 800
                    canvas_height = canvas.winfo_height() or 600
                    x, y, anchor = canvas_width // 2, canvas_height // 2, "center"

                canvas.create_image(
                    x,
                    y,
                    anchor=anchor,
                    image=self._canvas_bg_image,
                    tags="background_image",
                )
                canvas.tag_lower("background_image")  # Send to back
                log.info("gui.redraw_zones.background_restored")
        else:
            log.warning("gui.redraw_zones.no_background_image")
            # Try to load a frame if there's no background image
            self.load_video_frame_to_canvas()

        log.info(
            "gui.redraw_zones.zone_data_loaded",
            has_main_polygon=bool(zone_data.polygon),
            roi_count=len(zone_data.roi_polygons),
        )

        # Draw main polygon
        if zone_data.polygon and len(zone_data.polygon) >= 3:
            try:
                # Convert video coordinates to canvas coordinates
                canvas_polygon = []
                for point in zone_data.polygon:
                    canvas_point = self._video_to_canvas(point[0], point[1])
                    canvas_polygon.extend([canvas_point[0], canvas_point[1]])

                canvas.create_polygon(
                    canvas_polygon,
                    fill="",
                    outline="cyan",
                    width=2,
                    tags="main_polygon",
                )
                log.info("gui.main_polygon.drawn", points=len(zone_data.polygon))
            except Exception as e:
                log.error("gui.main_polygon.draw_error", error=str(e))

        # Draw ROI polygons with visual improvements
        for i, polygon in enumerate(zone_data.roi_polygons):
            if len(polygon) < 3:
                continue

            # ROI color (stored in BGR for OpenCV)
            color_bgr = zone_data.roi_colors[i] if i < len(zone_data.roi_colors) else (0, 255, 0)
            # Convert BGR to RGB for Tkinter hex color
            color_hex = f"#{color_bgr[2]:02x}{color_bgr[1]:02x}{color_bgr[0]:02x}"

            # ROI name
            name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i + 1}"

            # Draw polygon with specific tags
            try:
                # Convert video coordinates to canvas coordinates
                canvas_polygon = []
                for point in polygon:
                    canvas_point = self._video_to_canvas(point[0], point[1])
                    canvas_polygon.extend([canvas_point[0], canvas_point[1]])

                # Create the polygon
                canvas.create_polygon(
                    canvas_polygon,
                    fill="",  # No fill to maintain transparency
                    outline=color_hex,
                    width=2,
                    tags=("roi_polygon", f"roi_{i}"),
                )

                # Add label with the name at the center of the polygon
                # Calculate center using canvas coordinates
                poly_array = np.array(
                    [
                        (canvas_polygon[i], canvas_polygon[i + 1])
                        for i in range(0, len(canvas_polygon), 2)
                    ]
                )
                center_x = int(poly_array[:, 0].mean())
                center_y = int(poly_array[:, 1].mean())

                # Create semi-transparent background for better readability
                canvas.create_oval(
                    center_x - 25,
                    center_y - 10,
                    center_x + 25,
                    center_y + 10,
                    fill="white",
                    outline=color_hex,
                    width=1,
                    tags=("roi_label_bg", f"roi_label_bg_{i}"),
                )

                # Create the text of the name
                canvas.create_text(
                    center_x,
                    center_y,
                    text=name,
                    fill=color_hex,
                    font=("Arial", 9, "bold"),
                    tags=("roi_label", f"roi_label_{i}"),
                )

                log.info("gui.roi_drawn", name=name, color=color_hex, points=len(polygon))

            except Exception as e:
                log.error("gui.roi_draw_error", name=name, error=str(e), index=i)

        # Update listbox
        self.gui.update_zone_listbox(zone_data)

        log.info("gui.redraw_zones.complete")

    # ========== Frame Display Methods ==========

    def display_frame(self, frame):
        """Display a video frame inside the GUI, with overlays.

        Args:
            frame: OpenCV frame (BGR format)

        This method routes to display_analysis_frame if analysis is active,
        otherwise displays the frame normally with zone overlays.
        """
        # If analysis is active, route to analysis display
        if self.gui.analysis_active:
            self.display_analysis_frame(frame)
            return

        try:
            # Original behavior for non-analysis display
            # Draw zones before displaying
            frame_with_zones = self._draw_zones_on_frame(frame.copy())

            # Convert and embed
            frame_rgb = cv2.cvtColor(frame_with_zones, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            if self.gui.video_label:
                self.gui.video_label.configure(image=imgtk)
                self.gui.video_label.image = imgtk  # keep reference
        except Exception:
            # Fallback to OpenCV window if Pillow not installed or other error
            try:
                cv2.imshow("Preview", frame)
                cv2.waitKey(1)
            except Exception:
                pass

    def display_analysis_frame(self, frame):
        """Display analysis frame in the overlay instead of separate progress bar.

        Args:
            frame: OpenCV frame (BGR format)

        This method:
        - Draws zones on the frame
        - Stores the frame for later re-rendering with updated detections
        - Calls _render_last_analysis_frame to show the frame with current detections
        """
        try:
            # Store the original frame with zones only (before detection overlay)
            # so we can redraw detections when they update
            frame_with_zones = self._draw_zones_on_frame(frame.copy())
            self.gui._last_analysis_frame = frame_with_zones.copy()

            # Now render with current detections
            self._render_last_analysis_frame()
        except Exception:
            # Fallback to OpenCV window if Pillow not installed or other error
            try:
                cv2.imshow("Preview", frame)
                cv2.waitKey(1)
            except Exception:
                pass

    # ========== Detection Overlay Methods ==========

    def _draw_detections_on_frame(self, frame):
        """Draw all current detections (bounding boxes, IDs, confidence) on the frame.

        Args:
            frame: OpenCV frame (BGR format)

        Returns:
            frame: Frame with detections drawn on it
        """
        if not hasattr(self.gui, "_current_detections") or not self.gui._current_detections:
            return frame

        for det in self.gui._current_detections:
            if len(det) < 7:  # Need at least x1, y1, x2, y2, conf, track_id, class_id
                continue

            try:
                x1, y1, x2, y2, conf, track_id = det[:6]
                x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))

                # Draw bounding box
                color = (0, 255, 0)  # Green color for all detections
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # Draw track ID and confidence
                label = f"ID {track_id}"
                if conf is not None:
                    label += f" {conf:.2f}"

                # Background for label
                (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (x1, y1 - label_h - 4), (x1 + label_w, y1), color, -1)

                # Text label
                cv2.putText(
                    frame,
                    label,
                    (x1, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 0, 0),  # Black text
                    1,
                )
            except (TypeError, ValueError):
                # Skip invalid detections
                continue

        return frame

    def _render_last_analysis_frame(self) -> None:
        """Render the last analysis frame with current detection overlays.

        This method is called whenever detections update or track selection changes.
        It:
        - Starts with the base frame (zones already drawn)
        - Draws all detections (bounding boxes with IDs)
        - Adds highlight overlay for selected track
        - Displays the final result
        """
        if self.gui._last_analysis_frame is None:
            return
        # Start with base frame (zones already drawn)
        frame = self.gui._last_analysis_frame.copy()
        # Draw all detections (bounding boxes with IDs)
        frame = self._draw_detections_on_frame(frame)
        # Add highlight overlay for selected track if needed
        frame = self._annotate_selected_tracks(frame)
        # Display final result
        self._show_analysis_frame_image(frame)

    def _annotate_selected_tracks(self, frame):
        """Add highlight overlay for the selected track.

        Args:
            frame: OpenCV frame (BGR format)

        Returns:
            frame: Frame with selected track highlighted
        """
        has_selector = hasattr(self.gui, "track_selector_var")
        selected = self.gui.track_selector_var.get() if has_selector else "Todos"
        selected = str(selected).strip()
        if not selected or selected.lower() == "todos":
            return frame

        for det in self.gui._current_detections:
            if len(det) < 6:
                continue
            # Only the first 6 elements are used for annotation; any extra elements are ignored.
            x1, y1, x2, y2, _, track_id = det[:6]
            if track_id is None or str(track_id).strip() != selected:
                continue
            try:
                x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
            except (TypeError, ValueError):
                continue
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 215, 255), 3)
            cv2.putText(
                frame,
                f"ID {track_id}",
                (x1, max(y1 - 8, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 215, 255),
                2,
            )

        return frame

    def _show_analysis_frame_image(self, frame) -> None:  # noqa: C901
        """Display frame image in analysis view with proper scaling.

        Args:
            frame: OpenCV frame (BGR format)

        This method handles complex scaling logic to fit the frame within
        the available space in the analysis tab, accounting for all UI controls.
        """
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        label = getattr(self.gui, "analysis_video_label", None)

        if label is None:
            return

        # Get actual frame dimensions
        frame_h, frame_w = frame.shape[:2]

        # Strategy: Use root window dimensions as reference since tab dimensions may not be updated
        available_width = None
        available_height = None

        # First, try to get the notebook (parent of analysis_tab_frame) dimensions
        if hasattr(self.gui, "notebook") and self.gui.notebook:
            self.gui.notebook.update_idletasks()
            notebook_width = self.gui.notebook.winfo_width()
            notebook_height = self.gui.notebook.winfo_height()

            log.info(
                "gui.notebook_dimensions",
                width=notebook_width,
                height=notebook_height,
                valid=notebook_width > 100 and notebook_height > 100,
            )

            if notebook_width > 100 and notebook_height > 100:
                # IMPROVED: Calculate actual controls height dynamically
                # Since info_frame and controls_frame are not stored as instance attrs,
                # measure from the stored child widgets and progress_frame
                controls_height = 0

                # Measure status label + task/metadata labels (info section)
                if hasattr(self.gui, "analysis_status_label") and self.gui.analysis_status_label:
                    self.gui.analysis_status_label.update_idletasks()
                    status_h = self.gui.analysis_status_label.winfo_height()
                    if status_h > 1:
                        controls_height += status_h + 5

                if hasattr(self.gui, "analysis_task_label") and self.gui.analysis_task_label:
                    self.gui.analysis_task_label.update_idletasks()
                    task_h = self.gui.analysis_task_label.winfo_height()
                    if task_h > 1:
                        controls_height += task_h + 5

                # Measure metadata labels frame height (group, day, subject, profile)
                if hasattr(self.gui, "analysis_group_label") and self.gui.analysis_group_label:
                    self.gui.analysis_group_label.update_idletasks()
                    meta_h = self.gui.analysis_group_label.winfo_height()
                    if meta_h > 1:
                        controls_height += meta_h + 5

                # Measure tracking mode label
                if hasattr(self.gui, "tracking_mode_label") and self.gui.tracking_mode_label:
                    self.gui.tracking_mode_label.update_idletasks()
                    mode_h = self.gui.tracking_mode_label.winfo_height()
                    if mode_h > 1:
                        controls_height += mode_h + 5

                # Measure track selector (controls section)
                if hasattr(self.gui, "track_selector_widget") and self.gui.track_selector_widget:
                    self.gui.track_selector_widget.update_idletasks()
                    ctrl_h = self.gui.track_selector_widget.winfo_height()
                    if ctrl_h > 1:
                        controls_height += ctrl_h + 15  # Extra padding for controls frame

                # Check if progress frame is visible and add its height
                if (
                    hasattr(self.gui, "progress_frame")
                    and self.gui.progress_frame
                    and self.gui.progress_frame.winfo_viewable()
                ):
                    self.gui.progress_frame.update_idletasks()
                    prog_h = self.gui.progress_frame.winfo_height()
                    if prog_h > 10:
                        controls_height += prog_h + 10

                # Fallback if measurements failed
                if controls_height < 50:
                    controls_height = 250  # More conservative fallback (was 200)

                # Account for notebook padding and frame padding
                available_width = notebook_width - 60  # 20 padding + 20 margins + 20 buffer
                available_height = (
                    notebook_height - controls_height - 80
                )  # Increased buffer (was 60)

                log.info(
                    "gui.controls_height.total",
                    total=controls_height,
                    available_height=available_height,
                )

                log.info(
                    "gui.frame_sizing",
                    frame_size=f"{frame_w}x{frame_h}",
                    notebook_size=f"{notebook_width}x{notebook_height}",
                    controls_h=controls_height,
                    available=f"{int(available_width)}x{int(available_height)}",
                )

        # Fallback: use video_container or label dimensions
        if (
            available_width is None
            or available_width <= 100
            or available_height is None
            or available_height <= 100
        ):
            if hasattr(self.gui, "video_container") and self.gui.video_container:
                self.gui.video_container.update_idletasks()
                available_width = self.gui.video_container.winfo_width() - 10
                available_height = self.gui.video_container.winfo_height() - 10
                log.info(
                    "gui.frame_sizing.fallback_container",
                    available=f"{int(available_width)}x{int(available_height)}",
                )

        # Apply scaling to fit available space
        if (
            available_width
            and available_height
            and available_width > 100
            and available_height > 100
        ):
            # Calculate scale to fit both dimensions
            scale = min(available_width / frame_w, available_height / frame_h)
            # Ensure we don't exceed available space (never upscale)
            scale = min(scale, 1.0)

            if scale < 1.0:
                resample_attr = getattr(Image, "Resampling", None)
                if resample_attr is not None:
                    resample = getattr(
                        resample_attr,
                        "LANCZOS",
                        getattr(
                            resample_attr,
                            "BICUBIC",
                            getattr(resample_attr, "BILINEAR", 0),
                        ),
                    )
                else:
                    resample = getattr(
                        Image,
                        "LANCZOS",
                        getattr(Image, "BICUBIC", getattr(Image, "BILINEAR", 0)),
                    )
                new_size = (
                    max(1, int(frame_w * scale)),
                    max(1, int(frame_h * scale)),
                )
                img = img.resize(new_size, resample=resample)

        imgtk = ImageTk.PhotoImage(image=img)
        self.gui._analysis_overlay_image = imgtk
        if label is not None:
            label.configure(image=imgtk)
            label.image = imgtk

    def update_zone_listbox(self, zone_data=None):
        """Update zone listbox with visual color indicators."""
        # Guard against missing zone_listbox (Phase 6 fix: use zone_controls)
        listbox = self.gui.zone_controls.zone_listbox if self.gui.zone_controls else None
        if not listbox:
            return

        # Clear list
        for item in listbox.get_children():
            listbox.delete(item)

        # Phase 4: Stop if zone_data is None (don't pull from controller)
        if zone_data is None:
            zone_data = self.gui._get_zone_data_for_active_context()
            if zone_data is None:
                log.warning("gui.update_zone_listbox.no_zone_data")
                return

        # Main arena with emoji and color
        if zone_data.polygon:
            listbox.insert(
                "",
                "end",
                values=("🏠 Arena Principal", "Polígono", "Ciano"),
                tags=("arena",),
            )
            # Configure text color for arena
            listbox.tag_configure("arena", foreground="darkcyan")

        # Enable/disable ROI button based on arena existence
        self.gui._enable_roi_button_if_arena_exists(zone_data)

        # Map BGR colors (OpenCV format) to names and hex
        color_map = {
            (0, 255, 0): ("Verde", "#00AA00"),
            (255, 0, 0): ("Azul", "#0000AA"),  # BGR: (255, 0, 0) = Blue
            (0, 0, 255): ("Vermelho", "#AA0000"),  # BGR: (0, 0, 255) = Red
            (0, 255, 255): ("Amarelo", "#AAAA00"),  # BGR: (0, 255, 255) = Yellow
            (255, 0, 255): ("Magenta", "#AA00AA"),  # BGR: (255, 0, 255) = Magenta
            (255, 255, 0): ("Ciano", "#00AAAA"),  # BGR: (255, 255, 0) = Cyan
        }

        # ROIs with emojis, colors and tags
        for i, name in enumerate(zone_data.roi_names):
            # Get ROI color if available
            color_name = "Verde"
            color_hex = "#00AA00"

            if i < len(zone_data.roi_colors):
                roi_color = tuple(zone_data.roi_colors[i])
                color_info = color_map.get(roi_color, ("Verde", "#00AA00"))
                color_name = color_info[0]
                color_hex = color_info[1]

            # Insert ROI with emoji
            listbox.insert(
                "",
                "end",
                values=(f"📍 {name}", "Área de Interesse", color_name),
                tags=(f"roi_{i}",),
            )

            # Configure text color for ROI
            try:
                listbox.tag_configure(f"roi_{i}", foreground=color_hex)
            except Exception:
                pass  # Silent fallback if color not supported

    def start_polygon_drawing(self):
        """Activates polygon drawing mode."""
        # Garante que há frame no canvas
        if self.gui._canvas_bg_image is None:
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

        self.gui.video_display.canvas.config(cursor="crosshair")
        self.gui.video_display.canvas.bind("<Button-1>", self.gui._on_canvas_click)
        self.gui.video_display.canvas.bind("<B1-Motion>", self.gui._on_vertex_drag_motion)
        self.gui.video_display.canvas.bind("<ButtonRelease-1>", self.gui._on_vertex_drag_end)
        self.gui.video_display.canvas.bind(
            "<Double-Button-1>", self.gui._on_canvas_double_click
        )
        self.gui.video_display.canvas.bind("<Motion>", self.gui._on_canvas_motion)

        # Bind keyboard shortcuts for undo/redo
        self.gui.video_display.canvas.bind("<Control-z>", self.gui._on_drawing_undo)
        self.gui.video_display.canvas.bind("<Control-y>", self.gui._on_drawing_redo)
        self.gui.video_display.canvas.bind(
            "<Control-Shift-Z>", self.gui._on_drawing_redo
        )  # Alternative
        self.gui.video_display.canvas.focus_set()  # Ensure canvas can receive keyboard events

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

    def handle_vertex_drag(self, event):
        """Update the polygon point and redraw as the handle is dragged."""
        if self.gui._dragged_handle_index is None:
            return

        # Apply the drag offset to get the actual handle position
        canvas_x = float(event.x) + self.gui._drag_offset[0]
        canvas_y = float(event.y) + self.gui._drag_offset[1]

        # Apply snapping to nearby vertices or edges
        snapped_point = self.gui._apply_snapping(canvas_x, canvas_y, exclude_current_polygon=True)
        if snapped_point:
            canvas_x, canvas_y = snapped_point

        # If editing an ROI, clamp the point within the main arena
        if (
            isinstance(self.gui.current_editing_zone, tuple)
            and self.gui.current_editing_zone[0] == "roi"
        ):
            main_arena_poly = self.gui._get_zone_data_for_active_context().polygon
            if main_arena_poly:
                # Convert main arena polygon from video coords to canvas coords
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                # Use GeometryService for clamping
                canvas_x, canvas_y = GeometryService.clamp_point_to_polygon(
                    (canvas_x, canvas_y), canvas_arena_poly
                )

        # Clamp to canvas bounds for all zones (arena and ROI)
        canvas_width = self.gui.video_display.canvas.winfo_width() or 800
        canvas_height = self.gui.video_display.canvas.winfo_height() or 600
        canvas_x = max(0, min(canvas_x, canvas_width))
        canvas_y = max(0, min(canvas_y, canvas_height))

        # Convert canvas coordinates to video coordinates before storing
        video_point = self._canvas_to_video(canvas_x, canvas_y)
        self.gui.edited_polygon_points[self.gui._dragged_handle_index] = [
            video_point[0],
            video_point[1],
        ]

        # Redraw the entire interactive polygon and its handles
        self._draw_interactive_polygon()

    def handle_canvas_click(self, event):
        """Handle single clicks on the canvas during polygon drawing."""
        if self.gui.drawing_state_manager.mode != "polygon":
            return

        # Get canvas coordinates directly from event
        canvas_x = float(event.x)
        canvas_y = float(event.y)

        # Check if clicking on an existing vertex (for dragging)
        if self.gui.drawing_state_manager.has_points():
            for i, (vx, vy) in enumerate(self.gui.drawing_state_manager.current_points):
                dist = ((canvas_x - vx) ** 2 + (canvas_y - vy) ** 2) ** 0.5
                if dist <= self.gui.drawing_state_manager.vertex_hover_tolerance:
                    # Start dragging this vertex
                    self.gui.drawing_state_manager.dragging_vertex_index = i
                    self.gui.video_display.canvas.config(cursor="hand2")
                    return  # Don't add new point

        # Not over a vertex, proceed to add new point
        # Apply snapping to nearby vertices or edges
        snapped_point = self.gui._apply_snapping(canvas_x, canvas_y)
        if snapped_point:
            canvas_x, canvas_y = snapped_point

        # If drawing an ROI, clamp the point inside the main arena
        if self.gui.drawing_state_manager.drawing_type == "roi":
            main_arena_poly = self.gui._get_zone_data_for_active_context().polygon
            if main_arena_poly:
                # Convert main arena polygon from video coords to canvas coords
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                # Use GeometryService for clamping
                canvas_x, canvas_y = GeometryService.clamp_point_to_polygon(
                    (canvas_x, canvas_y), canvas_arena_poly
                )
                log.debug(
                    "roi_click_clamped",
                    original=(float(event.x), float(event.y)),
                    clamped=(canvas_x, canvas_y),
                )

        # Add point to state manager
        canvas_point = (canvas_x, canvas_y)
        video_point = self._canvas_to_video(canvas_x, canvas_y)

        self.gui.drawing_state_manager.add_point(canvas_point, video_point, canvas_point)

        # Draw a small circle to mark the vertex
        self.gui.video_display.canvas.create_oval(
            canvas_x - 2,
            canvas_y - 2,
            canvas_x + 2,
            canvas_y + 2,
            fill="red",
            outline="red",
            tags=("temp_vertex", "drawing_aid"),
        )
        # Draw the fixed line segment if it's not the first point
        current_points = self.gui.drawing_state_manager.current_points
        if len(current_points) > 1:
            p1 = current_points[-2]
            p2 = current_points[-1]
            self.gui.video_display.canvas.create_line(
                p1[0], p1[1], p2[0], p2[1], fill="cyan", width=2, tags="drawing_aid"
            )

    def edit_selected_zone_vertices(self):
        """Enable interactive editing of the selected zone's vertices."""
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
            self.gui.setup_interactive_polygon(polygon_points)
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
                self.gui.setup_interactive_polygon(polygon_points)
                self.gui.current_editing_zone = ("roi", roi_index, roi_name)
                self.gui.set_status(
                    f"Editando vértices da ROI '{roi_name}'. Arraste os pontos amarelos."
                )

            except (ValueError, IndexError):
                self.gui.show_error("Erro", f"ROI '{roi_name}' não encontrada.")
                return

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
        self.gui.video_display.canvas.config(cursor="")
        # Unbind all possible drawing events
        self.gui.video_display.canvas.unbind("<Button-1>")
        self.gui.video_display.canvas.unbind("<Double-Button-1>")
        self.gui.video_display.canvas.unbind("<Motion>")
        self.gui.video_display.canvas.unbind("<ButtonPress-1>")
        self.gui.video_display.canvas.unbind("<B1-Motion>")
        self.gui.video_display.canvas.unbind("<ButtonRelease-1>")
        # Unbind keyboard shortcuts
        self.gui.video_display.canvas.unbind("<Control-z>")
        self.gui.video_display.canvas.unbind("<Control-y>")
        self.gui.video_display.canvas.unbind("<Control-Shift-Z>")

        self.gui.video_display.canvas.delete("elastic_line")
        self.gui.video_display.canvas.delete("drawing_aid")  # Deletes both vertices and fixed lines
        self.gui.video_display.canvas.delete("snap_indicator")  # Clear snap indicators

        # Clear coordinate lists
        self.gui.drawing_state_manager.clear_points()

        self.gui.set_status("Pronto.")

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

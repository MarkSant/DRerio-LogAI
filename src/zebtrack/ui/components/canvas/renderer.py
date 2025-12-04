"""
Canvas Renderer Component.

Handles drawing operations on the canvas, including background images,
zones (arena/ROIs), detection overlays, and interactive polygons.
"""

import cv2
import numpy as np
import structlog
from PIL import Image, ImageTk

log = structlog.get_logger()


class CanvasRenderer:
    """Handles drawing operations on the canvas."""

    def __init__(self, canvas_manager):
        """Initialize CanvasRenderer.

        Args:
            canvas_manager: Reference to parent CanvasManager
        """
        self.manager = canvas_manager
        self.gui = canvas_manager.gui

    def draw_bg_image(self):
        """Draw the background image to canvas with proper scaling and centering."""
        if not hasattr(self.manager, "_raw_bg_image") or not self.manager._raw_bg_image:
            if hasattr(self.gui, "_original_image") and self.gui._original_image:
                self.manager._raw_bg_image = self.gui._original_image
            else:
                return

        # Get actual canvas dimensions after layout
        canvas_width = self.gui.video_display.canvas.winfo_width()
        canvas_height = self.gui.video_display.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            # Canvas not ready yet, try again
            self.gui.root.after(10, self.draw_bg_image)
            return

        # Calculate scaling to fit image while maintaining aspect ratio
        img_w, img_h = self.manager._raw_bg_image.size
        scale = min(canvas_width / img_w, canvas_height / img_h, 1.0)
        new_width = int(img_w * scale)
        new_height = int(img_h * scale)

        # Store scaling information for coordinate conversion
        self.manager._bg_scale = scale
        self.manager._bg_img_size = (img_w, img_h)

        # Calculate offset (top-left position of scaled image in canvas)
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        offset_x = center_x - new_width // 2
        offset_y = center_y - new_height // 2
        self.manager._bg_offset = (offset_x, offset_y)

        # Scale the image
        image = self.manager._raw_bg_image.resize((new_width, new_height), Image.LANCZOS)

        # Clear canvas and display centered image
        self.gui.video_display.canvas.delete("all")
        self.manager._canvas_bg_image = ImageTk.PhotoImage(image)

        # Store positioning for later restoration
        self.manager._canvas_bg_position = (center_x, center_y, "center")

        self.gui.video_display.canvas.create_image(
            center_x,
            center_y,
            anchor="center",
            image=self.manager._canvas_bg_image,
            tags="background_image",
        )

    def redraw_zones(self, zone_data=None):
        """Redraw zones preserving the background."""
        log.info("gui.redraw_zones.start")

        canvas = self.gui.video_display.canvas if self.gui.video_display else None
        if canvas is None:
            log.warning("gui.redraw_zones.no_canvas")
            return

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
        if self.manager._canvas_bg_image:
            bg_items = canvas.find_withtag("background_image")
            if not bg_items:
                if (
                    hasattr(self.manager, "_canvas_bg_position")
                    and self.manager._canvas_bg_position
                ):
                    x, y, anchor = self.manager._canvas_bg_position
                else:
                    canvas_width = canvas.winfo_width() or 800
                    canvas_height = canvas.winfo_height() or 600
                    x, y, anchor = canvas_width // 2, canvas_height // 2, "center"

                canvas.create_image(
                    x,
                    y,
                    anchor=anchor,
                    image=self.manager._canvas_bg_image,
                    tags="background_image",
                )
                canvas.tag_lower("background_image")
                log.info("gui.redraw_zones.background_restored")
        else:
            log.warning("gui.redraw_zones.no_background_image")
            # Try to load a frame if there's no background image
            self.manager.load_video_frame_to_canvas()

        # Draw main polygon
        if zone_data.polygon and len(zone_data.polygon) >= 3:
            try:
                canvas_polygon = []
                for point in zone_data.polygon:
                    canvas_point = self.manager._video_to_canvas(point[0], point[1])
                    canvas_polygon.extend([canvas_point[0], canvas_point[1]])

                canvas.create_polygon(
                    canvas_polygon,
                    fill="",
                    outline="cyan",
                    width=2,
                    tags="main_polygon",
                )
            except Exception as e:
                log.error("gui.main_polygon.draw_error", error=str(e))

        # Draw ROI polygons
        for i, polygon in enumerate(zone_data.roi_polygons):
            if len(polygon) < 3:
                continue

            color_bgr = zone_data.roi_colors[i] if i < len(zone_data.roi_colors) else (0, 255, 0)
            color_hex = f"#{color_bgr[2]:02x}{color_bgr[1]:02x}{color_bgr[0]:02x}"
            name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i + 1}"

            try:
                canvas_polygon = []
                for point in polygon:
                    canvas_point = self.manager._video_to_canvas(point[0], point[1])
                    canvas_polygon.extend([canvas_point[0], canvas_point[1]])

                canvas.create_polygon(
                    canvas_polygon,
                    fill="",
                    outline=color_hex,
                    width=2,
                    tags=("roi_polygon", f"roi_{i}"),
                )

                # Add label
                poly_array = np.array(
                    [
                        (canvas_polygon[i], canvas_polygon[i + 1])
                        for i in range(0, len(canvas_polygon), 2)
                    ]
                )
                center_x = int(poly_array[:, 0].mean())
                center_y = int(poly_array[:, 1].mean())

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

                canvas.create_text(
                    center_x,
                    center_y,
                    text=name,
                    fill=color_hex,
                    font=("Arial", 9, "bold"),
                    tags=("roi_label", f"roi_label_{i}"),
                )

            except Exception as e:
                log.error("gui.roi_draw_error", name=name, error=str(e), index=i)

        # Note: We do NOT publish ZONES_UPDATED here because redraw_zones is usually
        # the *result* of that event. Publishing it would cause an infinite loop.
        # The component initiating the change (e.g. DialogManager) is responsible for publishing.

        log.info("gui.redraw_zones.complete")

    def update_overlay(self, detections, is_single_subject=False):
        """Draw detection overlays on the canvas.

        NOTE: This method draws on video_display.canvas which is the ZONE tab canvas.
        During analysis, detection overlays are already drawn by detector.draw_overlay()
        and displayed via canvas_manager.update_video_frame() on the analysis_display_widget.

        This method should NOT draw on the zone canvas during analysis to avoid
        bboxes appearing over the zone drawing area.

        Args:
            detections: List of detections (x1, y1, x2, y2, conf, track_id, class_id)
            is_single_subject: Boolean flag for single subject mode style
        """
        # Skip drawing overlays on zone canvas during active analysis
        # The analysis tab has its own display with overlays already rendered on the frame
        if getattr(self.gui, 'analysis_active', False):
            return

        canvas = self.gui.video_display.canvas if self.gui.video_display else None
        if not canvas:
            return

        # Clear previous overlays
        canvas.delete("detection_overlay")

        if not detections:
            return

        for det in detections:
            try:
                # Unpack detection (support both 6 and 7 element tuples)
                if len(det) == 6:
                    x1, y1, x2, y2, conf, track_id = det
                    class_id = 0
                else:
                    x1, y1, x2, y2, conf, track_id, class_id = det

                # Convert to canvas coordinates
                cx1, cy1 = self.manager._video_to_canvas(x1, y1)
                cx2, cy2 = self.manager._video_to_canvas(x2, y2)

                # Style configuration
                color = "magenta" if is_single_subject else "cyan"
                if class_id == 0: # Aquarium
                    color = "yellow"

                # Draw bounding box
                canvas.create_rectangle(
                    cx1, cy1, cx2, cy2,
                    outline=color,
                    width=2,
                    tags="detection_overlay"
                )

                # Draw label
                label_text = f"ID: {track_id}" if track_id is not None else "Det"
                if is_single_subject:
                    label_text = "Alvo"

                # Text background
                canvas.create_text(
                    cx1, cy1 - 10,
                    text=label_text,
                    fill=color,
                    anchor="sw",
                    font=("Arial", 10, "bold"),
                    tags="detection_overlay"
                )

            except Exception as e:
                log.error("renderer.overlay_draw_error", error=str(e))

    def draw_interactive_polygon(self):
        """Redraw the polygon and its handles based on current points."""
        self.gui.video_display.canvas.delete(
            "interactive_polygon", "handle", "edit_clamp_indicator"
        )

        canvas_points = []
        for point in self.gui.edited_polygon_points:
            canvas_point = self.manager._video_to_canvas(point[0], point[1])
            canvas_points.append([canvas_point[0], canvas_point[1]])

        flat_points = [coord for point in canvas_points for coord in point]
        self.gui.interactive_polygon_item = self.gui.video_display.canvas.create_polygon(
            flat_points,
            fill="",
            outline="yellow",
            width=2,
            tags="interactive_polygon",
        )

        self.gui.polygon_handles = []
        for i, canvas_point in enumerate(canvas_points):
            x, y = canvas_point[0], canvas_point[1]

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
                        canvas_pt = self.manager._video_to_canvas(point[0], point[1])
                        canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                    arena_array = np.array(canvas_arena_poly, dtype=np.float32)
                    result = cv2.pointPolygonTest(arena_array, (x, y), True)
                    is_on_boundary = abs(result) < 1.0

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

            self.gui.video_display.canvas.tag_bind(
                handle, "<ButtonPress-1>", lambda e, i=i: self.gui._on_handle_press(e, i)
            )
            self.gui.video_display.canvas.tag_bind(handle, "<B1-Motion>", self.gui._on_handle_drag)
            self.gui.video_display.canvas.tag_bind(
                handle, "<ButtonRelease-1>", self.gui._on_handle_release
            )

    def redraw_polygon_in_progress(self):
        """Redraw the polygon vertices and edges after undo/redo."""
        self.gui.video_display.canvas.delete("drawing_aid")

        current_points = self.gui.drawing_state_manager.current_points

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

        for i in range(len(current_points) - 1):
            p1 = current_points[i]
            p2 = current_points[i + 1]
            self.gui.video_display.canvas.create_line(
                p1[0], p1[1], p2[0], p2[1], fill="cyan", width=2, tags="drawing_aid"
            )

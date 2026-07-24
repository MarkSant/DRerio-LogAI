"""
Canvas Renderer Component.

Handles drawing operations on the canvas, including background images,
zones (arena/ROIs), detection overlays, and interactive polygons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
import structlog
from PIL import Image, ImageTk

if TYPE_CHECKING:
    from zebtrack.core.services.zone_context_service import ZoneContextService

log = structlog.get_logger()


class CanvasRenderer:
    """Handles drawing operations on the canvas."""

    def __init__(self, canvas_manager, *, zone_context_service: ZoneContextService | None = None):
        """Initialize CanvasRenderer.

        Args:
            canvas_manager: Reference to parent CanvasManager
            zone_context_service: Optional ZoneContextService for dependency injection.
        """
        self.manager = canvas_manager
        self.gui = canvas_manager.gui
        self._zone_context_service = zone_context_service

    @property
    def zone_context_service(self):
        """ZoneContextService instance (injected or resolved from gui)."""
        if self._zone_context_service is not None:
            return self._zone_context_service
        return getattr(self.gui, "_zone_context_service", None)

    def _get_canvas(self):
        """Get the canvas safely, returning None if video_display doesn't exist or is destroyed."""
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

    def draw_bg_image(self):
        """Draw the background image to canvas with proper scaling and centering."""
        canvas = self._get_canvas()
        if canvas is None:
            log.debug("draw_bg_image.no_canvas_yet")
            return

        if not hasattr(self.manager, "_raw_bg_image") or not self.manager._raw_bg_image:
            if hasattr(self.gui, "_original_image") and self.gui._original_image:
                self.manager._raw_bg_image = self.gui._original_image
            else:
                return

        # Get actual canvas dimensions after layout
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()

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
        resampling: Any
        if hasattr(Image, "Resampling"):
            resampling = Image.Resampling.LANCZOS
        else:
            resampling = getattr(Image, "NEAREST", 0)
        image = self.manager._raw_bg_image.resize((new_width, new_height), resampling)

        # Clear canvas and display centered image
        canvas.delete("all")
        self.manager._canvas_bg_image = ImageTk.PhotoImage(image)

        # Store positioning for later restoration
        self.manager._canvas_bg_position = (center_x, center_y, "center")

        canvas.create_image(
            center_x,
            center_y,
            anchor="center",
            image=self.manager._canvas_bg_image,
            tags="background_image",
        )

    def redraw_zones(self, zone_data=None):
        """Redraw zones preserving the background."""
        log.info("gui.redraw_zones.start")

        canvas = self._get_canvas()
        if canvas is None:
            log.warning("gui.redraw_zones.no_canvas")
            return

        if zone_data is None:
            zone_data = self.zone_context_service.get_zone_data_for_active_context()
            if zone_data is None:
                log.warning("gui.redraw_zones.no_zone_data")
                return

        self._clear_zone_elements(canvas)
        self._ensure_background(canvas)

        if not self._has_background_geometry():
            log.debug("gui.redraw_zones.waiting_for_background")
            return

        self._draw_geotaxis_overlay()

        # Handle Multi-Aquarium Data
        from zebtrack.core.detection import MultiAquariumZoneData

        if isinstance(zone_data, MultiAquariumZoneData):
            self._draw_multi_aquarium_zones(canvas, zone_data)
            return

        # Draw main polygon (Single Aquarium)
        self._draw_single_aquarium_zones(canvas, zone_data)

        log.info("gui.redraw_zones.complete")

    def _has_background_geometry(self) -> bool:
        """Return whether a displayed frame has valid canvas coordinates."""
        return bool(
            getattr(self.manager, "_raw_bg_image", None)
            and getattr(self.manager, "_canvas_bg_image", None)
            and getattr(self.manager, "_bg_scale", None) is not None
            and getattr(self.manager, "_bg_offset", None) is not None
        )

    def _clear_zone_elements(self, canvas):
        """Clear only zone elements, preserving background."""
        for tag in [
            "main_polygon",
            "roi_polygon",
            "roi_label",
            "roi_label_bg",
            "elastic_line",
            "drawing_aid",
            "temp_vertex",
            "geotaxis_zone",
        ]:
            canvas.delete(tag)

    def _ensure_background(self, canvas):
        """Ensure background image is present."""
        if self.manager._canvas_bg_image:
            bg_items = canvas.find_withtag("background_image")
            if not bg_items:
                self._restore_background_image(canvas)
        else:
            log.warning("gui.redraw_zones.no_background_image")
            # Try to load a frame if there's no background image
            self.manager.load_video_frame_to_canvas()

    def _restore_background_image(self, canvas):
        """Restore background image to canvas."""
        if hasattr(self.manager, "_canvas_bg_position") and self.manager._canvas_bg_position:
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

    def _draw_geotaxis_overlay(self):
        """Draw Geotaxis Zones if enabled."""
        if getattr(self.manager, "show_geotaxis_zones", False):
            # Get config from manager or settings
            settings = getattr(self.manager.gui, "settings", None)
            num_zones = 3
            bottom_zones = 1
            if settings and hasattr(settings, "behavioral_analysis"):
                num_zones = settings.behavioral_analysis.default_geotaxis_num_zones
                bottom_zones = settings.behavioral_analysis.default_geotaxis_bottom_zones

            self.draw_geotaxis_zones(num_zones=num_zones, bottom_zones=bottom_zones)

    def _draw_multi_aquarium_zones(self, canvas, zone_data):
        """Draw zones for multi-aquarium setup."""
        for aquarium in zone_data.aquariums:
            if aquarium.polygon and len(aquarium.polygon) >= 3:
                try:
                    self._draw_aquarium_polygon(canvas, aquarium)
                except Exception as e:
                    log.error(
                        "gui.multi_aquarium.draw_error", aquarium_id=aquarium.id, error=str(e)
                    )

    def _draw_aquarium_polygon(self, canvas, aquarium):
        """Draw a single aquarium polygon."""
        canvas_polygon = []
        for point in aquarium.polygon:
            canvas_point = self.manager._video_to_canvas(point[0], point[1])
            canvas_polygon.extend([canvas_point[0], canvas_point[1]])

        # Use different colors for different aquariums if desired
        outline_color = "#008B8B" if aquarium.id == 0 else "#0066CC"

        canvas.create_polygon(
            canvas_polygon,
            fill="",
            outline=outline_color,
            width=2,
            tags=("main_polygon", f"aquarium_{aquarium.id}"),
        )

        # Add label for aquarium
        center_x = sum(canvas_polygon[0::2]) / len(aquarium.polygon)
        center_y = sum(canvas_polygon[1::2]) / len(aquarium.polygon)

        canvas.create_text(
            center_x,
            center_y,
            text=f"Aquário {aquarium.id + 1}",
            fill=outline_color,
            font=("Segoe UI", 10, "bold"),
            tags=("main_polygon", "aquarium_label"),
        )

    def _draw_single_aquarium_zones(self, canvas, zone_data):
        """Draw zones for single aquarium setup."""
        if zone_data.polygon and len(zone_data.polygon) >= 3:
            try:
                canvas_polygon = []
                for point in zone_data.polygon:
                    canvas_point = self.manager._video_to_canvas(point[0], point[1])
                    canvas_polygon.extend([canvas_point[0], canvas_point[1]])

                canvas.create_polygon(
                    canvas_polygon,
                    fill="",
                    outline="#008B8B",
                    width=2,
                    tags="main_polygon",
                )
            except Exception as e:
                log.error("gui.main_polygon.draw_error", error=str(e))

        # Draw ROI polygons
        self._draw_roi_polygons(canvas, zone_data)

    def _draw_roi_polygons(self, canvas, zone_data):
        """Draw ROI polygons and labels."""
        for i, polygon in enumerate(zone_data.roi_polygons):
            if len(polygon) < 3:
                continue

            color_bgr = zone_data.roi_colors[i] if i < len(zone_data.roi_colors) else (0, 255, 0)
            color_hex = f"#{color_bgr[2]:02x}{color_bgr[1]:02x}{color_bgr[0]:02x}"
            name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i + 1}"

            try:
                self._draw_single_roi(canvas, polygon, color_hex, name, i)
            except Exception as e:
                log.error("gui.roi_draw_error", name=name, error=str(e), index=i)

    def _draw_single_roi(self, canvas, polygon, color_hex, name, index):
        """Draw a single ROI polygon and its label."""
        canvas_polygon = []
        for point in polygon:
            canvas_point = self.manager._video_to_canvas(point[0], point[1])
            canvas_polygon.extend([canvas_point[0], canvas_point[1]])

        canvas.create_polygon(
            canvas_polygon,
            fill="",
            outline=color_hex,
            width=2,
            tags=("roi_polygon", f"roi_{index}"),
        )

        # Add label
        poly_array = np.array(
            [(canvas_polygon[i], canvas_polygon[i + 1]) for i in range(0, len(canvas_polygon), 2)]
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
            tags=("roi_label_bg", f"roi_label_bg_{index}"),
        )

        canvas.create_text(
            center_x,
            center_y,
            text=name,
            fill=color_hex,
            font=("Arial", 9, "bold"),
            tags=("roi_label", f"roi_label_{index}"),
        )

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
        if getattr(self.gui, "analysis_active", False):
            return

        # STRICT CHECK: Only draw if the Zone Tab is actually visible
        # This prevents bboxes from being drawn on the hidden canvas when on other tabs
        if self.gui.notebook and hasattr(self.gui, "zone_tab_frame") and self.gui.zone_tab_frame:
            try:
                current_tab = self.gui.notebook.select()
                zone_tab_id = str(self.gui.zone_tab_frame)
                if current_tab != zone_tab_id:
                    return
            except Exception:
                # If select() fails or widgets destroyed, stop drawing
                return

        canvas = self._get_canvas()
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
                    x1, y1, x2, y2, _conf, track_id = det
                    class_id = 0
                else:
                    x1, y1, x2, y2, _conf, track_id, class_id = det

                # Convert to canvas coordinates
                cx1, cy1 = self.manager._video_to_canvas(x1, y1)
                cx2, cy2 = self.manager._video_to_canvas(x2, y2)

                # Style configuration
                color = "magenta" if is_single_subject else "cyan"
                if class_id == 0:  # Aquarium
                    color = "yellow"

                # Draw bounding box
                canvas.create_rectangle(
                    cx1, cy1, cx2, cy2, outline=color, width=2, tags="detection_overlay"
                )

                # Draw label
                label_text = f"ID: {track_id}" if track_id is not None else "Det"
                if is_single_subject:
                    label_text = "Alvo"

                # Text background
                canvas.create_text(
                    cx1,
                    cy1 - 10,
                    text=label_text,
                    fill=color,
                    anchor="sw",
                    font=("Arial", 10, "bold"),
                    tags="detection_overlay",
                )

            except Exception as e:
                log.error("renderer.overlay_draw_error", error=str(e))

    def draw_interactive_polygon(self):
        """Redraw the polygon and its handles based on current points."""
        canvas = self._get_canvas()
        if not canvas:
            return

        canvas.delete("interactive_polygon", "handle", "edit_clamp_indicator", "ghost_polygon")

        # While editing, hide the persisted version of the active zone to avoid
        # visual overlap between old saved vertices and the interactive polygon.
        active_zone = getattr(self.manager, "current_editing_zone", None) or getattr(
            self.gui, "current_editing_zone", None
        )
        if active_zone == "arena":
            canvas.delete("main_polygon")
        elif isinstance(active_zone, tuple) and active_zone[0] == "roi":
            roi_index = active_zone[1]
            canvas.delete(f"roi_{roi_index}", f"roi_label_{roi_index}", f"roi_label_bg_{roi_index}")

        # Draw ghost polygon of the other aquarium (visual reference)
        ghost_polygon = self.manager.get_other_aquarium_polygon()
        if ghost_polygon:
            ghost_canvas_points = []
            for pt in ghost_polygon:
                cx, cy = self.manager._video_to_canvas(pt[0], pt[1])
                ghost_canvas_points.extend([cx, cy])

            if len(ghost_canvas_points) >= 6:
                canvas.create_polygon(
                    ghost_canvas_points,
                    fill="",
                    outline="#888888",
                    width=2,
                    dash=(5, 3),
                    tags="ghost_polygon",
                )
                # Label for the ghost polygon
                canvas.create_text(
                    ghost_canvas_points[0],
                    ghost_canvas_points[1] - 15,
                    text="Aquário 1 (referência)",
                    fill="#666666",
                    font=("Segoe UI", 9, "italic"),
                    tags="ghost_polygon",
                )

        canvas_points = []
        for point in self.gui.edited_polygon_points:
            canvas_point = self.manager._video_to_canvas(point[0], point[1])
            canvas_points.append([canvas_point[0], canvas_point[1]])

        flat_points = [coord for point in canvas_points for coord in point]
        self.gui.interactive_polygon_item = canvas.create_polygon(
            flat_points,
            fill="",
            outline="#B8860B",  # DarkGoldenRod
            width=2,
            tags="interactive_polygon",
        )

        selected_indices = getattr(self.manager, "selected_vertex_indices", None) or set()

        self.gui.polygon_handles = []
        for i, canvas_point in enumerate(canvas_points):
            x, y = canvas_point[0], canvas_point[1]

            is_selected = i in selected_indices
            is_on_boundary = False
            if (
                isinstance(self.gui.current_editing_zone, tuple)
                and self.gui.current_editing_zone[0] == "roi"
            ):
                zone_data = self.zone_context_service.get_zone_data_for_active_context()
                main_arena_poly = zone_data.polygon if zone_data else None
                if main_arena_poly:
                    canvas_arena_poly = []
                    for point in main_arena_poly:
                        canvas_pt = self.manager._video_to_canvas(point[0], point[1])
                        canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                    arena_array = np.array(canvas_arena_poly, dtype=np.float32)
                    result = cv2.pointPolygonTest(arena_array, (x, y), True)
                    is_on_boundary = abs(result) < 1.0

            if is_selected:
                # Selected vertices stand out (issue 1 & 2): red fill, white ring.
                handle_fill = "#FF3030"
                handle_outline = "white"
                half = 6
            elif is_on_boundary:
                handle_fill = "orange"
                handle_outline = "red"
                half = 4
            else:
                handle_fill = "darkgoldenrod"
                handle_outline = "#DAA520"
                half = 4

            handle = canvas.create_rectangle(
                x - half,
                y - half,
                x + half,
                y + half,
                fill=handle_fill,
                outline=handle_outline,
                width=2 if is_selected else 1,
                tags=("handle", f"handle-{i}"),
            )
            self.gui.polygon_handles.append(handle)

            if is_on_boundary:
                canvas.create_oval(
                    x - 8,
                    y - 8,
                    x + 8,
                    y + 8,
                    outline="orange",
                    width=2,
                    tags="edit_clamp_indicator",
                )

            handler = self.gui.canvas_manager.event_handler
            canvas.tag_bind(
                handle,
                "<ButtonPress-1>",
                lambda e, i=i, h=handler: h.on_handle_press(e, i),
            )
            canvas.tag_bind(handle, "<B1-Motion>", handler.on_handle_drag)
            canvas.tag_bind(handle, "<ButtonRelease-1>", handler.on_handle_release)
            # Multi-vertex selection / deletion gestures (issues 1 & 2).
            canvas.tag_bind(
                handle,
                "<Triple-Button-1>",
                lambda e, i=i, h=handler: h.on_handle_triple_click(e, i),
            )
            canvas.tag_bind(
                handle,
                "<Shift-ButtonPress-1>",
                lambda e, i=i, h=handler: h.on_handle_shift_click(e, i),
            )
            canvas.tag_bind(
                handle,
                "<Control-ButtonPress-1>",
                lambda e, i=i, h=handler: h.on_handle_ctrl_click(e, i),
            )

    def redraw_polygon_in_progress(self):
        """Redraw the polygon vertices and edges after undo/redo."""
        canvas = self._get_canvas()
        if not canvas:
            return

        canvas.delete("drawing_aid")

        current_points = self.gui.drawing_state_manager.current_points

        for canvas_x, canvas_y in current_points:
            canvas.create_oval(
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
            canvas.create_line(
                p1[0], p1[1], p2[0], p2[1], fill="#008B8B", width=2, tags="drawing_aid"
            )

    def draw_geotaxis_zones(self, num_zones: int = 3, bottom_zones: int = 1):
        """Draw horizontal lines indicating geotaxis zones."""
        canvas = self._get_canvas()
        if not canvas:
            return

        canvas.delete("geotaxis_zone")

        # Get zone data
        zone_data = self.zone_context_service.get_zone_data_for_active_context()
        if not zone_data:
            return

        from zebtrack.core.detection import MultiAquariumZoneData

        polygons_to_draw = []
        if isinstance(zone_data, MultiAquariumZoneData):
            for aq in zone_data.aquariums:
                if aq.polygon and len(aq.polygon) >= 3:
                    polygons_to_draw.append(aq.polygon)
        elif zone_data.polygon and len(zone_data.polygon) >= 3:
            polygons_to_draw.append(zone_data.polygon)

        if not polygons_to_draw:
            return

        for poly in polygons_to_draw:
            # Convert to canvas coords
            canvas_poly = []
            for pt in poly:
                cp = self.manager._video_to_canvas(pt[0], pt[1])
                canvas_poly.append(cp)

            ys = [p[1] for p in canvas_poly]
            if not ys:
                continue

            min_y, max_y = min(ys), max(ys)
            height = max_y - min_y

            if height <= 0:
                continue

            step = height / num_zones

            xs = [p[0] for p in canvas_poly]
            min_x, max_x = min(xs), max(xs)

            # Draw zone text
            canvas.create_text(
                min_x + 5,
                min_y + 5,
                text="TOP",
                anchor="nw",
                fill="cyan",
                font=("Arial", 8),
                tags="geotaxis_zone",
            )

            for i in range(1, num_zones):
                y = min_y + i * step
                # Draw dashed line
                canvas.create_line(
                    min_x, y, max_x, y, fill="cyan", dash=(4, 4), width=1, tags="geotaxis_zone"
                )

            # Highlight bottom zone area (last 'bottom_zones' segments)
            y_bottom_start = max_y - (step * bottom_zones)
            canvas.create_rectangle(
                min_x,
                y_bottom_start,
                max_x,
                max_y,
                fill="blue",
                stipple="gray12",
                outline="",
                tags="geotaxis_zone",
            )
            canvas.create_text(
                min_x + 5,
                max_y - 5,
                text="BOTTOM",
                anchor="sw",
                fill="cyan",
                font=("Arial", 8),
                tags="geotaxis_zone",
            )

"""Canvas management for ApplicationGUI (Facade).

Decomposed in Phase 4.5 into focused sub-modules:
- CanvasRenderer: Zone/polygon rendering (canvas/renderer.py) [Phase 4.1]
- CanvasEventHandler: Mouse/keyboard event handling (canvas/event_handler.py) [Phase 4.2]
- MultiAquariumOverlayManager: Multi-aquarium overlay ops (canvas/multi_aquarium_overlay.py)
- VideoFrameManager: Video frame loading and display (canvas/video_frame_manager.py)
- ZoneEditor: Zone CRUD, drawing lifecycle, clipboard (canvas/zone_editor.py)

This file retains:
- Constructor and sub-component wiring
- Canvas access (_get_canvas)
- Event subscriptions and handlers
- Coordinate transforms (_canvas_to_video, _video_to_canvas, _point_to_segment_distance)
- Interactive polygon setup (setup_interactive_polygon)
- Snapping logic (apply_snapping)
- Delegation shims for backward compatibility
"""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

from zebtrack.ui.components.canvas.event_handler import CanvasEventHandler

if TYPE_CHECKING:
    from pathlib import Path

    from zebtrack.core.services.zone_context_service import ZoneContextService
from zebtrack.ui import payloads as payloads
from zebtrack.ui.components.canvas.multi_aquarium_overlay import MultiAquariumOverlayManager
from zebtrack.ui.components.canvas.renderer import CanvasRenderer
from zebtrack.ui.components.canvas.video_frame_manager import VideoFrameManager
from zebtrack.ui.components.canvas.zone_editor import ZoneEditor
from zebtrack.ui.event_bus_v2 import UIEvents
from zebtrack.utils.geometry_service import GeometryService

log = structlog.get_logger()


def _payload_get(payload: payloads.EventPayload | dict[str, Any], key: str, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


class CanvasManager:
    """Manages canvas operations, drawing, and coordinate transformations.

    Facade that delegates to focused sub-components while preserving
    backward-compatible API for all consumers.
    """

    # Class-level aliases for external code that references these directly
    AQUARIUM_COLORS: typing.ClassVar = MultiAquariumOverlayManager.AQUARIUM_COLORS
    _BGR_COLOR_MAP: typing.ClassVar = ZoneEditor._BGR_COLOR_MAP

    def __init__(
        self, gui, event_bus_v2=None, *, zone_context_service: ZoneContextService | None = None
    ):
        """Initialize CanvasManager.

        Args:
            gui: Reference to ApplicationGUI instance
            event_bus_v2: EventBusV2 instance for v4.0 Event-Driven Architecture (optional)
            zone_context_service: Optional ZoneContextService for dependency injection.
        """
        self.gui = gui
        self.event_bus_v2 = event_bus_v2
        self._zone_context_service = zone_context_service
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

        # Multi-vertex selection state (issues 1 & 2). Indices reference
        # gui.edited_polygon_points. Populated via Shift/Ctrl+click on handles,
        # rubber-band selection or the canvas context menu; consumed by
        # delete_vertices() and the move-in-group logic in on_handle_drag.
        self.selected_vertex_indices: set[int] = set()
        self._rubber_band_start: tuple[float, float] | None = None
        self._rubber_band_item: int | None = None
        self._rubber_band_mode: str = "replace"  # replace | add | remove
        self._vertex_context_menu = None
        # Last known canvas position of a group-drag, in canvas coords.
        self._group_drag_last: tuple[float, float] | None = None

        # Visualization settings
        self.show_geotaxis_zones = False

        # Live session tracking
        self._live_frame_subscription = None  # Track subscription for cleanup

        # Initialize sub-components (Phase 4.1-4.2 originals)
        self.renderer = CanvasRenderer(self)
        self.event_handler = CanvasEventHandler(self)

        # Initialize sub-components (Phase 4.5 extractions)
        self.multi_aquarium = MultiAquariumOverlayManager(self)
        self.video_frame = VideoFrameManager(self)
        self.zone_editor = ZoneEditor(self, zone_context_service=zone_context_service)

        # Subscribe to events if event bus is available
        if self.event_bus_v2:
            self._setup_event_subscriptions()

    @property
    def zone_context_service(self):
        """ZoneContextService instance (injected or resolved from gui)."""
        if self._zone_context_service is not None:
            return self._zone_context_service
        return getattr(self.gui, "_zone_context_service", None)

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

        # Subscribe to live frame updates via EventBusV2
        if self.event_bus_v2:
            self.event_bus_v2.subscribe(UIEvents.UI_UPDATE_LIVE_FRAME, self._on_live_frame_update)
            # Note: _live_session_active remains False until a live session actually starts
            log.debug("canvas_manager.subscribed_to_live_frame_updates")

    def _on_zones_updated(self, data: payloads.EventPayload):
        """Handle ZONES_UPDATED event.

        Args:
            data: Event payload containing zone_data
        """
        zone_data = _payload_get(data, "zone_data")
        log.debug(
            "canvas_manager.zones_updated_event_received", has_zone_data=zone_data is not None
        )
        self.update_zone_listbox(zone_data)

    def _on_polygon_edit_requested(self, data: payloads.EventPayload):
        """Handle POLYGON_EDIT_REQUESTED event.

        Args:
            data: Event payload containing:
                - polygon: np.ndarray of polygon points
        """
        polygon = _payload_get(data, "polygon")
        if polygon is not None:
            self.setup_interactive_polygon(polygon)

    def _on_live_frame_update(self, data: payloads.EventPayload):
        """Handle UI_UPDATE_LIVE_FRAME event from LiveCameraService.

        Args:
            data: Payload with 'frame' (np.ndarray) and 'detections'.
        """
        frame = _payload_get(data, "frame")
        detections = _payload_get(data, "detections")

        if frame is not None:
            # We are already on the main thread here via EventDispatcher polling
            self.update_video_frame(frame, detections)

    def unsubscribe_from_live_frames(self):
        """Unsubscribe from live frame updates to stop receiving events."""
        log.info(
            "canvas_manager.unsubscribe_from_live_frames.called",
            has_subscription=hasattr(self, "_live_frame_subscription"),
            has_event_bus_v2=self.event_bus_v2 is not None,
        )

        if self.event_bus_v2:
            try:
                self.event_bus_v2.unsubscribe(
                    UIEvents.UI_UPDATE_LIVE_FRAME, self._on_live_frame_update
                )
                if hasattr(self, "_live_frame_subscription"):
                    self._live_frame_subscription = None
                log.info("canvas_manager.unsubscribed_from_live_frames.success")
            except Exception as e:
                log.warning("canvas_manager.unsubscribe_failed", error=str(e), exc_info=True)

    # ========== Core Methods (Remain on Facade) ==========

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

        # Fresh edit session — clear any leftover vertex selection.
        self.selected_vertex_indices = set()

        # Draw the interactive polygon with handles
        self.renderer.draw_interactive_polygon()

        # Bind canvas-level editing events (rubber-band selection, context menu,
        # Delete key). Per-handle bindings are (re)attached by draw_interactive_polygon.
        self.event_handler.bind_editing_events()

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

    def apply_snapping(self, canvas_x, canvas_y, exclude_current_polygon=False, snap_threshold=10):
        """Apply snapping to nearby vertices or edges of existing polygons."""
        zone_data = self.zone_context_service.get_zone_data_for_active_context()
        all_polygons = []

        from zebtrack.core.detection import MultiAquariumZoneData

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

    # ========== Delegated Methods (kept on facade for backward compat) ==========

    def _redraw_polygon_in_progress(self):
        """Redraw the polygon vertices and edges after undo/redo. Delegates to renderer."""
        self.renderer.redraw_polygon_in_progress()

    def redraw_zones_from_project_data(self, zone_data=None):
        """Redraw zones preserving the background. Delegates to renderer."""
        self.renderer.redraw_zones(zone_data)

    # =====================================================================
    # Delegation Shims (Phase 4.5 - Backward Compatibility)
    # =====================================================================
    # All methods below delegate to their respective sub-component.
    # This preserves the public API surface so consumers (gui.py,
    # event_dispatcher.py, ui_coordinator.py, analysis_view_controller.py)
    # continue working without modification.
    # =====================================================================

    # --- MultiAquariumOverlayManager ---

    def on_multi_auto_detect_success(self, data: dict):
        """Handle successful multi-aquarium detection. Delegates to multi_aquarium."""
        return self.multi_aquarium.on_multi_auto_detect_success(data)

    def draw_multi_aquarium_overlay(self, *args, **kwargs) -> np.ndarray:
        """Draw multi-aquarium overlay on frame. Delegates to multi_aquarium."""
        return self.multi_aquarium.draw_multi_aquarium_overlay(*args, **kwargs)

    def create_side_by_side_preview(self, *args, **kwargs) -> np.ndarray:
        """Create side-by-side aquarium preview. Delegates to multi_aquarium."""
        return self.multi_aquarium.create_side_by_side_preview(*args, **kwargs)

    @staticmethod
    def hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to BGR tuple. Delegates to MultiAquariumOverlayManager."""
        return MultiAquariumOverlayManager.hex_to_bgr(hex_color)

    def _check_prompt_second_aquarium(self) -> None:
        """Check if second aquarium prompt is needed. Delegates to multi_aquarium."""
        self.multi_aquarium._check_prompt_second_aquarium()

    def _prompt_add_second_aquarium(self) -> None:
        """Prompt user to add second aquarium. Delegates to multi_aquarium."""
        self.multi_aquarium._prompt_add_second_aquarium()

    def _convert_to_multi_aquarium_format(self) -> None:
        """Convert zone data to multi-aquarium format. Delegates to multi_aquarium."""
        self.multi_aquarium._convert_to_multi_aquarium_format()

    def _start_second_aquarium_drawing(self) -> None:
        """Start drawing second aquarium polygon. Delegates to multi_aquarium."""
        self.multi_aquarium._start_second_aquarium_drawing()

    def get_other_aquarium_polygon(self) -> list[list[int]] | None:
        """Get polygon of the other aquarium. Delegates to multi_aquarium."""
        return self.multi_aquarium.get_other_aquarium_polygon()

    def _show_aquarium_indicator(self, text: str) -> None:
        """Show aquarium indicator on canvas. Delegates to multi_aquarium."""
        self.multi_aquarium._show_aquarium_indicator(text)

    # --- VideoFrameManager ---

    def display_roi_video_frame(self, video_path: Path | str | None):
        """Load first frame of video and display on canvas. Delegates to video_frame."""
        self.video_frame.display_roi_video_frame(video_path)

    def update_video_frame(self, frame: np.ndarray, detections: list | None = None) -> None:
        """Update canvas with a raw video frame. Delegates to video_frame."""
        self.video_frame.update_video_frame(frame, detections)

    def load_video_frame_to_canvas(
        self, video_path: Path | str | None = None, frame_number: int = 0
    ):
        """Load a video frame to the canvas. Delegates to video_frame."""
        return self.video_frame.load_video_frame_to_canvas(video_path, frame_number)

    def load_selected_video_frame(self, event=None):
        """Load frame from selected video to main canvas. Delegates to video_frame."""
        self.video_frame.load_selected_video_frame(event)

    def on_canvas_configure(self, event=None):
        """Handle canvas resize events. Delegates to video_frame."""
        self.video_frame.on_canvas_configure(event)

    def _draw_bg_image_to_canvas(self):
        """Draw background image to canvas. Delegates to video_frame."""
        self.video_frame._draw_bg_image_to_canvas()

    def _get_selected_analysis_track(self) -> str:
        """Return currently selected Track ID. Delegates to video_frame."""
        return self.video_frame._get_selected_analysis_track()

    def _filter_detections_by_track(self, detections: list, selected_track: str) -> list:
        """Filter detections by Track ID. Delegates to video_frame."""
        return self.video_frame._filter_detections_by_track(detections, selected_track)

    def _update_analysis_track_options_from_detections(self, detections: list) -> None:
        """Refresh track selector options. Delegates to video_frame."""
        self.video_frame._update_analysis_track_options_from_detections(detections)

    @staticmethod
    def _draw_detection_overlay_on_frame(frame: np.ndarray, detections: list) -> None:
        """Draw detection rectangles on frame. Delegates to VideoFrameManager."""
        VideoFrameManager._draw_detection_overlay_on_frame(frame, detections)

    def _render_last_analysis_frame(self) -> None:
        """Re-render last analysis frame. Delegates to video_frame."""
        self.video_frame._render_last_analysis_frame()

    # --- ZoneEditor ---

    def update_zone_listbox(self, zone_data=None):
        """Update zone listbox. Delegates to zone_editor."""
        self.zone_editor.update_zone_listbox(zone_data)

    def update_processing_mode(self, sequential: bool) -> None:
        """Update processing mode (parallel vs sequential). Delegates to zone_editor."""
        self.zone_editor.update_processing_mode(sequential)

    def start_polygon_drawing(self):
        """Activate polygon drawing mode. Delegates to zone_editor."""
        self.zone_editor.start_polygon_drawing()

    def stop_drawing(self):
        """Deactivate any drawing mode. Delegates to zone_editor."""
        self.zone_editor.stop_drawing()

    def handle_vertex_drag(self, event):
        """Handle vertex drag event. Delegates to zone_editor."""
        return self.zone_editor.handle_vertex_drag(event)

    def handle_canvas_click(self, event):
        """Handle canvas click event. Delegates to zone_editor."""
        return self.zone_editor.handle_canvas_click(event)

    def start_main_arena_drawing(self):
        """Start drawing main arena polygon. Delegates to zone_editor."""
        self.zone_editor.start_main_arena_drawing()

    def start_roi_drawing(self):
        """Start drawing ROI polygon. Delegates to zone_editor."""
        self.zone_editor.start_roi_drawing()

    def start_circle_drawing(self):
        """Activate circle drawing mode. Delegates to zone_editor."""
        self.zone_editor.start_circle_drawing()

    def on_canvas_press_circle(self, event):
        """Handle mouse press during circle drawing. Delegates to zone_editor."""
        self.zone_editor.on_canvas_press_circle(event)

    def on_canvas_drag_circle(self, event):
        """Handle mouse drag during circle drawing. Delegates to zone_editor."""
        self.zone_editor.on_canvas_drag_circle(event)

    def on_canvas_release_circle(self, event):
        """Handle mouse release during circle drawing. Delegates to zone_editor."""
        self.zone_editor.on_canvas_release_circle(event)

    def edit_selected_zone_vertices(self):
        """Enable interactive editing of selected zone vertices. Delegates to zone_editor."""
        self.zone_editor.edit_selected_zone_vertices()

    def save_arena(self):
        """Save the edited polygon. Delegates to zone_editor."""
        self.zone_editor.save_arena()

    def discard_arena(self):
        """Discard the interactive polygon. Delegates to zone_editor."""
        self.zone_editor.discard_arena()

    def clear_interactive_polygon(self):
        """Clear all interactive elements. Delegates to zone_editor."""
        self.zone_editor.clear_interactive_polygon()

    def update_roi_button_state(self):
        """Enable ROI button if arena exists. Delegates to zone_editor."""
        self.zone_editor.update_roi_button_state()

    def remove_selected_roi(self):
        """Remove selected ROI with confirmation. Delegates to zone_editor."""
        self.zone_editor.remove_selected_roi()

    def _get_color_name_from_bgr(self, bgr: tuple) -> str:
        """Convert BGR tuple to Portuguese color name. Delegates to zone_editor."""
        return self.zone_editor._get_color_name_from_bgr(bgr)

    def copy_zones_from_video(self, video_path: Path | str | None) -> None:
        """Copy zones from video to clipboard. Delegates to zone_editor."""
        self.zone_editor.copy_zones_from_video(video_path)

    def paste_zones_to_video(self, video_path: Path | str | None) -> None:
        """Paste zones from clipboard to video. Delegates to zone_editor."""
        self.zone_editor.paste_zones_to_video(video_path)

    def delete_zones_from_video(self, video_path: Path | str | None) -> None:
        """Delete all zones from video. Delegates to zone_editor."""
        self.zone_editor.delete_zones_from_video(video_path)

    def toggle_geotaxis_visualization(self, show: bool):
        """Toggle geotaxis zones visualization. Delegates to zone_editor."""
        self.zone_editor.toggle_geotaxis_visualization(show)

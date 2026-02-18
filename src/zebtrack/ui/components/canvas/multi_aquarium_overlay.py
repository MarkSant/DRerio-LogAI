"""Multi-aquarium overlay management for CanvasManager.

Extracted from canvas_manager.py (Phase 4.5) to reduce God Object complexity.
Handles multi-aquarium auto-detection results, format conversion, overlay drawing,
and side-by-side preview generation.

All methods access the parent CanvasManager via self.canvas_manager back-reference.
"""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

import cv2
import numpy as np
import structlog

if TYPE_CHECKING:
    from zebtrack.core.detection import MultiAquariumZoneData
    from zebtrack.ui.components.canvas_manager import CanvasManager

log = structlog.get_logger()


class MultiAquariumOverlayManager:
    """Manages multi-aquarium overlay operations for CanvasManager.

    Handles:
    - Auto-detection result processing (on_multi_auto_detect_success)
    - Format conversion from single to multi-aquarium (convert_to_multi_aquarium_format)
    - Second aquarium prompts and drawing flow
    - Multi-aquarium overlay rendering on video frames
    - Side-by-side aquarium preview generation
    - Ghost polygon rendering for cross-aquarium reference
    """

    # Distinct colors for each aquarium
    AQUARIUM_COLORS: typing.ClassVar = {
        0: {"border": (0, 102, 204), "fill": (0, 102, 204, 51), "text": "Aquário 1"},
        1: {"border": (0, 204, 102), "fill": (0, 204, 102, 51), "text": "Aquário 2"},
    }

    def __init__(self, canvas_manager: CanvasManager) -> None:
        """Initialize MultiAquariumOverlayManager.

        Args:
            canvas_manager: Reference to the parent CanvasManager instance.
        """
        self.canvas_manager = canvas_manager

    @property
    def gui(self):
        """Shortcut to parent CanvasManager's gui reference."""
        return self.canvas_manager.gui

    def on_multi_auto_detect_success(self, data: dict) -> None:
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
        from zebtrack.core.detection import AquariumData, MultiAquariumZoneData

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
        self.canvas_manager.redraw_zones_from_project_data(multi_data)
        self.canvas_manager.update_zone_listbox(multi_data)

        self.gui.show_info(
            "Sucesso",
            f"Detectados {len(polygons)} aquários com sucesso!\n"
            "Verifique se as marcações estão corretas.",
        )

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
        from zebtrack.core.detection import AquariumData, MultiAquariumZoneData

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
        self.canvas_manager.start_main_arena_drawing()

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
        from zebtrack.core.project.zone_manager import ZoneManager

        zone_manager = ZoneManager()
        multi_data = zone_manager.get_multi_aquarium_zone_data(project_data, video_path)

        if multi_data:
            aquarium = multi_data.get_aquarium(other_id)
            if aquarium and aquarium.polygon:
                return [list(point) for point in aquarium.polygon]

        # Fallback: if other_id=0, try regular zone data
        if other_id == 0:
            zone_data = self.gui.controller.project_manager.get_zone_data(video_path)
            if zone_data and hasattr(zone_data, "polygon") and zone_data.polygon:
                return [list(point) for point in zone_data.polygon]

        return None

    def _show_aquarium_indicator(self, text: str) -> None:
        """Show indicator of which aquarium is being drawn."""
        canvas = self.canvas_manager._get_canvas()
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

    def draw_multi_aquarium_overlay(
        self,
        frame: np.ndarray,
        zone_data: MultiAquariumZoneData,
        detections_by_aquarium: dict[int, list] | None = None,
        show_labels: bool = True,
        show_rois: bool = True,
    ) -> np.ndarray:
        """Draw overlay with multiple aquariums on a video frame.

        Each aquarium is drawn with a distinct border color, and optionally
        includes labels indicating the aquarium number and experimental group.
        Detections (bounding boxes) are drawn with the corresponding aquarium color.

        Args:
            frame: The video frame as a numpy array (BGR format from OpenCV).
            zone_data: MultiAquariumZoneData containing aquarium configurations.
            detections_by_aquarium: Optional dict mapping aquarium_id to list of
                detections. Each detection is a tuple
                (x1, y1, x2, y2, conf, track_id, class_id).
            show_labels: Whether to show aquarium labels (default True).
            show_rois: Whether to show ROI polygons (default True).

        Returns:
            The frame with overlay drawn (modified in place but also returned).

        Example:
            >>> overlay_frame = multi_aquarium.draw_multi_aquarium_overlay(
            ...     frame=current_frame,
            ...     zone_data=multi_aquarium_zone_data,
            ...     detections_by_aquarium={0: [...], 1: [...]},
            ... )
        """
        from zebtrack.core.detection import MultiAquariumZoneData

        if not isinstance(zone_data, MultiAquariumZoneData):
            log.warning(
                "canvas_manager.draw_multi_aquarium_overlay.invalid_zone_data",
                zone_data_type=type(zone_data).__name__,
            )
            return frame

        overlay = frame.copy()

        for aq in zone_data.aquariums:
            colors = self.AQUARIUM_COLORS.get(aq.id, self.AQUARIUM_COLORS[0])
            # Explicit cast to ensure MyPy knows it's a color tuple,
            # not a string from the dict union
            border_color = typing.cast(tuple[int, int, int], colors["border"])

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
        zone_data: MultiAquariumZoneData,
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
            >>> preview = multi_aquarium.create_side_by_side_preview(
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
                colors = self.AQUARIUM_COLORS.get(aq.id, self.AQUARIUM_COLORS[0])
                # Explicit cast for border color
                border_color = typing.cast(tuple[int, int, int], colors["border"])

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
                colors = self.AQUARIUM_COLORS.get(aq.id, self.AQUARIUM_COLORS[0])
                # Explicit cast for text label
                label = str(colors["text"])
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
                    typing.cast(tuple[int, int, int], colors["border"]),
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

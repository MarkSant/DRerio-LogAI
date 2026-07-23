"""Video frame loading and analysis display for CanvasManager.

Extracted from canvas_manager.py (Phase 4.5) to reduce God Object complexity.
Handles video/image frame loading to canvas, analysis frame display with
detection overlays, and frame caching for re-rendering.

All methods access the parent CanvasManager via self.canvas_manager back-reference.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import cv2
import numpy as np
import structlog
from PIL import Image

if TYPE_CHECKING:
    from pathlib import Path

    from zebtrack.ui.components.canvas_manager import CanvasManager
    from zebtrack.ui.components.dialog_manager import DialogManager

log = structlog.get_logger()


class VideoFrameManager:
    """Manages video frame loading and analysis display for CanvasManager.

    Handles:
    - Loading video/image frames to the zone canvas (display_roi_video_frame,
      load_video_frame_to_canvas, load_selected_video_frame)
    - Background image drawing delegation to renderer
    - Canvas configure event handling
    - Analysis frame display with detection overlays (update_video_frame)
    - Track filtering and selection for analysis display
    - Detection overlay rendering on frames
    - Frame caching for re-rendering after settings changes
    """

    #: Delay (ms) for the deferred background repaint scheduled after loading a
    #: frame in ``display_roi_video_frame``. Exposed as a class constant so
    #: consumers that must run *after* this repaint (e.g. a live auto-detect
    #: zone-overlay refresh) can derive their own delay instead of hardcoding a
    #: magic number that silently drifts if this value changes.
    BG_REPAINT_DELAY_MS = 10

    def __init__(
        self, canvas_manager: CanvasManager, *, dialog_manager: DialogManager | None = None
    ) -> None:
        """Initialize VideoFrameManager.

        Args:
            canvas_manager: Reference to the parent CanvasManager instance.
            dialog_manager: Optional DialogManager for dependency injection.
        """
        self.canvas_manager = canvas_manager
        self._dialog_manager = dialog_manager

        # Analysis frame cache (moved from CanvasManager)
        self._last_analysis_frame: np.ndarray | None = None
        self._last_detections: list | None = None

    @property
    def gui(self):
        """Shortcut to parent CanvasManager's gui reference."""
        return self.canvas_manager.gui

    @property
    def dialog_manager(self) -> DialogManager:
        """Return injected DialogManager or fall back to gui.dialog_manager."""
        return self._dialog_manager or self.gui.dialog_manager

    def _draw_bg_image_to_canvas(self) -> None:
        """Draw the background image to canvas. Delegates to renderer."""
        self.canvas_manager.renderer.draw_bg_image()

    def on_canvas_configure(self, event=None) -> None:
        """Handle canvas resize events. Delegates to renderer logic."""
        self.canvas_manager.renderer.draw_bg_image()
        if hasattr(self.gui, "controller") and self.gui.controller:
            self.canvas_manager.redraw_zones_from_project_data()

    def display_roi_video_frame(self, video_path: Path | str) -> None:
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
                self.dialog_manager.show_error(
                    "Erro",
                    "O vídeo selecionado não foi encontrado ou está inacessível.",
                )
                return

            self.gui.controller.project_manager.set_active_zone_video(video_path)
            self.gui.roi_template_manager.refresh_templates()

            # Check if file is an image or video
            lower_path = video_path.lower()  # type: ignore[union-attr]
            if lower_path.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff")):
                # It's an image - Use robust loading for Windows paths (unicode support)
                try:
                    # np.fromfile handles paths with special chars better than
                    # cv2.imread on Windows
                    file_data = np.fromfile(video_path, dtype=np.uint8)
                    frame = cv2.imdecode(file_data, cv2.IMREAD_COLOR)
                except Exception as e:
                    log.error(
                        "gui.display_roi_frame.image_load_failed",
                        error=str(e),
                        path=video_path,
                    )
                    frame = None

                if frame is None:
                    # Fallback to standard imread just in case
                    frame = cv2.imread(video_path)

                if frame is None:
                    self.dialog_manager.show_error("Erro", "Não foi possível ler a imagem.")
                    return
                ret = True
            else:
                # Assume it's a video
                cap = cv2.VideoCapture(video_path)
                if not cap.isOpened():
                    self.dialog_manager.show_error("Erro", "Não foi possível abrir o vídeo.")
                    return
                ret, frame = cap.read()
                cap.release()
                if not ret:
                    self.dialog_manager.show_error(
                        "Erro", "Não foi possível ler um frame do vídeo."
                    )
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
            self.canvas_manager._raw_bg_image = self.gui._original_image

            # Wait for the canvas to be properly sized after geometry update, then draw
            # Force canvas update before drawing to ensure proper sizing
            self.gui.root.update_idletasks()

            # Draw immediately to prevent black canvas warnings
            self._draw_bg_image_to_canvas()

            # Schedule another redraw to ensure canvas is fully ready.
            self.gui.root.after(self.BG_REPAINT_DELAY_MS, lambda: self._draw_bg_image_to_canvas())

        except Exception as e:
            self.dialog_manager.show_error("Erro ao Exibir Frame", str(e))

    def update_video_frame(self, frame: np.ndarray, detections: list | None = None) -> None:
        """Update the canvas with a raw video frame (numpy array).

        This method is called during video analysis to display frames.
        The frame already has overlays (arena, ROIs, bboxes) drawn by
        detector.draw_overlay().

        IMPORTANT: This should only display on the analysis tab widget,
        NOT on the zone canvas. The zone canvas should remain unchanged
        during analysis.

        Args:
            frame: The video frame as a numpy array (BGR format from OpenCV).
            detections: List of detections (not used - overlays already drawn
                on frame).
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

        # Save for re-rendering if needed
        self._last_analysis_frame = frame.copy()
        self._last_detections = detections

        try:
            frame_for_display = frame.copy()

            if detections:
                selected_track = self._get_selected_analysis_track()
                filtered_detections = self._filter_detections_by_track(detections, selected_track)
                self._update_analysis_track_options_from_detections(detections)
                self._draw_detection_overlay_on_frame(frame_for_display, filtered_detections)

            # Convert the frame for display (BGR -> RGB)
            frame_rgb = cv2.cvtColor(frame_for_display, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)

            # ONLY display on Analysis Tab widget during analysis
            # Do NOT update zone canvas - it should remain showing the static
            # zone drawing
            if self.gui.analysis_active and self.gui.analysis_display_widget:
                # Dynamic sizing
                target_w, target_h = 640, 480

                # Try to get current container size if available
                if self.gui.analysis_display_widget.video_container:
                    w = self.gui.analysis_display_widget.video_container.winfo_width()
                    h = self.gui.analysis_display_widget.video_container.winfo_height()
                    if w > 100 and h > 100:
                        target_w, target_h = w, h

                try:
                    resampling = Image.Resampling.LANCZOS
                except AttributeError:
                    # Fallback for older Pillow versions if needed,
                    # though pyproject specifies ^10.4.0
                    resampling = Image.LANCZOS  # type: ignore[attr-defined]

                pil_image.thumbnail((target_w, target_h), resampling)
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

    def _get_selected_analysis_track(self) -> str:
        """Return currently selected Track ID in analysis widget."""
        widget = getattr(self.gui, "analysis_display_widget", None)
        if widget and getattr(widget, "track_selector_var", None) is not None:
            selected = str(widget.track_selector_var.get()).strip()
            if selected:
                return selected
        return "Todos"

    def _filter_detections_by_track(self, detections: list, selected_track: str) -> list:
        """Filter detections according to selected Track ID."""
        if selected_track == "Todos":
            return detections

        filtered: list = []
        for det in detections:
            if not isinstance(det, tuple | list) or len(det) < 6:
                continue

            # Supported contracts:
            # - 6-tuple: (x1, y1, x2, y2, conf, track_id)
            # - 7-tuple: (x1, y1, x2, y2, conf, track_id, class_id)
            track_id = det[5]
            if len(det) >= 7:
                track_id = det[5]
            if str(track_id) == selected_track:
                filtered.append(det)
        return filtered

    def _update_analysis_track_options_from_detections(self, detections: list) -> None:
        """Refresh track selector options from current detections."""
        track_ids: set[str] = set()
        for det in detections:
            if isinstance(det, tuple | list) and len(det) >= 6:
                track_id = str(det[5]).strip()
                if track_id:
                    track_ids.add(track_id)

        options = ["Todos", *sorted(track_ids, key=lambda value: (len(value), value))]
        normalized = tuple(options)
        if getattr(self.gui, "_available_track_options", ("Todos",)) == normalized:
            return

        synchronizer = getattr(self.gui, "state_synchronizer", None)
        if synchronizer is not None and hasattr(synchronizer, "_update_track_options"):
            synchronizer._update_track_options(options)

    @staticmethod
    def _draw_detection_overlay_on_frame(frame: np.ndarray, detections: list) -> None:
        """Draw detection rectangles and labels directly on frame."""
        for det in detections:
            if not isinstance(det, tuple | list) or len(det) < 6:
                continue

            x1, y1, x2, y2 = map(int, det[:4])
            class_id = 0
            track_id = det[5]
            if len(det) >= 7:
                class_id = int(det[6])
            confidence = float(det[4]) if len(det) >= 5 else None

            color = (0, 255, 255) if class_id == 0 else (255, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            if track_id is not None:
                label = f"ID {track_id}"
            else:
                label = "Object"
            if confidence is not None:
                label = f"{label} ({int(confidence * 100)}%)"
            cv2.putText(
                frame,
                label,
                (x1, max(0, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                cv2.LINE_AA,
            )

    def _render_last_analysis_frame(self) -> None:
        """Re-render the last analysis frame with current settings."""
        if self._last_analysis_frame is not None:
            log.debug("canvas_manager._render_last_analysis_frame.called")
            self.update_video_frame(self._last_analysis_frame, self._last_detections)

    def load_video_frame_to_canvas(
        self, video_path: Path | str | None = None, frame_number: int = 0
    ):
        """Load a video frame to the canvas.

        Args:
            video_path: Path to the video file (optional, will use
                pending/project video if None)
            frame_number: Frame number to load (default: 0)

        Returns:
            bool: True if frame was loaded successfully, False otherwise
        """
        if video_path is None:
            # 1. Try to use currently active zone video
            # (e.g. just set by display_roi_video_frame)
            active_video = self.gui.controller.project_manager.get_active_zone_video()
            if isinstance(active_video, str | os.PathLike) and os.path.exists(active_video):
                video_path = os.fspath(active_video)

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

        if video_path is not None and not isinstance(video_path, str | os.PathLike):
            log.error(
                "gui.load_frame.invalid_video_path_type",
                path_type=type(video_path).__name__,
            )
            self.gui.controller.project_manager.set_active_zone_video(None)
            return False

        if not video_path or not os.path.exists(os.fspath(video_path)):
            # Audit Erro 10 (2026-05-25): demoted from error to debug.
            # This is a legitimate case (e.g., user double-clicked a "Sessão
            # planejada" placeholder which has no real path) — not a fault.
            log.debug("gui.load_frame.no_video", path=str(video_path) if video_path else None)
            self.gui.controller.project_manager.set_active_zone_video(None)
            return False

        try:
            self.gui.controller.project_manager.set_active_zone_video(video_path)

            # Check if file is an image or video
            lower_path = video_path.lower()  # type: ignore[union-attr]
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
                    log.error(
                        "gui.load_frame.image_exception",
                        error=str(e),
                        path=video_path,
                    )
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
            self.canvas_manager._raw_bg_image = self.gui._original_image

            # Display the image using proper canvas scaling
            self._draw_bg_image_to_canvas()

            log.info("gui.canvas.frame_loaded", video=video_path)
            return True

        except Exception as e:
            log.error("gui.load_frame.error", error=str(e))
            return False

    def load_selected_video_frame(self, event=None) -> None:
        """Load the frame from the selected video to the main canvas."""
        if hasattr(self.gui, "zone_edit_guard") and self.gui.zone_edit_guard:
            should_continue = self.gui.zone_edit_guard.confirm_pending_zone_edit_before_navigation(
                context="abrir outro vídeo"
            )
            if not should_continue:
                return

        tree = self.gui.zone_controls.video_selector_tree if self.gui.zone_controls else None
        if not tree:
            return

        selection = tree.selection()
        if not selection:
            self.dialog_manager.show_warning(
                "Nenhum Vídeo Selecionado",
                "Por favor, selecione um vídeo da lista para carregar.",
            )
            return

        item_id = selection[0]
        tags = tree.item(item_id, "tags")

        if not tags or not tags[0]:
            self.dialog_manager.show_info(
                "Selecione um Vídeo",
                "Por favor, escolha um item com ícone de peixe (🐟) para carregar o frame.",
            )
            return

        video_path = tags[0]

        # Reject non-video hierarchy nodes (group, day, subject)
        if video_path in ("group", "day", "subject"):
            self.dialog_manager.show_info(
                "Selecione um Vídeo",
                "Por favor, escolha um item com ícone de vídeo (🎬) para carregar o frame.",
            )
            return

        success = self.load_video_frame_to_canvas(video_path, frame_number=0)

        if success:
            self.dialog_manager.offer_zone_reuse(video_path)
            self.canvas_manager.redraw_zones_from_project_data()
            filename = os.path.basename(video_path)
            self.gui.set_status(f"✓ Frame carregado: {filename}")
            log.info("gui.video_selector.frame_loaded", path=video_path)
        else:
            self.dialog_manager.show_error(
                "Erro ao Carregar",
                f"Não foi possível carregar o vídeo selecionado.\n{video_path}",
            )

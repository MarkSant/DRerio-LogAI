import time
from dataclasses import dataclass, field
from types import SimpleNamespace

import cv2
import numpy as np
import structlog

from zebtrack.core.single_subject_tracker import SingleSubjectTracker
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import settings
from zebtrack.tracker.byte_tracker import BYTETracker

log = structlog.get_logger()


@dataclass
class ZoneData:
    """Holds the configuration for detection zones."""

    polygon: list[list[int]] = field(default_factory=list)
    roi_polygons: list[list[list[int]]] = field(default_factory=list)
    roi_names: list[str] = field(default_factory=list)
    roi_colors: list[tuple[int, int, int]] = field(default_factory=list)


class Detector:
    """
    Manages the detection process by delegating to a plugin and handling
    stateful logic for zone tracking.

    Nota de Otimização:
    O rastreamento de objetos é baseado nos bounding boxes. Se o modelo de IA
    carregado for um modelo de segmentação (*_seg.pt), ele realizará a
    tarefa computacionalmente mais custosa de encontrar máscaras de pixel,
    mesmo que apenas os bounding boxes sejam usados. Para um desempenho
    ótimo no rastreamento, um modelo treinado apenas para DETECÇÃO (que
    gera somente bounding boxes) deve ser usado em futuras versões.
    """

    def __init__(
        self,
        plugin: DetectorPlugin,
        base_width: int = 1280,
        base_height: int = 720,
    ):
        """
        Initializes the detector with a specific plugin.

        Args:
            plugin (DetectorPlugin): An instantiated detector plugin.
            base_width (int): The reference width the zones were defined on.
            base_height (int): The reference height the zones were defined on.
        """
        self.plugin = plugin
        if not self.plugin:
            log.error("detector.init.no_plugin")
            raise ValueError("Detector must be initialized with a valid plugin.")

        self.base_width = base_width
        self.base_height = base_height
        log.info("detector.init.success", plugin=self.plugin.get_name())

        # Zone configuration is now set dynamically via set_zones()
        self.zones: ZoneData = ZoneData()
        self.scaled_polygon: np.ndarray = np.array([])
        self.scaled_roi_polygons: list[np.ndarray] = []
        self._scaling_cache: dict = {}
        self._single_subject_mode = False
        self._single_subject_tracker = SingleSubjectTracker()
        self._byte_tracker: BYTETracker | None = None
        self._byte_tracker_params: tuple[float, float, int] | None = None
        self._zones_configured = False
        self._last_width: int | None = None
        self._last_height: int | None = None

    def set_zones(self, zones: ZoneData, actual_width: int, actual_height: int):
        """
        Sets the detection zones and scales them to the current video resolution.

        Args:
            zones (ZoneData): The zone configuration object.
            actual_width (int): The width of the video/camera frame to scale to.
            actual_height (int): The height of the video/camera frame to scale to.
        """
        if actual_width <= 0 or actual_height <= 0:
            raise ValueError(
                "Actual dimensions must be positive. "
                f"set_zones(zones, actual_width={actual_width}, actual_height={actual_height})"
            )

        self.zones = zones
        # Clear cache if zones are redefined, as scaling depends on zone data
        self._scaling_cache.clear()
        self._update_scaling(actual_width, actual_height)
        log.info("detector.zones.set", count=len(self.zones.roi_polygons))
        self._zones_configured = True
        self._last_width = actual_width
        self._last_height = actual_height
        self._single_subject_tracker.reset()

    def _update_scaling(self, actual_width: int, actual_height: int):
        """
        Updates the coordinates of the polygon and squares based on the actual
        video resolution, using a cache to avoid redundant calculations.
        """
        cache_key = (actual_width, actual_height)
        if cache_key in self._scaling_cache:
            cached_data = self._scaling_cache[cache_key]
            self.scaled_polygon = cached_data["polygon"]
            self.scaled_roi_polygons = cached_data["roi_polygons"]
            log.debug("detector.scaling.cache.hit", key=cache_key)
            return

        # Convert base polygons to numpy arrays for scaling
        base_polygon = np.array(self.zones.polygon, dtype=np.int32)
        base_roi_polygons = [np.array(p, dtype=np.int32) for p in self.zones.roi_polygons]

        if actual_width == self.base_width and actual_height == self.base_height:
            self.scaled_polygon = base_polygon
            self.scaled_roi_polygons = base_roi_polygons
        else:
            scale_x = actual_width / self.base_width
            scale_y = actual_height / self.base_height
            self.scaled_polygon = (base_polygon * [scale_x, scale_y]).astype(np.int32)
            self.scaled_roi_polygons = [
                (p * [scale_x, scale_y]).astype(np.int32) for p in base_roi_polygons
            ]

        # Store the newly calculated values in the cache
        self._scaling_cache[cache_key] = {
            "polygon": self.scaled_polygon,
            "roi_polygons": self.scaled_roi_polygons,
        }
        log.info(
            "detector.scaling.updated_and_cached",
            width=actual_width,
            height=actual_height,
        )

    def _is_inside_polygon(self, x1, y1, x2, y2, polygon):
        """
        Checks if any of the 4 corners OR the center of the bounding box is
        inside the polygon.
        Returns False if the polygon is empty or invalid.
        """
        if polygon.size == 0:
            return False

        # Calculate all 5 points: 4 corners + center
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2

        points_to_test = [
            (x1, y1),  # top-left
            (x2, y1),  # top-right
            (x2, y2),  # bottom-right
            (x1, y2),  # bottom-left
            (center_x, center_y),  # center
        ]

        # Return True if ANY of the 5 points is inside the polygon
        for point in points_to_test:
            if cv2.pointPolygonTest(polygon, point, False) >= 0:
                return True

        return False

    def bbox_hits_roi_polygon(
        self, x1: int, y1: int, x2: int, y2: int, roi_polygon: np.ndarray
    ) -> bool:
        """
        Returns True if 4 corners OR center of bbox falls within roi_polygon
        (cv2.pointPolygonTest >= 0).
        This is a utility helper for future live ROI checking functionality.
        """
        if roi_polygon.size == 0:
            return False

        # Calculate all 5 points: 4 corners + center
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2

        points_to_test = [
            (x1, y1),  # top-left
            (x2, y1),  # top-right
            (x2, y2),  # bottom-right
            (x1, y2),  # bottom-left
            (center_x, center_y),  # center
        ]

        # Return True if ANY of the 5 points is inside the polygon
        for point in points_to_test:
            if cv2.pointPolygonTest(roi_polygon, point, False) >= 0:
                return True

        return False

    def detect(self, frame: np.ndarray, project_type: str):
        """
        Processes a single frame for object detection and state tracking.
        """
        if not self._zones_configured:
            raise RuntimeError(
                "Must call set_zones() before detect(). "
                "Zones need video dimensions for proper scaling."
            )

        if self._last_width is not None and frame.shape[:2] != (
            self._last_height,
            self._last_width,
        ):
            log.warning(
                "detector.dimension_mismatch",
                expected=(self._last_width, self._last_height),
                actual=(frame.shape[1], frame.shape[0]),
                message=(
                    "Frame dimensions differ from dimensions used to set zones. "
                    "This may cause inaccurate detection scaling."
                ),
            )
        start_time = time.perf_counter()

        # Optimization: Crop the frame to the bounding box of the arena polygon
        if self.scaled_polygon.size > 0:
            x, y, w, h = cv2.boundingRect(self.scaled_polygon)
            cropped_frame = frame[y : y + h, x : x + w]

            # 1. Delegate actual detection to the loaded plugin on the cropped frame
            predictions = []
            for det in self.plugin.detect(cropped_frame):
                x1_crop, y1_crop, x2_crop, y2_crop, conf, track_id = self._ensure_track_tuple(det)
                x1 = x1_crop + x
                y1 = y1_crop + y
                x2 = x2_crop + x
                y2 = y2_crop + y
                predictions.append((x1, y1, x2, y2, conf, track_id))
        else:
            # Fallback to detecting on the full frame if no polygon is defined
            predictions = [self._ensure_track_tuple(det) for det in self.plugin.detect(frame)]

        # 2. Filter detections to only those inside the main polygon
        # This is still necessary for non-rectangular polygons
        detections_in_polygon = []
        if len(predictions) > 0:
            for det in predictions:
                x1, y1, x2, y2, confidence, track_id = det
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                confidence = float(confidence)

                if self._is_inside_polygon(x1, y1, x2, y2, self.scaled_polygon):
                    detections_in_polygon.append((x1, y1, x2, y2, confidence, track_id))
                else:
                    log.debug(
                        "detector.filtered_outside_polygon",
                        bbox=(x1, y1, x2, y2),
                        track_id=track_id,
                    )

        if self._single_subject_mode:
            detections_in_polygon = self._single_subject_tracker.assign(detections_in_polygon)
        else:
            detections_in_polygon = self._apply_byte_tracking(detections_in_polygon, frame.shape)

        end_time = time.perf_counter()
        log.debug(
            "frame.processing.time",
            duration_ms=(end_time - start_time) * 1000,
            plugin=self.plugin.get_name(),
        )

        # The command logic has been removed as it was tied to the old square ROIs
        command_to_send = None
        return detections_in_polygon, command_to_send

    def set_single_subject_mode(self, enabled: bool) -> None:
        """Toggle lightweight single-subject tracking."""

        enabled = bool(enabled)
        if self._single_subject_mode == enabled:
            return

        self._single_subject_mode = enabled
        self._single_subject_tracker.reset()
        if hasattr(self.plugin, "set_use_single_subject_mode"):
            try:
                self.plugin.set_use_single_subject_mode(enabled)
            except Exception:  # pragma: no cover - defensive
                log.warning(
                    "detector.single_subject_mode.plugin_update_failed",
                    enabled=enabled,
                    exc_info=True,
                )

    def is_single_subject_mode(self) -> bool:
        """Expose the current single-subject tracking flag."""

        return self._single_subject_mode

    def reset_tracking_state(self) -> None:
        """Reset tracker state between videos."""

        if hasattr(self.plugin, "reset_tracking_state"):
            try:
                self.plugin.reset_tracking_state()
            except Exception:  # pragma: no cover - defensive
                log.warning("detector.reset_tracking_state.plugin_failed", exc_info=True)
        self._single_subject_tracker.reset()
        self._byte_tracker = None
        self._byte_tracker_params = None

    def clear_cache(self):
        """Clears the internal scaling cache to free memory."""
        self._scaling_cache.clear()
        log.debug("detector.cache.cleared")

    @staticmethod
    def _ensure_track_tuple(detection):
        if len(detection) == 5:
            x1, y1, x2, y2, confidence = detection
            track_id = None
        else:
            x1, y1, x2, y2, confidence, track_id = detection[:6]
        return x1, y1, x2, y2, float(confidence), track_id

    def _apply_byte_tracking(
        self, detections: list[tuple], frame_shape: tuple[int, int, int]
    ) -> list[tuple]:
        if not detections:
            tracker = self._ensure_byte_tracker()
            if tracker is not None:
                empty = np.empty((0, 5), dtype=np.float32)
                tracker.update(
                    empty,
                    (frame_shape[0], frame_shape[1]),
                    self._resolve_model_input_shape(),
                )
            return []

        tracker = self._ensure_byte_tracker()
        if tracker is None:
            return [
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    float(confidence),
                    None,
                )
                for x1, y1, x2, y2, confidence, _ in detections
            ]

        det_array = np.array(
            [
                [float(x1), float(y1), float(x2), float(y2), float(confidence)]
                for x1, y1, x2, y2, confidence, _ in detections
            ],
            dtype=np.float32,
        )

        tracks = tracker.update(
            det_array,
            (frame_shape[0], frame_shape[1]),
            self._resolve_model_input_shape(),
        )

        results: list[tuple] = []
        for track in tracks:
            x1, y1, x2, y2 = track.tlbr
            results.append(
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    float(track.score),
                    int(track.track_id),
                )
            )

        return results

    def _ensure_byte_tracker(self) -> BYTETracker | None:
        track_thresh = self._get_track_threshold()
        match_thresh = self._get_match_threshold()
        track_buffer = self._get_track_buffer()

        params = (track_thresh, match_thresh, track_buffer)
        if self._byte_tracker is not None and self._byte_tracker_params == params:
            return self._byte_tracker

        try:
            args = SimpleNamespace(
                track_thresh=track_thresh,
                match_thresh=match_thresh,
                track_buffer=track_buffer,
                mot20=False,
            )
            frame_rate = getattr(settings.video_processing, "fps", 30) or 30
            self._byte_tracker = BYTETracker(args=args, frame_rate=frame_rate)
            self._byte_tracker_params = params
        except Exception:  # pragma: no cover - defensive
            log.warning("detector.bytetrack.init_failed", exc_info=True)
            self._byte_tracker = None
            self._byte_tracker_params = None

        return self._byte_tracker

    def _get_track_threshold(self) -> float:
        value = getattr(self.plugin, "track_threshold", None)
        if value is None:
            return float(getattr(settings.bytetrack, "track_threshold", 0.25))
        return float(value)

    def _get_match_threshold(self) -> float:
        value = getattr(self.plugin, "match_threshold", None)
        if value is None:
            return float(getattr(settings.bytetrack, "match_threshold", 0.15))
        return float(value)

    def _get_track_buffer(self) -> int:
        value = getattr(self.plugin, "track_buffer", None)
        if value is None:
            return 60
        try:
            return int(value)
        except (TypeError, ValueError):
            return 60

    def _resolve_model_input_shape(self) -> tuple[int, int]:
        try:
            shape = getattr(self.plugin, "model_input_shape", None)
            if shape and len(shape) == 2:
                return int(shape[0]), int(shape[1])
        except Exception:  # pragma: no cover - defensive
            log.debug("detector.model_input_shape.fallback", exc_info=True)
        return int(self.base_height), int(self.base_width)

    def draw_overlay(self, frame, detections):
        """
        Draws detection overlays on the frame.
        """
        # Draw the ROI polygons
        for i, polygon in enumerate(self.scaled_roi_polygons):
            if i < len(self.zones.roi_colors):
                color = self.zones.roi_colors[i]
                cv2.polylines(frame, [polygon], isClosed=True, color=color, thickness=2)

        # Draw the processing area polygon
        if self.scaled_polygon.size > 0:
            cv2.polylines(
                frame,
                [self.scaled_polygon],
                isClosed=True,
                color=(0, 0, 0),
                thickness=1,
            )

        # Draw the bounding boxes for detections
        for x1, y1, x2, y2, confidence, track_id in detections:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 255), 2)
            label = f"ID: {track_id} ({int(confidence * 100)}%)"
            cv2.putText(
                frame,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 255),
                2,
            )

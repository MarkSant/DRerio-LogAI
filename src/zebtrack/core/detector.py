import time
from dataclasses import dataclass, field
from typing import List, Tuple

import cv2
import numpy as np
import structlog

from zebtrack.plugins.base import DetectorPlugin

log = structlog.get_logger()


@dataclass
class ZoneData:
    """Holds the configuration for detection zones."""

    polygon: List[List[int]] = field(default_factory=list)
    roi_polygons: List[List[List[int]]] = field(default_factory=list)
    roi_names: List[str] = field(default_factory=list)
    roi_colors: List[Tuple[int, int, int]] = field(default_factory=list)


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
        self.scaled_roi_polygons: List[np.ndarray] = []
        self._scaling_cache: dict = {}

    def set_zones(self, zones: ZoneData, actual_width: int, actual_height: int):
        """
        Sets the detection zones and scales them to the current video resolution.

        Args:
            zones (ZoneData): The zone configuration object.
            actual_width (int): The width of the video/camera frame to scale to.
            actual_height (int): The height of the video/camera frame to scale to.
        """
        self.zones = zones
        # Clear cache if zones are redefined, as scaling depends on zone data
        self._scaling_cache.clear()
        self._update_scaling(actual_width, actual_height)
        log.info("detector.zones.set", count=len(self.zones.roi_polygons))

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
        base_roi_polygons = [
            np.array(p, dtype=np.int32) for p in self.zones.roi_polygons
        ]

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
        Checks if a corner of the bounding box is inside the polygon.
        Returns False if the polygon is empty or invalid.
        """
        if polygon.size == 0:
            return False
        return (
            cv2.pointPolygonTest(polygon, (x1, y1), False) >= 0
            or cv2.pointPolygonTest(polygon, (x2, y2), False) >= 0
        )

    def process_frame(self, frame: np.ndarray, project_type: str):
        """
        Processes a single frame for object detection and state tracking.
        """
        start_time = time.perf_counter()

        # Optimization: Crop the frame to the bounding box of the arena polygon
        if self.scaled_polygon.size > 0:
            x, y, w, h = cv2.boundingRect(self.scaled_polygon)
            cropped_frame = frame[y : y + h, x : x + w]

            # 1. Delegate actual detection to the loaded plugin on the cropped frame
            predictions_cropped = self.plugin.detect(cropped_frame)

            # Translate predictions back to the original frame's coordinate system
            predictions = []
            for det in predictions_cropped:
                x1, y1, x2, y2, conf, track_id = det
                predictions.append(
                    (x1 + x, y1 + y, x2 + x, y2 + y, conf, track_id)
                )
        else:
            # Fallback to detecting on the full frame if no polygon is defined
            predictions = self.plugin.detect(frame)

        # 2. Filter detections to only those inside the main polygon
        # This is still necessary for non-rectangular polygons
        detections_in_polygon = []
        if len(predictions) > 0:
            for det in predictions:
                x1, y1, x2, y2, confidence, track_id = det
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                if self._is_inside_polygon(x1, y1, x2, y2, self.scaled_polygon):
                    detections_in_polygon.append((x1, y1, x2, y2, confidence, track_id))

        end_time = time.perf_counter()
        log.debug(
            "frame.processing.time",
            duration_ms=(end_time - start_time) * 1000,
            plugin=self.plugin.get_name(),
        )

        # The command logic has been removed as it was tied to the old square ROIs
        command_to_send = None
        return detections_in_polygon, command_to_send

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

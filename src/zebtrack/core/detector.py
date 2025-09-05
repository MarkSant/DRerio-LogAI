import time
from dataclasses import dataclass, field
from typing import List, Tuple, Union

import cv2
import numpy as np
import structlog

from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import settings

log = structlog.get_logger()


@dataclass
class ZoneData:
    """Holds the configuration for detection zones."""

    polygon: List[List[int]] = field(default_factory=list)
    squares: List[Tuple[Tuple[int, int], Tuple[int, int]]] = field(default_factory=list)
    colors: List[Tuple[int, int, int]] = field(default_factory=list)
    enter_commands: List[Union[int, str]] = field(default_factory=list)
    exit_commands: List[Union[int, str]] = field(default_factory=list)


class Detector:
    """
    Manages the detection process by delegating to a plugin and handling
    stateful logic for zone tracking.
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

        # State variables for tracking object movement
        self.crossed_in = False
        self.crossed_out = False
        self.flag = 0  # 0: looking for entry, 1: looking for exit
        self.current_square = 0

        # Zone configuration is now set dynamically via set_zones()
        self.zones: ZoneData = ZoneData()
        self.scaled_polygon: np.ndarray = np.array([])
        self.scaled_squares: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []

    def set_zones(self, zones: ZoneData, actual_width: int, actual_height: int):
        """
        Sets the detection zones and scales them to the current video resolution.

        Args:
            zones (ZoneData): The zone configuration object.
            actual_width (int): The width of the video/camera frame to scale to.
            actual_height (int): The height of the video/camera frame to scale to.
        """
        self.zones = zones
        self._update_scaling(actual_width, actual_height)
        log.info("detector.zones.set", count=len(self.zones.squares))

    def _update_scaling(self, actual_width: int, actual_height: int):
        """
        Updates the coordinates of the polygon and squares based on the actual
        video resolution.
        """
        # Convert base polygon to numpy array for scaling
        base_polygon = np.array(self.zones.polygon, dtype=np.int32)
        base_squares = self.zones.squares

        if actual_width == self.base_width and actual_height == self.base_height:
            self.scaled_polygon = base_polygon
            self.scaled_squares = base_squares
            return

        scale_x = actual_width / self.base_width
        scale_y = actual_height / self.base_height

        self.scaled_polygon = (base_polygon * [scale_x, scale_y]).astype(np.int32)
        self.scaled_squares = []
        for p1, p2 in base_squares:
            x1, y1 = p1
            x2, y2 = p2
            scaled_p1 = (int(x1 * scale_x), int(y1 * scale_y))
            scaled_p2 = (int(x2 * scale_x), int(y2 * scale_y))
            self.scaled_squares.append((scaled_p1, scaled_p2))

        log.info(
            "detector.scaling.updated",
            width=actual_width,
            height=actual_height,
        )

    def _is_inside_square(self, x1, y1, x2, y2, square):
        """Checks if a bounding box overlaps with an area square."""
        (sx1, sy1), (sx2, sy2) = square
        return not (x2 < sx1 or x1 > sx2 or y2 < sy1 or y1 > sy2)

    def _is_inside_polygon(self, x1, y1, x2, y2, polygon):
        """Checks if a corner of the bounding box is inside the polygon."""
        return (
            cv2.pointPolygonTest(polygon, (x1, y1), False) >= 0
            or cv2.pointPolygonTest(polygon, (x2, y2), False) >= 0
        )

    def process_frame(self, frame: np.ndarray, project_type: str):
        """
        Processes a single frame for object detection and state tracking.
        """
        start_time = time.perf_counter()

        # 1. Delegate actual detection to the loaded plugin
        predictions = self.plugin.detect(frame)

        # 2. Apply stateful logic based on the detections
        detections_in_polygon = []
        command_to_send = None
        found_object_for_state_change = False

        if len(predictions) > 0:
            for det in predictions:
                x1, y1, x2, y2, confidence, track_id = det
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                if self._is_inside_polygon(x1, y1, x2, y2, self.scaled_polygon):
                    detections_in_polygon.append((x1, y1, x2, y2, confidence, track_id))

                    if project_type == "live" and not found_object_for_state_change:
                        if self.flag == 0:  # Looking for entry
                            for index, square in enumerate(self.scaled_squares):
                                if self._is_inside_square(x1, y1, x2, y2, square):
                                    self.crossed_in = True
                                    self.flag = 1
                                    self.current_square = index + 1
                                    command_to_send = self.zones.enter_commands[index]
                                    found_object_for_state_change = True
                                    break
                        elif self.flag == 1:  # Looking for exit
                            is_in_any_square = any(
                                self._is_inside_square(x1, y1, x2, y2, sq)
                                for sq in self.scaled_squares
                            )
                            if not is_in_any_square:
                                self.crossed_out = True
                                self.flag = 0
                                command_to_send = self.zones.exit_commands[
                                    self.current_square - 1
                                ]
                                self.current_square = 0
                                found_object_for_state_change = True

        end_time = time.perf_counter()
        log.debug(
            "frame.processing.time",
            duration_ms=(end_time - start_time) * 1000,
            plugin=self.plugin.get_name(),
        )

        return detections_in_polygon, command_to_send

    def draw_overlay(self, frame, detections):
        """
        Draws detection overlays on the frame.
        """
        # Draw the area-of-interest squares
        for i, ((x1, y1), (x2, y2)) in enumerate(self.scaled_squares):
            # Check if there are enough colors defined
            if i < len(self.zones.colors):
                cv2.rectangle(frame, (x1, y1), (x2, y2), self.zones.colors[i], 2)

        # Draw the processing area polygon
        if self.scaled_polygon.any():
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

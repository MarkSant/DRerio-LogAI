import time

import cv2
import numpy as np
import structlog

from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import settings

log = structlog.get_logger()


class Detector:
    """
    Manages the detection process by delegating to a plugin and handling
    stateful logic for zone tracking.
    """

    def __init__(self, plugin: DetectorPlugin):
        """
        Initializes the detector with a specific plugin.

        Args:
            plugin (DetectorPlugin): An instantiated detector plugin.
        """
        self.plugin = plugin
        if not self.plugin:
            log.error("detector.init.no_plugin")
            raise ValueError("Detector must be initialized with a valid plugin.")

        log.info("detector.init.success", plugin=self.plugin.get_name())

        # State variables for tracking object movement
        self.crossed_in = False
        self.crossed_out = False
        self.flag = 0  # 0: looking for entry, 1: looking for exit
        self.current_square = 0

        # Zone coordinates are defined in settings and scaled for the video resolution.
        self.base_polygon = np.array(settings.detection_zones.polygon, dtype=np.int32)
        self.base_squares = settings.detection_zones.squares
        self.scaled_polygon = self.base_polygon
        self.scaled_squares = self.base_squares
        self.update_scaling(
            settings.camera.desired_width, settings.camera.desired_height
        )

    def update_scaling(self, actual_width: int, actual_height: int):
        """
        Updates the coordinates of the polygon and squares based on the actual
        video resolution.
        """
        base_width = settings.camera.desired_width
        base_height = settings.camera.desired_height

        if actual_width == base_width and actual_height == base_height:
            self.scaled_polygon = self.base_polygon
            self.scaled_squares = self.base_squares
            return

        scale_x = actual_width / base_width
        scale_y = actual_height / base_height

        self.scaled_polygon = (self.base_polygon * [scale_x, scale_y]).astype(np.int32)
        self.scaled_squares = []
        for p1, p2 in self.base_squares:
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
                                    command_to_send = (
                                        settings.detection_zones.enter_commands[index]
                                    )
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
                                command_to_send = (
                                    settings.detection_zones.exit_commands[
                                        self.current_square - 1
                                    ]
                                )
                                self.current_square = 0
                                found_object_for_state_change = True

        end_time = time.perf_counter()
        log.debug(
            "frame.processing.time",
            duration_ms=(end_time - start_time) * 1000,
            plugin=self.plugin.get_name(),
        )

        return detections_in_polygon, command_to_send


def draw_overlay(frame, detections, detector_instance):
    """
    Draws detection overlays on the frame.
    """
    # Draw the area-of-interest squares
    for i, ((x1, y1), (x2, y2)) in enumerate(detector_instance.scaled_squares):
        cv2.rectangle(frame, (x1, y1), (x2, y2), settings.detection_zones.colors[i], 2)

    # Draw the processing area polygon
    cv2.polylines(
        frame,
        [detector_instance.scaled_polygon],
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

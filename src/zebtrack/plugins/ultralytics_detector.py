from typing import Tuple

import numpy as np
from ultralytics import YOLO
from ultralytics.engine.results import Boxes, Masks

from zebtrack.core.datastructures import Detection
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import settings


class UltralyticsDetectorPlugin(DetectorPlugin):
    """A detector plugin that uses the ultralytics YOLO model."""

    def __init__(self, model_path: str):
        """
        Initializes the YOLO model.

        Args:
            model_path (str): The path to the .pt model file.
        """
        self.model = YOLO(model_path)
        self.conf_threshold = settings.yolo_model.confidence_threshold
        self.nms_threshold = settings.yolo_model.nms_threshold

    def detect(self, frame: np.ndarray, diagnostic: bool = False) -> list[Detection]:
        """
        Performs object detection and tracking.

        In standard mode, it tracks only 'zebrafish'.
        In diagnostic mode, it detects all classes and does not perform tracking.

        Args:
            frame (np.ndarray): The input image.
            diagnostic (bool): If True, detects all classes and includes masks.

        Returns:
            A list of Detection objects.
        """
        if diagnostic:
            # For diagnostics, we want raw detections of all classes, no tracking
            results = self.model.predict(
                frame,
                verbose=False,
                conf=self.conf_threshold,
                iou=self.nms_threshold,
                classes=None,  # Detect all classes
            )
        else:
            # For standard analysis, we track only the zebrafish class
            results = self.model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                verbose=False,
                conf=self.conf_threshold,
                iou=self.nms_threshold,
                classes=1,  # Track only the 'zebrafish' class
            )

        predictions = []
        if not results or not results[0].boxes:
            return predictions

        boxes: Boxes = results[0].boxes
        masks: Masks | None = results[0].masks

        for i in range(len(boxes)):
            class_id = int(boxes.cls[i])
            has_masks = masks and masks.xy is not None and len(masks.xy) > i
            mask_coords = masks.xy[i] if has_masks else None

            predictions.append(
                Detection(
                    box=boxes.xyxy[i].cpu().numpy(),
                    mask=mask_coords,
                    confidence=float(boxes.conf[i]),
                    class_id=class_id,
                    class_name=self.model.names.get(class_id, f"ID {class_id}"),
                )
            )

        return predictions

    @staticmethod
    def get_name() -> str:
        return "YOLO (Ultralytics)"

    @property
    def model_input_shape(self) -> Tuple[int, int]:
        # This is a bit of a simplification. YOLOv8 can handle various input sizes,
        # but 640 is the default and what's implicitly used.
        return 640, 640

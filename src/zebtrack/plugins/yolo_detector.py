from typing import List, Tuple

import numpy as np
import torch
from ultralytics import YOLO

from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import settings


class YOLOv8Plugin(DetectorPlugin):
    """A detector plugin that uses the ultralytics YOLOv8 model."""

    def __init__(self, model_path: str):
        """
        Initializes the YOLOv8 model.

        Args:
            model_path (str): The path to the .pt model file.
        """
        self.model = YOLO(model_path)
        self.conf_threshold = settings.yolo_model.confidence_threshold
        self.nms_threshold = settings.yolo_model.nms_threshold

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
        """
        Performs inference using the YOLOv8 model.
        """
        use_half = torch.cuda.is_available()
        results = self.model(
            frame,
            verbose=False,
            conf=self.conf_threshold,
            iou=self.nms_threshold,
            half=use_half,
        )

        predictions = []
        for det in results[0].boxes.data.cpu().numpy():
            x1, y1, x2, y2, confidence, _ = det
            predictions.append((int(x1), int(y1), int(x2), int(y2), float(confidence)))

        return predictions

    @staticmethod
    def get_name() -> str:
        return "YOLOv8 (Ultralytics)"

    @property
    def model_input_shape(self) -> Tuple[int, int]:
        # This is a bit of a simplification. YOLOv8 can handle various input sizes,
        # but 640 is the default and what's implicitly used.
        # For a more robust implementation, one might inspect the model's properties.
        return (640, 640)

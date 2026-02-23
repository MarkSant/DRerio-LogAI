from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


class DetectorPlugin(ABC):
    """
    Abstract Base Class for a detector plugin.

    This interface defines the contract that all detector plugins must follow,
    ensuring they can be used interchangeably by the main Detector class.
    """

    conf_threshold: float = 0.25
    nms_threshold: float = 0.45

    @abstractmethod
    def __init__(self, model_path: Path | str):
        """
        Initializes the plugin and loads the specified model.

        Args:
            model_path: The path to the model file or directory.
        """
        pass

    @abstractmethod
    def detect(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[tuple[int, int, int, int, float, int | None, int]]:
        """
        Performs object detection on a single frame.

        Args:
            frame (np.ndarray): The input video frame.
            conf_threshold (float, optional): Confidence threshold override.

        Returns:
            A list of detections. Each detection is a tuple containing:
            (x1, y1, x2, y2, confidence, track_id, class_id).
            ``track_id`` should be ``None`` when the underlying model does not
            provide identity assignments for the detections.
        """
        pass

    @staticmethod
    @abstractmethod
    def get_name() -> str:
        """
        Returns the user-friendly name of the plugin.
        e.g., "YOLOv8 (Ultralytics)"
        """
        pass

    @property
    @abstractmethod
    def model_input_shape(self) -> tuple[int, int]:
        """
        Returns the expected input shape (height, width) of the model.
        """
        pass

    def detect_batch(
        self,
        frames: list[np.ndarray],
        conf_threshold: float | None = None,
    ) -> list[list[tuple[int, int, int, int, float, int | None, int]]]:
        """Process multiple frames in a single call (batch inference).

        The default implementation falls back to sequential ``detect()`` calls.
        Plugins that support native batch inference should override this.

        Args:
            frames: List of BGR frames.
            conf_threshold: Optional confidence threshold override.

        Returns:
            List of detection lists, one per input frame.
        """
        return [self.detect(frame, conf_threshold=conf_threshold) for frame in frames]

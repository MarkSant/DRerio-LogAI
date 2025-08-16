from abc import ABC, abstractmethod
from typing import List, Tuple

import numpy as np


class DetectorPlugin(ABC):
    """
    Abstract Base Class for a detector plugin.

    This interface defines the contract that all detector plugins must follow,
    ensuring they can be used interchangeably by the main Detector class.
    """

    @abstractmethod
    def __init__(self, model_path: str):
        """
        Initializes the plugin and loads the specified model.

        Args:
            model_path (str): The path to the model file or directory.
        """
        pass

    @abstractmethod
    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
        """
        Performs object detection on a single frame.

        Args:
            frame (np.ndarray): The input video frame.

        Returns:
            A list of detections. Each detection is a tuple containing:
            (x1, y1, x2, y2, confidence).
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
    def model_input_shape(self) -> Tuple[int, int]:
        """
        Returns the expected input shape (height, width) of the model.
        """
        pass

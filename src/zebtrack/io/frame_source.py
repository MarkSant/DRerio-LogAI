"""
This module defines the abstract base class for all frame sources.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

import numpy as np


class FrameSource(ABC):
    """
    An abstract base class for objects that provide frames, such as a camera
    or a video file.

    This class defines a common interface that all frame source implementations
    must adhere to, ensuring they can be used interchangeably within the
    application.
    """

    @abstractmethod
    def get_frame(self) -> Tuple[bool, np.ndarray | None]:
        """
        Reads the next frame from the source.

        Returns:
            A tuple containing:
            - A boolean value: True if a frame was successfully read,
              False otherwise (e.g., at the end of a video or on error).
            - A NumPy array representing the frame in BGR color format if
              successful, otherwise None.
        """
        pass

    @abstractmethod
    def release(self) -> None:
        """
        Releases the underlying video resource (e.g., camera or file).

        This method should be called when the source is no longer needed to
        free up system resources.
        """
        pass

    @abstractmethod
    def get_properties(self) -> Dict[str, Any]:
        """
        Returns a dictionary of key properties of the frame source.

        Common properties include 'width', 'height', and 'fps'.

        Returns:
            A dictionary containing the source's properties.
        """
        pass

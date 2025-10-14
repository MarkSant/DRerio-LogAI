"""
This module provides a factory function for creating frame sources.
"""

from typing import Any

from zebtrack.io.camera import Camera
from zebtrack.io.frame_source import FrameSource
from zebtrack.io.video_source import VideoFileSource


def create_source(source_type: str, **kwargs: Any) -> FrameSource:
    """
    Factory function to create a frame source based on the specified type.

    Args:
        source_type (str): The type of source to create.
                           Supported values are "camera" and "file".
        **kwargs: Additional keyword arguments required by the specific
                  source's constructor.
                  - For "file" source_type, `video_path` (str) is required.

    Returns:
        An instance of a FrameSource subclass.

    Raises:
        ValueError: If an unsupported source_type is provided or if
                    required kwargs are missing.
    """
    if source_type == "camera":
        return Camera()
    elif source_type == "file":
        video_path = kwargs.get("video_path")
        if not video_path or not isinstance(video_path, str):
            raise ValueError("`video_path` keyword argument is required for 'file' source type.")
        return VideoFileSource(video_path=video_path)
    else:
        raise ValueError(
            f"Unsupported source type: {source_type}. Supported types are 'camera', 'file'."
        )

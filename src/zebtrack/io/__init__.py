"""
This package provides modules for input/output operations, including frame sources.
"""

from .camera import Camera
from .frame_source import FrameSource
from .live_stream_source import LiveStreamSource
from .video_source import VideoFileSource

__all__ = [
    "Camera",
    "FrameSource",
    "LiveStreamSource",
    "VideoFileSource",
]

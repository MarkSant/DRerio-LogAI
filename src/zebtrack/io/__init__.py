"""
This package provides modules for input/output operations, including frame sources.
"""

from .camera import Camera
from .frame_source import FrameSource
from .frame_source_factory import FrameSourceFactory
from .live_stream_source import LiveStreamSource
from .sources import create_source
from .video_source import VideoFileSource

__all__ = [
    "Camera",
    "FrameSource",
    "FrameSourceFactory",
    "LiveStreamSource",
    "VideoFileSource",
    "create_source",
]

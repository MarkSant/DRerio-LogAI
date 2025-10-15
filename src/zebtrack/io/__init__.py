"""
This package provides modules for input/output operations, including frame sources.
"""

from .camera import Camera
from .frame_source import FrameSource
from .sources import create_source
from .video_source import VideoFileSource

__all__ = ["Camera", "FrameSource", "VideoFileSource", "create_source"]

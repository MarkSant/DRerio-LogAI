"""Shared type definitions for ZebTrack-AI core modules.

This module contains commonly used type aliases to avoid duplication
across different manager modules.
"""

from typing import Literal

# Asset types supported by the system
AssetType = Literal["arena", "rois", "trajectory", "summary", "video"]

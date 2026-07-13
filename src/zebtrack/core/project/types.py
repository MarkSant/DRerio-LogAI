"""Shared type definitions for DRerio LogAI core modules.

This module contains commonly used type aliases to avoid duplication
across different manager modules.
"""

from typing import Literal

# Asset types supported by the system
AssetType = Literal["arena", "rois", "trajectory", "summary", "video"]

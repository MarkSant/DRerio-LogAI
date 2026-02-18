"""Detector plugin implementations and registry.

This package contains plugin implementations for different detection backends
(YOLO, OpenVINO) with graceful dependency handling.
"""

from zebtrack.plugins.base import DetectorPlugin

# A simple plugin registry. The keys are the user-facing names.
# The main application can use this to discover and instantiate plugins.
DETECTOR_PLUGINS: dict[str, type[DetectorPlugin]] = {}

try:
    from .ultralytics_detector import UltralyticsDetectorPlugin

    ULTRALYTICS_PLUGIN_AVAILABLE = True
    DETECTOR_PLUGINS[UltralyticsDetectorPlugin.get_name()] = UltralyticsDetectorPlugin
except ImportError:
    UltralyticsDetectorPlugin = None  # type: ignore[assignment,misc]  # conditional import
    ULTRALYTICS_PLUGIN_AVAILABLE = False

try:
    from .openvino_detector import OpenVINOPlugin

    OPENVINO_PLUGIN_AVAILABLE = True
    DETECTOR_PLUGINS[OpenVINOPlugin.get_name()] = OpenVINOPlugin
except ImportError:
    OpenVINOPlugin = None  # type: ignore[assignment,misc]  # conditional import
    OPENVINO_PLUGIN_AVAILABLE = False

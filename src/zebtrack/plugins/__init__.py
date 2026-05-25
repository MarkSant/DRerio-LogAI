"""Detector plugin implementations and registry.

This package contains plugin implementations for different detection backends
(YOLO, OpenVINO) with graceful dependency handling.
"""

from zebtrack.plugins.base import DetectorPlugin

# A simple plugin registry. The keys are the user-facing names.
# The main application can use this to discover and instantiate plugins.
DETECTOR_PLUGINS: dict[str, type[DetectorPlugin]] = {}
UltralyticsDetectorPlugin: type[DetectorPlugin] | None = None
OpenVINOPlugin: type[DetectorPlugin] | None = None

try:
    from .ultralytics_detector import UltralyticsDetectorPlugin as _UltralyticsDetectorPlugin

    ULTRALYTICS_PLUGIN_AVAILABLE = True
    UltralyticsDetectorPlugin = _UltralyticsDetectorPlugin
    DETECTOR_PLUGINS[_UltralyticsDetectorPlugin.get_name()] = _UltralyticsDetectorPlugin
except ImportError:
    ULTRALYTICS_PLUGIN_AVAILABLE = False

try:
    from .openvino_detector import OpenVINOPlugin as _OpenVINOPlugin

    OPENVINO_PLUGIN_AVAILABLE = True
    OpenVINOPlugin = _OpenVINOPlugin
    DETECTOR_PLUGINS[_OpenVINOPlugin.get_name()] = _OpenVINOPlugin
except ImportError:
    OPENVINO_PLUGIN_AVAILABLE = False

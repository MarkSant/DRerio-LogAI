# Try to import plugins, but handle missing dependencies gracefully
try:
    from .ultralytics_detector import UltralyticsDetectorPlugin

    ULTRALYTICS_PLUGIN_AVAILABLE = True
except ImportError:
    UltralyticsDetectorPlugin = None
    ULTRALYTICS_PLUGIN_AVAILABLE = False

try:
    from .openvino_detector import OpenVINOPlugin

    OPENVINO_PLUGIN_AVAILABLE = True
except ImportError:
    OpenVINOPlugin = None
    OPENVINO_PLUGIN_AVAILABLE = False

# A simple plugin registry. The keys are the user-facing names.
# The main application can use this to discover and instantiate plugins.
DETECTOR_PLUGINS = {}

# Only add plugins if they're available
if ULTRALYTICS_PLUGIN_AVAILABLE:
    DETECTOR_PLUGINS[UltralyticsDetectorPlugin.get_name()] = UltralyticsDetectorPlugin

if OPENVINO_PLUGIN_AVAILABLE:
    DETECTOR_PLUGINS[OpenVINOPlugin.get_name()] = OpenVINOPlugin

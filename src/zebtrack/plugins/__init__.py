# Try to import plugins, but handle missing dependencies gracefully

# Declare plugin symbols with explicit optional types to help static analysis
UltralyticsDetectorPlugin: type | None = None
OpenVINOPlugin: type | None = None

try:
    from .ultralytics_detector import UltralyticsDetectorPlugin  # type: ignore

    ULTRALYTICS_PLUGIN_AVAILABLE = True
except ImportError:
    ULTRALYTICS_PLUGIN_AVAILABLE = False

try:
    from .openvino_detector import OpenVINOPlugin  # type: ignore

    OPENVINO_PLUGIN_AVAILABLE = True
except ImportError:
    OPENVINO_PLUGIN_AVAILABLE = False

# A simple plugin registry. The keys are the user-facing names.
# The main application can use this to discover and instantiate plugins.
DETECTOR_PLUGINS: dict[str, type] = {}

# Only add plugins if they're available
if ULTRALYTICS_PLUGIN_AVAILABLE and UltralyticsDetectorPlugin is not None:
    DETECTOR_PLUGINS[UltralyticsDetectorPlugin.get_name()] = UltralyticsDetectorPlugin

if OPENVINO_PLUGIN_AVAILABLE and OpenVINOPlugin is not None:
    DETECTOR_PLUGINS[OpenVINOPlugin.get_name()] = OpenVINOPlugin

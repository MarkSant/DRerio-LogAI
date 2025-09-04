from .openvino_detector import OpenVINOPlugin
from .ultralytics_detector import UltralyticsDetectorPlugin

# A simple plugin registry. The keys are the user-facing names.
# The main application can use this to discover and instantiate plugins.
DETECTOR_PLUGINS = {
    UltralyticsDetectorPlugin.get_name(): UltralyticsDetectorPlugin,
    OpenVINOPlugin.get_name(): OpenVINOPlugin,
}

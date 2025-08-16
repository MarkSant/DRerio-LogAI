from .openvino_detector import OpenVINOPlugin
from .yolo_detector import YOLOv8Plugin

# A simple plugin registry. The keys are the user-facing names.
# The main application can use this to discover and instantiate plugins.
DETECTOR_PLUGINS = {
    YOLOv8Plugin.get_name(): YOLOv8Plugin,
    OpenVINOPlugin.get_name(): OpenVINOPlugin,
}

"""
Extended unit tests for plugins registry in plugins/__init__.py.
"""

from __future__ import annotations

import zebtrack.plugins as plugins_pkg


class TestPluginsInitExtended:
    """Test plugin registry and availability flags."""

    def test_detector_plugins_registry(self):
        assert isinstance(plugins_pkg.DETECTOR_PLUGINS, dict)
        if plugins_pkg.ULTRALYTICS_PLUGIN_AVAILABLE:
            assert "YOLO (Ultralytics)" in plugins_pkg.DETECTOR_PLUGINS
            assert plugins_pkg.UltralyticsDetectorPlugin is not None

        if plugins_pkg.OPENVINO_PLUGIN_AVAILABLE:
            assert "OpenVINO" in plugins_pkg.DETECTOR_PLUGINS
            assert plugins_pkg.OpenVINOPlugin is not None

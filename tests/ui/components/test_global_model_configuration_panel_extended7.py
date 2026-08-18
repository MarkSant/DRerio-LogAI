"""Extended unit tests for ui/components/global_model_configuration_panel.py (Part 7)."""

from __future__ import annotations

from zebtrack.ui.components.global_model_configuration_panel import (
    _CONVERSION_POLL_INTERVAL_MS,
    _method_labels,
    _openvino_status_labels,
    _perspective_labels,
    _target_labels,
)


class TestGlobalModelConfigurationPanelExtended7:
    """Test global model configuration constants and label dictionaries."""

    def test_conversion_poll_interval_constant(self):
        assert _CONVERSION_POLL_INTERVAL_MS == 1500

    def test_openvino_status_labels_keys(self):
        labels = _openvino_status_labels()
        assert set(labels.keys()) == {"ready", "converting", "failed", "not_converted"}

    def test_perspective_labels_keys(self):
        labels = _perspective_labels()
        assert set(labels.keys()) == {"lateral", "top_down"}

    def test_target_labels_keys(self):
        labels = _target_labels()
        assert set(labels.keys()) == {"aquarium", "zebrafish"}

    def test_method_labels_keys(self):
        labels = _method_labels()
        assert set(labels.keys()) == {"seg", "det"}

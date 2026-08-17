"""Extended unit tests for ui/components/global_model_configuration_panel.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.global_model_configuration_panel import (
    _CONVERSION_POLL_INTERVAL_MS,
    GlobalModelConfigurationPanel,
    _method_labels,
    _openvino_status_labels,
    _perspective_labels,
    _strip_accents,
    _target_labels,
)


class TestGlobalModelConfigurationPanelExtended:
    """Test GlobalModelConfigurationPanel helper mappings, accent folding, and callbacks."""

    def test_constants_and_target_labels(self):
        assert _CONVERSION_POLL_INTERVAL_MS == 1500

        targets = _target_labels()
        assert "aquarium" in targets
        assert "zebrafish" in targets

    def test_method_and_perspective_labels(self):
        methods = _method_labels()
        assert "seg" in methods
        assert "det" in methods

        perspectives = _perspective_labels()
        assert "lateral" in perspectives
        assert "top_down" in perspectives

    def test_openvino_status_labels(self):
        statuses = _openvino_status_labels()
        assert "ready" in statuses
        assert "converting" in statuses
        assert "failed" in statuses
        assert "not_converted" in statuses

    def test_strip_accents(self):
        assert _strip_accents("aquário") == "aquario"
        assert _strip_accents("coração") == "coracao"
        assert _strip_accents("TESTE") == "TESTE"
        assert _strip_accents("") == ""

    def test_set_weight_refresh_callback(self):
        panel = object.__new__(GlobalModelConfigurationPanel)
        panel._refresh_weight_choices = None

        mock_cb = MagicMock()
        panel.set_weight_refresh_callback(mock_cb)
        assert panel._refresh_weight_choices is mock_cb

"""Extended unit tests for ui/components/global_model_configuration_panel.py (Part 6)."""

from __future__ import annotations

from zebtrack.ui.components.global_model_configuration_panel import (
    _method_labels,
    _openvino_status_labels,
    _perspective_labels,
    _strip_accents,
    _target_labels,
)


class TestGlobalModelConfigurationPanelExtended6:
    """Test helper functions, labels, and text normalization in global model config panel."""

    def test_target_labels(self):
        labels = _target_labels()
        assert "aquarium" in labels
        assert "zebrafish" in labels

    def test_method_labels(self):
        labels = _method_labels()
        assert "seg" in labels
        assert "det" in labels

    def test_perspective_labels(self):
        labels = _perspective_labels()
        assert "lateral" in labels
        assert "top_down" in labels

    def test_openvino_status_labels(self):
        labels = _openvino_status_labels()
        assert "ready" in labels
        assert "converting" in labels
        assert "failed" in labels
        assert "not_converted" in labels

    def test_strip_accents_folds_accents(self):
        assert _strip_accents("aquário") == "aquario"
        assert _strip_accents("configuração") == "configuracao"
        assert _strip_accents("teste") == "teste"

    def test_strip_accents_empty_string(self):
        assert _strip_accents("") == ""
        assert _strip_accents("   ") == "   "

    def test_strip_accents_no_accents(self):
        assert _strip_accents("zebrafish") == "zebrafish"

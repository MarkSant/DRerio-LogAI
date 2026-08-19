"""Extended unit tests for ui/components/global_model_configuration_panel.py."""

from __future__ import annotations

from zebtrack.ui.components.global_model_configuration_panel import (
    _CONVERSION_POLL_INTERVAL_MS,
    _method_labels,
    _openvino_status_labels,
    _perspective_labels,
    _strip_accents,
    _target_labels,
)


class TestGlobalModelConfigurationPanelExtended2:
    """Test label mappings, accent stripping, and polling intervals."""

    def test_constants_and_intervals(self):
        assert _CONVERSION_POLL_INTERVAL_MS == 1500

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

    def test_strip_accents(self):
        assert _strip_accents("aquário") == "aquario"
        assert _strip_accents("olá mundo") == "ola mundo"
        assert _strip_accents("teste rápido") == "teste rapido"
        assert _strip_accents("plain ascii") == "plain ascii"

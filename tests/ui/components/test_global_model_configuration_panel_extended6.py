"""Extended unit tests for ui/components/global_model_configuration_panel.py (Part 6)."""

from __future__ import annotations

from zebtrack.ui.components.global_model_configuration_panel import (
    _strip_accents,
)


class TestGlobalModelConfigurationPanelExtended6:
    """Test helper functions, labels, and text normalization in global model config panel."""

    def test_strip_accents_folds_accents(self):
        assert _strip_accents("aquário") == "aquario"
        assert _strip_accents("configuração") == "configuracao"
        assert _strip_accents("teste") == "teste"

    def test_strip_accents_empty_string(self):
        assert _strip_accents("") == ""
        assert _strip_accents("   ") == "   "

    def test_strip_accents_no_accents(self):
        assert _strip_accents("zebrafish") == "zebrafish"

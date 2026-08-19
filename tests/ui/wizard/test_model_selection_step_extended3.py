"""Extended unit tests for ui/wizard/model_selection_step.py."""

from __future__ import annotations

from zebtrack.ui.wizard.model_selection_step import (
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_MAX_CENTER_DISTANCE,
    DEFAULT_TRACK_BUFFER,
    DEFAULT_TRACK_THRESHOLD,
    _method_options,
    _recommended_suffix,
)


class TestModelSelectionStepExtended3:
    """Test ModelSelectionStep constants and method options."""

    def test_method_options(self):
        opts = _method_options()
        assert "seg" in opts
        assert "det" in opts
        assert "Segmentation" in opts["seg"] or "seg" in opts["seg"]
        assert "Detection" in opts["det"] or "det" in opts["det"]

    def test_recommended_suffix(self):
        suffix = _recommended_suffix()
        assert "⭐" in suffix or "Recommended" in suffix

    def test_bytetrack_types(self):
        assert isinstance(DEFAULT_TRACK_THRESHOLD, float)
        assert isinstance(DEFAULT_MATCH_THRESHOLD, float)
        assert isinstance(DEFAULT_TRACK_BUFFER, int)
        assert isinstance(DEFAULT_MAX_CENTER_DISTANCE, float)

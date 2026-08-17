"""Extended unit tests for analysis/visualization_generator.py."""

from __future__ import annotations

import pytest

from zebtrack.analysis.visualization_generator import (
    PLOT_GENERATION_TIMEOUT_SECONDS,
    _normalize_color_for_matplotlib,
)


class TestVisualizationGeneratorExtended2:
    """Test visualization generator constants and color normalization."""

    def test_constants(self):
        assert PLOT_GENERATION_TIMEOUT_SECONDS == 60

    def test_normalize_color_for_matplotlib_rgb_255(self):
        rgb_255 = (255, 128, 0)
        norm = _normalize_color_for_matplotlib(rgb_255)
        assert norm[0] == pytest.approx(1.0)
        assert norm[1] == pytest.approx(128 / 255.0)
        assert norm[2] == pytest.approx(0.0)

    def test_normalize_color_for_matplotlib_already_normalized(self):
        rgb_1 = (1.0, 0.5, 0.0)
        assert _normalize_color_for_matplotlib(rgb_1) == (1.0, 0.5, 0.0)

    def test_normalize_color_for_matplotlib_string_color(self):
        assert _normalize_color_for_matplotlib("red") == "red"
        assert _normalize_color_for_matplotlib("#FF0000") == "#FF0000"

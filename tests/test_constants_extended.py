"""Unit tests for application constants in constants.py."""

from __future__ import annotations

from zebtrack.constants import (
    DEFAULT_FLUSH_INTERVAL_SECONDS,
    DEFAULT_FLUSH_ROW_THRESHOLD,
    DEFAULT_MAX_PARALLEL_PLOTS,
    SPLASH_CLOSE_DELAY_MS,
    SPLASH_HEIGHT,
    SPLASH_WIDTH,
    WIZARD_MIN_HEIGHT,
    WIZARD_MIN_WIDTH,
    WIZARD_TARGET_HEIGHT,
    WIZARD_TARGET_WIDTH,
)


class TestConstantsExtended:
    """Test that application constants are present, typed, and sane."""

    def test_recorder_flush_interval_is_positive_float(self):
        assert isinstance(DEFAULT_FLUSH_INTERVAL_SECONDS, float)
        assert DEFAULT_FLUSH_INTERVAL_SECONDS > 0

    def test_recorder_flush_row_threshold_is_positive_int(self):
        assert isinstance(DEFAULT_FLUSH_ROW_THRESHOLD, int)
        assert DEFAULT_FLUSH_ROW_THRESHOLD > 0

    def test_splash_dimensions_are_positive(self):
        assert SPLASH_WIDTH > 0
        assert SPLASH_HEIGHT > 0
        assert SPLASH_CLOSE_DELAY_MS >= 0

    def test_wizard_target_larger_than_minimum(self):
        assert WIZARD_TARGET_WIDTH >= WIZARD_MIN_WIDTH
        assert WIZARD_TARGET_HEIGHT >= WIZARD_MIN_HEIGHT

    def test_wizard_dimensions_are_positive(self):
        assert WIZARD_MIN_WIDTH > 0
        assert WIZARD_MIN_HEIGHT > 0
        assert WIZARD_TARGET_WIDTH > 0
        assert WIZARD_TARGET_HEIGHT > 0

    def test_max_parallel_plots_is_positive(self):
        assert isinstance(DEFAULT_MAX_PARALLEL_PLOTS, int)
        assert DEFAULT_MAX_PARALLEL_PLOTS >= 1

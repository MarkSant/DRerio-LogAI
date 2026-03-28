"""Tests for zebtrack.constants module."""

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


class TestConstantsValues:
    """Ensure constants have the expected documented values."""

    def test_flush_interval_seconds(self):
        assert DEFAULT_FLUSH_INTERVAL_SECONDS == 5.0

    def test_flush_row_threshold(self):
        assert DEFAULT_FLUSH_ROW_THRESHOLD == 500

    def test_splash_width(self):
        assert SPLASH_WIDTH == 500

    def test_splash_height(self):
        assert SPLASH_HEIGHT == 400

    def test_splash_close_delay(self):
        assert SPLASH_CLOSE_DELAY_MS == 300

    def test_wizard_target_width(self):
        assert WIZARD_TARGET_WIDTH == 1050

    def test_wizard_target_height(self):
        assert WIZARD_TARGET_HEIGHT == 780

    def test_wizard_min_width(self):
        assert WIZARD_MIN_WIDTH == 900

    def test_wizard_min_height(self):
        assert WIZARD_MIN_HEIGHT == 650

    def test_max_parallel_plots(self):
        assert DEFAULT_MAX_PARALLEL_PLOTS == 3

    def test_all_positive(self):
        """All constants must be positive numbers."""
        for val in (
            DEFAULT_FLUSH_INTERVAL_SECONDS,
            DEFAULT_FLUSH_ROW_THRESHOLD,
            SPLASH_WIDTH,
            SPLASH_HEIGHT,
            SPLASH_CLOSE_DELAY_MS,
            WIZARD_TARGET_WIDTH,
            WIZARD_TARGET_HEIGHT,
            WIZARD_MIN_WIDTH,
            WIZARD_MIN_HEIGHT,
            DEFAULT_MAX_PARALLEL_PLOTS,
        ):
            assert val > 0

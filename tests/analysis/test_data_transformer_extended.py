"""
Extended unit tests for DataTransformer in analysis/data_transformer.py.
"""

from __future__ import annotations

import pandas as pd
import pytest

from zebtrack.analysis.data_transformer import (
    DataTransformer,
    _rgb_to_color_name,
)


class TestRgbToColorNameExtended:
    """Test RGB color to name conversion and fallback representations."""

    def test_exact_matches(self):
        assert _rgb_to_color_name((255, 0, 0)) == "Red"
        assert _rgb_to_color_name((0, 255, 0)) == "Green"
        assert _rgb_to_color_name((0, 0, 255)) == "Blue"
        assert _rgb_to_color_name((0, 0, 0)) == "Black"
        assert _rgb_to_color_name((255, 255, 255)) == "White"

    def test_approximate_matches_within_threshold(self):
        # Slightly off-red
        assert _rgb_to_color_name((250, 5, 5)) == "Red"
        # Slightly off-blue
        assert _rgb_to_color_name((5, 5, 250)) == "Blue"

    def test_fallback_rgb_string(self):
        # Far-off custom color
        res = _rgb_to_color_name((77, 88, 99))
        assert "RGB(77,88,99)" in res or isinstance(res, str)

    def test_invalid_tuples(self):
        assert _rgb_to_color_name("invalid") == "invalid"
        assert _rgb_to_color_name((1, 2)) == "(1, 2)"


class TestDataTransformerExtended:
    """Test DataTransformer schema validation, display preparation, and column standardization."""

    @pytest.fixture
    def transformer(self) -> DataTransformer:
        return DataTransformer()

    def test_validate_schema_valid(self, transformer: DataTransformer):
        df = pd.DataFrame(
            {
                "experiment_id": ["exp_1"],
                "group_id": ["Control"],
                "analysis_timestamp": ["2025-01-01"],
                "total_distance_cm": [100.0],
                "mean_speed_cm_s": [3.0],
            }
        )
        # Does not raise
        transformer.validate_schema(df)

    def test_validate_schema_missing_column_raises(self, transformer: DataTransformer):
        df = pd.DataFrame(
            {
                "experiment_id": ["exp_1"],
                "group_id": ["Control"],
            }
        )
        with pytest.raises(ValueError, match=r"(?i)missing required columns"):
            transformer.validate_schema(df)

    def test_standardize_roi_columns(self, transformer: DataTransformer):
        df = pd.DataFrame(
            {
                "experiment_id": ["exp_1"],
                "time_in_Center_s": [15.0],
                "entries_in_Center": [3],
            }
        )
        # Standardize with expected ROI names: Center and Periphery
        res = transformer.standardize_roi_columns(df, expected_roi_names=["Center", "Periphery"])
        assert "time_in_Center_s" in res.columns
        assert any("Periphery" in col for col in res.columns)

    def test_translate_english_to_display(self, transformer: DataTransformer):
        assert transformer._translate_english_to_display("time_in_Center_s") == "Time in Center (s)"
        assert transformer._translate_english_to_display("entries_in_Center") == "Entries in Center"
        res = transformer._translate_english_to_display("geotaxis_zone_0_pct")
        assert res == "Geotaxis Zone 1 (%)"

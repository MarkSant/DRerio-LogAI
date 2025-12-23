import pandas as pd
import pytest
from zebtrack.analysis.data_transformer import DataTransformer


class TestGeotaxisNaming:
    def test_rename_geotaxis_columns_3_zones(self):
        """Test renaming for standard 3 zones (Bottom, Middle, Surface)."""
        dt = DataTransformer()
        height_cm = 15.0
        num_zones = 3

        # Mapping input column -> expected output
        test_cases = {
            "geotaxis_zone_0_pct": "Fundo (0.0-5.0cm) [%]",
            "geotaxis_zone_1_pct": "Meio (5.0-10.0cm) [%]",
            "geotaxis_zone_2_pct": "Superfície (10.0-15.0cm) [%]",
        }

        # Create DataFrame with all columns
        df = pd.DataFrame(columns=list(test_cases.keys()))

        result_df = dt.rename_geotaxis_columns(df, height_cm, num_zones)

        for input_col, expected in test_cases.items():
            assert expected in result_df.columns, f"Expected {expected} for input {input_col}"
            assert input_col not in result_df.columns

    def test_rename_geotaxis_columns_4_zones(self):
        """Test renaming for 4 zones (Bottom, Meio 1, Meio 2, Surface)."""
        dt = DataTransformer()
        height_cm = 20.0
        num_zones = 4

        test_cases = {
            "geotaxis_zone_0_pct": "Fundo (0.0-5.0cm) [%]",
            "geotaxis_zone_1_pct": "Meio 1 (5.0-10.0cm) [%]",
            "geotaxis_zone_2_pct": "Meio 2 (10.0-15.0cm) [%]",
            "geotaxis_zone_3_pct": "Superfície (15.0-20.0cm) [%]",
        }

        df = pd.DataFrame(columns=list(test_cases.keys()))
        result_df = dt.rename_geotaxis_columns(df, height_cm, num_zones)

        for input_col, expected in test_cases.items():
            assert expected in result_df.columns

    def test_rename_geotaxis_columns_2_zones(self):
        """Test renaming for 2 zones (Bottom, Surface)."""
        dt = DataTransformer()
        height_cm = 10.0
        num_zones = 2

        test_cases = {
            "geotaxis_zone_0_pct": "Fundo (0.0-5.0cm) [%]",
            "geotaxis_zone_1_pct": "Superfície (5.0-10.0cm) [%]",
        }

        df = pd.DataFrame(columns=list(test_cases.keys()))
        result_df = dt.rename_geotaxis_columns(df, height_cm, num_zones)

        for input_col, expected in test_cases.items():
            assert expected in result_df.columns

    def test_ignore_non_geotaxis_columns(self):
        """Ensure non-geotaxis columns are left untouched."""
        dt = DataTransformer()
        cols = ["Total Distance", "Average Speed", "geotaxis_zone_0_pct"]
        expected_cols = ["Total Distance", "Average Speed", "Fundo (0.0-5.0cm) [%]"]

        df = pd.DataFrame(columns=cols)
        result_df = dt.rename_geotaxis_columns(df, height_cm=15.0, num_zones=3)

        assert list(result_df.columns) == expected_cols

    def test_handles_missing_params(self):
        """Should return original columns if height_cm or num_zones is None."""
        dt = DataTransformer()
        cols = ["geotaxis_zone_0_pct"]
        df = pd.DataFrame(columns=cols)

        # Test missing height
        res1 = dt.rename_geotaxis_columns(df, None, 3)
        assert list(res1.columns) == cols

        # Test missing num_zones
        res2 = dt.rename_geotaxis_columns(df, 15.0, None)
        assert list(res2.columns) == cols

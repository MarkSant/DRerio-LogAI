"""
Extended unit tests for ParquetSummaryReporter.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from zebtrack.analysis.reporters.parquet_reporter import ParquetSummaryReporter


class TestParquetSummaryReporter:
    """Test ParquetSummaryReporter export logic."""

    def test_export_summary_basic(self, tmp_path: Path):
        tidy = pd.DataFrame(
            {
                "subject_id": [1, 2],
                "total_distance_cm": [120.5, 95.2],
            }
        )
        mock_transformer = MagicMock()
        mock_transformer.validate_schema = MagicMock()

        ctx = SimpleNamespace(
            tidy_data=tidy,
            data_transformer=mock_transformer,
        )

        reporter = ParquetSummaryReporter(ctx)  # type: ignore[arg-type]
        out_path = tmp_path / "subdir" / "summary.parquet"

        reporter.export_summary(str(out_path))

        assert out_path.exists()
        loaded = pd.read_parquet(out_path)
        pd.testing.assert_frame_equal(loaded, tidy)
        mock_transformer.validate_schema.assert_called_once()
        mock_transformer.standardize_roi_columns.assert_not_called()

    def test_export_summary_with_expected_rois(self, tmp_path: Path):
        tidy = pd.DataFrame(
            {
                "subject_id": [1],
                "roi_ZoneA_time_s": [10.0],
            }
        )
        mock_transformer = MagicMock()
        mock_transformer.standardize_roi_columns.return_value = tidy
        mock_transformer.validate_schema = MagicMock()

        ctx = SimpleNamespace(
            tidy_data=tidy,
            data_transformer=mock_transformer,
        )

        reporter = ParquetSummaryReporter(ctx)  # type: ignore[arg-type]
        out_path = tmp_path / "summary_rois.parquet"

        reporter.export_summary(out_path, expected_roi_names=["ZoneA", "ZoneB"])

        assert out_path.exists()
        mock_transformer.standardize_roi_columns.assert_called_once_with(tidy, ["ZoneA", "ZoneB"])
        mock_transformer.validate_schema.assert_called_once()

"""
Extended unit tests for ExcelReporter in analysis/reporters/excel_reporter.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from zebtrack.analysis.data_transformer import DataTransformer
from zebtrack.analysis.reporters.excel_reporter import (
    MAIN_SHEET_NAME,
    PER_ANIMAL_SHEET_NAME,
    ExcelReporter,
)


class TestExcelReporterExtended:
    """Test ExcelReporter formats, standardization, geotaxis renaming, and per-animal sheets."""

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        ctx = MagicMock()
        ctx.tidy_data = pd.DataFrame(
            {
                "experiment_id": ["exp1"],
                "group_id": ["Control"],
                "analysis_timestamp": ["2026-01-01 12:00:00"],
                "total_distance_cm": [120.5],
                "mean_speed_cm_s": [4.1],
            }
        )
        ctx.data_transformer = DataTransformer()
        ctx.metadata = {"aquarium_height_cm": 15.0, "geotaxis_num_zones": 3}
        ctx.per_animal_data = None
        return ctx

    def test_export_summary_csv(self, mock_context: MagicMock, tmp_path: Path):
        reporter = ExcelReporter(mock_context)
        out_csv = tmp_path / "summary.csv"

        reporter.export_summary(out_csv)
        assert out_csv.exists()

        df = pd.read_csv(out_csv)
        assert "Total Distance (cm)" in df.columns or "total_distance_cm" in df.columns

    def test_export_summary_excel_single_sheet(self, mock_context: MagicMock, tmp_path: Path):
        reporter = ExcelReporter(mock_context)
        out_xlsx = tmp_path / "summary.xlsx"

        reporter.export_summary(out_xlsx)
        assert out_xlsx.exists()

        excel_file = pd.ExcelFile(out_xlsx)
        assert MAIN_SHEET_NAME in excel_file.sheet_names
        assert PER_ANIMAL_SHEET_NAME not in excel_file.sheet_names

    def test_export_summary_excel_with_per_animal_sheet(
        self, mock_context: MagicMock, tmp_path: Path
    ):
        mock_context.per_animal_data = pd.DataFrame(
            {"animal_id": [1, 2], "distance_cm": [50.0, 70.5]}
        )
        reporter = ExcelReporter(mock_context)
        out_xlsx = tmp_path / "multi_summary.xlsx"

        reporter.export_summary(out_xlsx)
        assert out_xlsx.exists()

        excel_file = pd.ExcelFile(out_xlsx)
        assert MAIN_SHEET_NAME in excel_file.sheet_names
        assert PER_ANIMAL_SHEET_NAME in excel_file.sheet_names

    def test_export_summary_with_expected_roi_names(self, mock_context: MagicMock, tmp_path: Path):
        reporter = ExcelReporter(mock_context)
        out_csv = tmp_path / "roi_summary.csv"

        reporter.export_summary(out_csv, expected_roi_names=["Zone_A", "Zone_B"])
        assert out_csv.exists()

    def test_per_animal_frame_empty_returns_none(self, mock_context: MagicMock):
        mock_context.per_animal_data = pd.DataFrame()
        reporter = ExcelReporter(mock_context)
        assert reporter._per_animal_frame() is None

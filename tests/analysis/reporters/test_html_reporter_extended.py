"""
Extended unit tests for HtmlReporter.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from zebtrack.analysis.reporters.html_reporter import HtmlReporter


class TestHtmlReporter:
    """Test HtmlReporter interactive report generation."""

    def test_missing_plotly_raises_import_error(self, tmp_path: Path):
        ctx = SimpleNamespace(b_analyzer=MagicMock())
        reporter = HtmlReporter(ctx)  # type: ignore[arg-type]

        with patch.dict(
            sys.modules, {"plotly": None, "plotly.graph_objects": None, "plotly.subplots": None}
        ):
            with pytest.raises(ImportError, match="Plotly is not installed"):
                reporter.export_interactive_html_report(tmp_path / "report.html")

    def test_missing_behavior_analyzer_raises_value_error(self, tmp_path: Path):
        ctx = SimpleNamespace(b_analyzer=None)
        reporter = HtmlReporter(ctx)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="BehaviorAnalyzer not available"):
            reporter.export_interactive_html_report(tmp_path / "report.html")

    def test_export_interactive_html_report_success(self, tmp_path: Path):
        traj_df = pd.DataFrame(
            {
                "x_cm": [0.0, 1.0, 2.0, 3.0],
                "y_cm": [0.0, 1.0, 0.0, 1.0],
            },
            index=[0, 1, 2, 3],
        )

        mock_b_analyzer = MagicMock()
        mock_b_analyzer.trajectory_data = traj_df
        mock_b_analyzer.calculate_velocity_timeseries.return_value = {
            "v_mag": pd.Series([1.0, 2.0, 0.5, 3.0])
        }
        mock_b_analyzer.detect_freezing_episodes.return_value = [
            {"start_frame": 2, "duration_s": 1.5}
        ]

        mock_r_analyzer = MagicMock()
        mock_r_analyzer.get_time_spent_in_rois.return_value = {"Zone1": 15.2, "Zone2": 8.4}

        ctx = SimpleNamespace(
            b_analyzer=mock_b_analyzer,
            r_analyzer=mock_r_analyzer,
            freezing_threshold=1.5,
            freezing_duration=1.0,
            metadata={"experiment_id": "EXP_001", "subject_id": "Fish_A", "fps": 30.0},
        )

        reporter = HtmlReporter(ctx)  # type: ignore[arg-type]
        out_file = tmp_path / "interactive_report.html"

        reporter.export_interactive_html_report(out_file)

        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "Interactive Analysis Report - EXP_001" in content
        assert "plotly" in content.lower()

"""
Extended unit tests for ScriptExporter.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from zebtrack.analysis.reporters.script_exporter import ScriptExporter


class TestScriptExporterExtended:
    """Test ScriptExporter export methods and script template generators."""

    def _create_exporter(self) -> ScriptExporter:
        df = pd.DataFrame(
            {
                "subject_id": [1, 2, 3],
                "group": ["Control", "Control", "Treated"],
                "total_distance_cm": [120.0, 115.0, 80.0],
                "freezing_duration_s": [10.0, 12.0, 35.0],
                "time_in_roi_ZoneA_s": [50.0, 60.0, 20.0],
            }
        )
        ctx = SimpleNamespace(
            tidy_data=df,
            metadata={"experiment_id": "EXP_001"},
        )
        return ScriptExporter(ctx)  # type: ignore[arg-type]

    def test_export_for_r(self, tmp_path: Path):
        exporter = self._create_exporter()
        out_dir = tmp_path / "r_export"

        files = exporter.export_for_r(out_dir, include_script=True)

        assert "feather" in files
        assert "csv" in files
        assert "script" in files
        assert files["feather"].exists()
        assert files["csv"].exists()
        assert files["script"].exists()

        script_content = files["script"].read_text(encoding="utf-8")
        assert "library(arrow)" in script_content
        assert "ggplot2" in script_content

    def test_export_for_r_without_script(self, tmp_path: Path):
        exporter = self._create_exporter()
        out_dir = tmp_path / "r_export_no_script"

        files = exporter.export_for_r(str(out_dir), include_script=False)
        assert "feather" in files
        assert "csv" in files
        assert "script" not in files

    def test_export_for_python(self, tmp_path: Path):
        exporter = self._create_exporter()
        out_dir = tmp_path / "py_export"

        files = exporter.export_for_python(out_dir, include_script=True)

        assert "parquet" in files
        assert "feather" in files
        assert "script" in files
        assert files["parquet"].exists()
        assert files["feather"].exists()
        assert files["script"].exists()

        script_content = files["script"].read_text(encoding="utf-8")
        assert "pandas as pd" in script_content
        assert "seaborn as sns" in script_content

    def test_export_for_python_without_script(self, tmp_path: Path):
        exporter = self._create_exporter()
        out_dir = tmp_path / "py_export_no_script"

        files = exporter.export_for_python(str(out_dir), include_script=False)
        assert "parquet" in files
        assert "feather" in files
        assert "script" not in files

    def test_convenience_export_methods(self, tmp_path: Path):
        exporter = self._create_exporter()

        feather_file = tmp_path / "custom" / "test.feather"
        res_f = exporter.export_feather(str(feather_file))
        assert res_f.exists()

        r_file = tmp_path / "custom" / "test.R"
        res_r = exporter.export_r_script(str(r_file))
        assert res_r.exists()

        py_file = tmp_path / "custom" / "test.py"
        res_py = exporter.export_python_script(str(py_file))
        assert res_py.exists()

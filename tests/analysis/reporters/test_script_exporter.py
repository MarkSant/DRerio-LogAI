"""Unit tests for ``zebtrack.analysis.reporters.ScriptExporter``.

The exporter produces the reproducibility artifacts (R/Python analysis scripts +
Feather/Parquet/CSV data dumps) that let a researcher re-run the analysis outside
the app — so its output is scientifically meaningful and worth pinning.

``ScriptExporter`` only reads ``ctx.tidy_data`` (a DataFrame) and the script
templates are static, so a lightweight stub context with a small DataFrame is
used instead of the heavy full-analysis fixture.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pyarrow.feather as feather
import pytest

from zebtrack.analysis.reporters.script_exporter import ScriptExporter


@pytest.fixture
def exporter():
    tidy = pd.DataFrame(
        {
            "subject_id": [1, 1, 2],
            "timestamp": [0.0, 0.1, 0.2],
            "x_cm": [1.0, 2.0, 3.0],
            "y_cm": [4.0, 5.0, 6.0],
            "velocity_cm_s": [0.5, 1.5, 2.5],
        }
    )
    return ScriptExporter(SimpleNamespace(tidy_data=tidy))


class TestScriptTemplates:
    def test_r_template_has_key_sections(self, exporter):
        script = exporter._generate_r_script_template()
        assert "ZebTrack-AI Analysis Script for R" in script
        assert "library(arrow)" in script
        assert 'read_feather("data.feather")' in script
        assert "ggplot" in script

    def test_python_template_has_key_sections(self, exporter):
        script = exporter._generate_python_script_template()
        assert "ZebTrack-AI Analysis Notebook" in script
        assert "import pandas as pd" in script
        assert 'read_parquet("data.parquet")' in script


class TestSingleFileExports:
    def test_export_r_script_writes_file(self, exporter, tmp_path):
        out = exporter.export_r_script(tmp_path / "analysis.R")
        assert out.exists()
        assert out.suffix == ".R"
        assert out.read_text(encoding="utf-8") == exporter._generate_r_script_template()

    def test_export_python_script_writes_file(self, exporter, tmp_path):
        out = exporter.export_python_script(tmp_path / "analysis.py")
        assert out.exists()
        assert "import pandas as pd" in out.read_text(encoding="utf-8")

    def test_export_script_creates_missing_parent_dirs(self, exporter, tmp_path):
        out = exporter.export_python_script(tmp_path / "nested" / "deep" / "nb.py")
        assert out.exists()

    def test_export_feather_round_trip(self, exporter, tmp_path):
        out = exporter.export_feather(tmp_path / "data.feather")
        assert out.exists()
        loaded = feather.read_feather(out)
        pd.testing.assert_frame_equal(loaded, exporter._ctx.tidy_data)


class TestBundledExports:
    def test_export_for_r_creates_all_files(self, exporter, tmp_path):
        created = exporter.export_for_r(tmp_path)
        assert set(created) == {"feather", "csv", "script"}
        assert all(p.exists() for p in created.values())
        assert created["script"].suffix == ".R"

    def test_export_for_r_without_script(self, exporter, tmp_path):
        created = exporter.export_for_r(tmp_path, include_script=False)
        assert "script" not in created
        assert set(created) == {"feather", "csv"}

    def test_export_for_python_creates_all_files(self, exporter, tmp_path):
        created = exporter.export_for_python(tmp_path)
        assert set(created) == {"parquet", "feather", "script"}
        assert all(p.exists() for p in created.values())
        assert created["script"].name == "analysis_notebook.py"

    def test_export_for_r_accepts_string_path(self, exporter, tmp_path):
        created = exporter.export_for_r(str(tmp_path / "rout"))
        assert created["feather"].exists()

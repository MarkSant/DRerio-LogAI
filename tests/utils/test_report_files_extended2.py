"""Extended unit tests for utils/report_files.py."""

from __future__ import annotations

from pathlib import Path

from zebtrack.utils.report_files import (
    describe_session_output,
    find_summary_excel_file,
    has_summary_excel_output,
    is_summary_excel_file,
)


class TestReportFilesExtended2:
    """Test report files discovery, naming detection, and description formatting."""

    def test_is_summary_excel_file_matches(self, tmp_path: Path):
        f1 = tmp_path / "4_RelatorioSumario_exp1.xlsx"
        f1.touch()
        f2 = tmp_path / "session_summary.xlsx"
        f2.touch()
        f3 = tmp_path / "trajectory_data.csv"
        f3.touch()

        assert is_summary_excel_file(f1) is True
        assert is_summary_excel_file(f2) is True
        assert is_summary_excel_file(f3) is False

    def test_find_and_has_summary_excel_file(self, tmp_path: Path):
        assert find_summary_excel_file(None) is None
        assert find_summary_excel_file(tmp_path / "missing_dir") is None
        assert has_summary_excel_output(tmp_path) is False

        summary_f = tmp_path / "4_RelatorioSumario_test.xlsx"
        summary_f.touch()

        assert find_summary_excel_file(tmp_path) == summary_f
        assert has_summary_excel_output(tmp_path) is True

    def test_describe_session_output(self):
        assert "arena" in describe_session_output(Path("1_ProcessingArea_vid.png"))
        assert "ROIs" in describe_session_output(Path("2_AreasOfInterest_vid.png"))
        assert "trajectory" in describe_session_output(Path("3_CoordMovimento_vid.parquet"))
        assert "segmentation masks" in describe_session_output(Path("3b_Mascaras_vid.parquet"))
        assert "summary" in describe_session_output(Path("4_RelatorioSumario_vid.xlsx"))
        assert "recorded video" in describe_session_output(Path("recording.mp4"))
        assert describe_session_output(Path("custom_file.txt")) == "custom_file.txt"

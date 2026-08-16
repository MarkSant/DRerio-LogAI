"""
Extended unit tests for report file discovery and labeling helpers.
"""

from __future__ import annotations

from pathlib import Path

from zebtrack.utils.report_files import (
    describe_session_output,
    find_block_partial_report_files,
    find_summary_excel_file,
    has_summary_excel_output,
    is_summary_excel_file,
    list_session_outputs,
    normalize_day_number,
)


class TestReportFilesExtended:
    """Test report file classification, labeling, and listing."""

    def test_is_summary_excel_file(self, tmp_path: Path):
        summary_xlsx = tmp_path / "4_Relatorio_video1.xlsx"
        summary_xlsx.touch()
        assert is_summary_excel_file(summary_xlsx) is True

        summary_xls = tmp_path / "session_summary.xls"
        summary_xls.touch()
        assert is_summary_excel_file(summary_xls) is True

        other_file = tmp_path / "3_CoordMovimento.parquet"
        other_file.touch()
        assert is_summary_excel_file(other_file) is False

    def test_find_summary_excel_file(self, tmp_path: Path):
        assert find_summary_excel_file(None) is None
        assert find_summary_excel_file(tmp_path / "nonexistent") is None

        # Empty dir
        assert find_summary_excel_file(tmp_path) is None

        # Add report and summary files
        rep = tmp_path / "4_Relatorio_general.xlsx"
        rep.touch()
        resumo_file = tmp_path / "4_Resumo_general.xlsx"
        resumo_file.touch()

        # Primary token ('resumo' / 'summary') preferred over secondary ('relatorio')
        best = find_summary_excel_file(tmp_path)
        assert best == resumo_file
        assert has_summary_excel_output(tmp_path) is True

    def test_describe_session_output(self, tmp_path: Path):
        p_arena = tmp_path / "1_ProcessingArea_001.png"
        expected_arena = "1_ProcessingArea_001.png (arena / processing area)"
        assert describe_session_output(p_arena) == expected_arena

        p_traj = tmp_path / "3_CoordMovimento_001.parquet"
        assert describe_session_output(p_traj) == "3_CoordMovimento_001.parquet (trajectory)"

        p_masks = tmp_path / "3b_Mascaras_001.parquet"
        assert describe_session_output(p_masks) == "3b_Mascaras_001.parquet (segmentation masks)"

        p_video = tmp_path / "recording.mp4"
        assert describe_session_output(p_video) == "recording.mp4 (recorded video)"

        p_unknown = tmp_path / "custom_data.csv"
        assert describe_session_output(p_unknown) == "custom_data.csv"

    def test_list_session_outputs(self, tmp_path: Path):
        assert list_session_outputs(None) == []
        assert list_session_outputs(tmp_path / "nonexistent") == []

        # Create files out of order
        f_traj = tmp_path / "3_CoordMovimento_001.parquet"
        f_traj.touch()
        f_arena = tmp_path / "1_ProcessingArea_001.png"
        f_arena.touch()
        f_sum = tmp_path / "4_RelatorioSumario_001.xlsx"
        f_sum.touch()

        listed = list_session_outputs(tmp_path)
        # Should be ordered by pipeline prefix:
        # 1_ProcessingArea, 3_CoordMovimento, 4_RelatorioSumario
        assert listed == [f_arena, f_traj, f_sum]

    def test_normalize_day_number(self):
        assert normalize_day_number(1) == 1
        assert normalize_day_number("Dia_2") == 2
        assert normalize_day_number("D03") == 3
        assert normalize_day_number("4") == 4
        assert normalize_day_number("") is None
        assert normalize_day_number(None) is None
        assert normalize_day_number("NoDigits") is None

    def test_find_block_partial_report_files(self, tmp_path: Path):
        assert find_block_partial_report_files(None, day_id=1, group_candidates=["Control"]) == []
        assert (
            find_block_partial_report_files(tmp_path, day_id=1, group_candidates=["Control"]) == []
        )

        reports_dir = tmp_path / "partial_reports"
        reports_dir.mkdir()

        f_xlsx = reports_dir / "PartialReport_Dia1_Control_summary.xlsx"
        f_xlsx.touch()
        f_docx = reports_dir / "PartialReport_Dia1_Control_doc.docx"
        f_docx.touch()
        f_other = reports_dir / "PartialReport_Dia2_Treatment.xlsx"
        f_other.touch()

        found = find_block_partial_report_files(
            tmp_path, day_id="Dia_1", group_candidates=["Control"]
        )
        assert len(found) == 2
        assert found[0] == f_xlsx
        assert found[1] == f_docx

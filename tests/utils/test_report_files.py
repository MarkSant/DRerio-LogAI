"""The live-session completion message must list what was really written.

The old message hardcoded three bullets. Two named files that do not exist
(``*_trajectory.parquet`` -- the real name is ``3_CoordMovimento_<base>.parquet``
-- and ``*_zones.parquet``, which is really two separate files) and one named an
extension the recorder never produces (``.avi``; ``recorder.py`` hardcodes
``.mp4``). Meanwhile it omitted the reports it had just written, the closed-loop
latency log and the frame ledger.
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

# A session WITH Arduino, ROIs and masks -- i.e. every conditional output on.
_FULL_SESSION = [
    "1_ProcessingArea_cam.parquet",
    "2_AreasOfInterest_cam.parquet",
    "3_CoordMovimento_cam.parquet",
    "3b_Mascaras_cam.parquet",
    "4_Relatorio_exp.xlsx",
    "4_Relatorio_exp.docx",
    "5_ClosedLoop_cam.csv",
    "6_FrameLedger_cam.csv",
    "6_FrameLedger_cam_anchor.json",
    "_recording_metadata.json",
    "cam.mp4",
]


def _make_session(tmp_path: Path, names: list[str]) -> Path:
    folder = tmp_path / "session"
    folder.mkdir()
    for name in names:
        (folder / name).write_text("x", encoding="utf-8")
    return folder


class TestListing:
    def test_lists_every_file_actually_written(self, tmp_path):
        folder = _make_session(tmp_path, _FULL_SESSION)

        listed = {p.name for p in list_session_outputs(folder)}

        assert listed == set(_FULL_SESSION)

    def test_includes_the_outputs_the_old_message_omitted(self, tmp_path):
        folder = _make_session(tmp_path, _FULL_SESSION)

        listed = {p.name for p in list_session_outputs(folder)}

        # The reports the researcher actually wants, plus the two audit trails.
        assert "4_Relatorio_exp.xlsx" in listed
        assert "4_Relatorio_exp.docx" in listed
        assert "5_ClosedLoop_cam.csv" in listed
        assert "6_FrameLedger_cam.csv" in listed

    def test_pipeline_order_not_alphabetical(self, tmp_path):
        folder = _make_session(tmp_path, _FULL_SESSION)

        names = [p.name for p in list_session_outputs(folder)]

        assert names.index("1_ProcessingArea_cam.parquet") < names.index(
            "3_CoordMovimento_cam.parquet"
        )
        assert names.index("3_CoordMovimento_cam.parquet") < names.index("4_Relatorio_exp.xlsx")
        # The video is not a numbered output; it sorts last.
        assert names[-1] == "cam.mp4"

    def test_conditional_outputs_simply_absent_when_not_produced(self, tmp_path):
        """No Arduino, no ROIs, no masks -- a static list would lie here."""
        folder = _make_session(
            tmp_path,
            ["1_ProcessingArea_cam.parquet", "3_CoordMovimento_cam.parquet", "cam.mp4"],
        )

        listed = {p.name for p in list_session_outputs(folder)}

        assert "5_ClosedLoop_cam.csv" not in listed
        assert "3b_Mascaras_cam.parquet" not in listed
        assert len(listed) == 3

    def test_missing_directory_returns_empty(self, tmp_path):
        assert list_session_outputs(tmp_path / "nope") == []
        assert list_session_outputs(None) == []


class TestDescriptions:
    def test_known_prefixes_get_a_label(self, tmp_path):
        assert "trajectory" in describe_session_output(Path("3_CoordMovimento_cam.parquet"))
        assert "frame ledger" in describe_session_output(Path("6_FrameLedger_cam.csv"))
        assert "closed-loop" in describe_session_output(Path("5_ClosedLoop_cam.csv"))

    def test_longer_prefix_wins(self, tmp_path):
        """``3b_Mascaras`` must not be labelled as the ``3_`` trajectory."""
        assert "mask" in describe_session_output(Path("3b_Mascaras_cam.parquet")).lower()
        assert "summary" in describe_session_output(Path("4_RelatorioSumario_exp.xlsx")).lower()

    def test_recorded_video_is_labelled_by_extension(self):
        assert "recorded video" in describe_session_output(Path("cam.mp4"))

    def test_unknown_file_degrades_to_its_bare_name(self):
        """Listing something unlabelled beats hiding it from the researcher."""
        assert describe_session_output(Path("something_new.bin")) == "something_new.bin"


class TestV8Outputs:
    """``3c_Objetos_`` (ADR-010) and ``7_AnalysisWindow_`` (ADR-011)."""

    def test_object_sidecar_is_labelled(self):
        assert describe_session_output(Path("3c_Objetos_cam.parquet")) == (
            "3c_Objetos_cam.parquet (detected objects per frame)"
        )

    def test_analysis_window_artifact_is_labelled(self):
        assert describe_session_output(Path("7_AnalysisWindow_cam.json")) == (
            "7_AnalysisWindow_cam.json (analysis window)"
        )

    def test_object_sidecar_is_not_taken_for_the_trajectory(self):
        assert "trajectory" not in describe_session_output(Path("3c_Objetos_cam.parquet"))

    def test_new_outputs_sit_in_pipeline_order(self, tmp_path):
        folder = _make_session(
            tmp_path,
            [*_FULL_SESSION, "3c_Objetos_cam.parquet", "7_AnalysisWindow_cam.json"],
        )

        names = [p.name for p in list_session_outputs(folder)]

        assert names.index("3b_Mascaras_cam.parquet") < names.index("3c_Objetos_cam.parquet")
        assert names.index("3c_Objetos_cam.parquet") < names.index("4_Relatorio_exp.docx")
        assert names.index("6_FrameLedger_cam_anchor.json") < names.index(
            "7_AnalysisWindow_cam.json"
        )
        assert names.index("7_AnalysisWindow_cam.json") < names.index("cam.mp4")

    def test_labels_follow_the_interface_language(self, monkeypatch):
        """Labels are UI text, resolved at call time through ``_()``."""
        from zebtrack.utils import report_files

        monkeypatch.setattr(report_files, "_", lambda text: f"<{text}>")

        assert describe_session_output(Path("3c_Objetos_cam.parquet")) == (
            "3c_Objetos_cam.parquet (<detected objects per frame>)"
        )
        assert describe_session_output(Path("cam.mp4")) == "cam.mp4 (<recorded video>)"


class TestReportFilesExtended:
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


class TestReportFilesExtended2:
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

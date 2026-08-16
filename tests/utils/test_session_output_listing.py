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

from zebtrack.utils.report_files import describe_session_output, list_session_outputs

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

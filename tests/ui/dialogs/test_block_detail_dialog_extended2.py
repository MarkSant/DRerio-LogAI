"""Extended unit tests for ui/dialogs/block_detail_dialog.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog, _block_label


class TestBlockDetailDialogExtended2:
    """Test BlockDetailDialog label formatting, day parsing, file status, and polygon source."""

    def test_block_label(self):
        label = _block_label(1, "Control")
        assert "1" in label
        assert "Control" in label

        label2 = _block_label("Dia_2", "Treated")
        assert "Dia_2" in label2
        assert "Treated" in label2

    def test_day_parsing_formats(self):
        # Test day parsing logic directly as done in __init__
        def parse_day(day: int | str) -> tuple[int, str]:
            day_num = day if isinstance(day, int) else int(day.replace("Dia_", "").replace("D", ""))
            day_str = f"Dia_{day_num}" if isinstance(day, int) else str(day)
            return day_num, day_str

        num1, str1 = parse_day(1)
        assert num1 == 1
        assert str1 == "Dia_1"

        num2, str2 = parse_day("Dia_3")
        assert num2 == 3
        assert str2 == "Dia_3"

        num3, str3 = parse_day("D5")
        assert num3 == 5
        assert str3 == "D5"

    def test_get_session_files_status_empty_dir(self, tmp_path: Path):
        dialog = object.__new__(BlockDetailDialog)
        status = dialog._get_session_files_status(tmp_path)
        assert status["video"] is False
        assert status["trajectory"] is False
        assert status["arena"] is False
        assert status["rois"] is False
        assert status["summary"] is False

    def test_get_session_files_status_with_files(self, tmp_path: Path):
        dialog = object.__new__(BlockDetailDialog)
        (tmp_path / "1_ProcessingArea_test.png").write_text("arena")
        (tmp_path / "3_CoordMovimento_test.parquet").write_text("trajectory")
        (tmp_path / "test.mp4").write_text("video")

        status = dialog._get_session_files_status(tmp_path)
        assert status["video"] is True
        assert status["trajectory"] is True
        assert status["arena"] is True
        assert status["rois"] is False
        assert status["summary"] is False

    def test_get_polygon_source_for_subject(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog.day_num = 1
        dialog.group_name = "Control"
        dialog.project_manager = MagicMock()
        dialog.project_manager.project_data = {
            "batches": [
                {
                    "videos": [
                        {
                            "metadata": {
                                "day": "Dia_1",
                                "group": "Control",
                                "subject": "Cobaia_1",
                                "polygon_source": "auto",
                            }
                        }
                    ]
                }
            ]
        }

        source = dialog._get_polygon_source_for_subject("Cobaia_1")
        assert source == "auto"

        source_none = dialog._get_polygon_source_for_subject("Cobaia_2")
        assert source_none is None

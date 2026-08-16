"""
Extended unit tests for VideoManager.
"""

from __future__ import annotations

from pathlib import Path

from zebtrack.core.project.video_manager import VideoManager


class TestVideoManagerScanInputPaths:
    """Test VideoManager.scan_input_paths for various inputs."""

    def test_scan_empty_list(self):
        result = VideoManager.scan_input_paths([])
        assert result == []

    def test_scan_nonexistent_path_ignored(self, tmp_path: Path):
        result = VideoManager.scan_input_paths([str(tmp_path / "nope.mp4")])
        assert result == []

    def test_scan_non_video_file_ignored(self, tmp_path: Path):
        txt = tmp_path / "doc.txt"
        txt.write_text("data")
        result = VideoManager.scan_input_paths([str(txt)])
        assert result == []

    def test_scan_mp4_file(self, tmp_path: Path):
        video = tmp_path / "sample.mp4"
        video.write_bytes(b"\x00" * 100)
        result = VideoManager.scan_input_paths([str(video)])
        assert len(result) == 1
        assert result[0]["path"].endswith("sample.mp4")
        assert result[0]["has_arena"] is False
        assert result[0]["has_rois"] is False
        assert result[0]["has_trajectory"] is False
        assert result[0]["has_complete_data"] is False
        assert result[0]["has_data"] is False

    def test_scan_mp4_with_parquet_files(self, tmp_path: Path):
        video = tmp_path / "my_video.mp4"
        video.write_bytes(b"\x00" * 100)
        (tmp_path / "1_ProcessingArea_my_video.parquet").write_bytes(b"")
        (tmp_path / "2_AreasOfInterest_my_video.parquet").write_bytes(b"")
        (tmp_path / "3_CoordMovimento_my_video.parquet").write_bytes(b"")
        result = VideoManager.scan_input_paths([str(video)])
        assert result[0]["has_arena"] is True
        assert result[0]["has_rois"] is True
        assert result[0]["has_trajectory"] is True
        assert result[0]["has_complete_data"] is True
        assert result[0]["has_data"] is True

    def test_scan_directory_finds_videos(self, tmp_path: Path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "clip1.mp4").write_bytes(b"\x00")
        (sub / "clip2.avi").write_bytes(b"\x00")
        result = VideoManager.scan_input_paths([str(tmp_path)])
        assert len(result) == 2
        paths = {r["path"] for r in result}
        assert any("clip1.mp4" in p for p in paths)
        assert any("clip2.avi" in p for p in paths)

    def test_scan_with_recording_metadata_json(self, tmp_path: Path):
        import json

        video = tmp_path / "vid.mp4"
        video.write_bytes(b"\x00")
        meta_file = tmp_path / "_recording_metadata.json"
        meta_file.write_text(json.dumps({"session_id": "s1"}))
        result = VideoManager.scan_input_paths([str(video)])
        assert result[0].get("metadata") == {"session_id": "s1"}


class TestVideoManagerClearCache:
    """Test VideoManager cache management."""

    def test_clear_scan_cache_runs_without_error(self):
        VideoManager.clear_scan_cache()  # Should not raise

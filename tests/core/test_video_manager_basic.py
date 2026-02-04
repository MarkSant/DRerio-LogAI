"""Tests for VideoManager helpers without filesystem scanning."""

from __future__ import annotations

from pathlib import Path

from zebtrack.core.video_manager import VideoManager


def test_normalize_path_handles_none():
    assert VideoManager.normalize_path(None) is None


def test_normalize_path_lowercase_and_slashes(tmp_path):
    path = tmp_path / "Some" / "Video.MP4"
    normalized = VideoManager.normalize_path(path)

    assert normalized is not None
    assert normalized.endswith("/some/video.mp4")


def test_refresh_complete_flag():
    entry = {"has_arena": True, "has_rois": True, "has_trajectory": False}
    VideoManager.refresh_complete_flag(entry)
    assert entry["has_complete_data"] is False

    entry["has_trajectory"] = True
    VideoManager.refresh_complete_flag(entry)
    assert entry["has_complete_data"] is True


def test_find_video_entry_by_path():
    project_data = {
        "batches": [
            {"videos": [{"path": "/data/A.MP4"}, {"path": "/data/B.MP4"}]}
        ]
    }

    entry = VideoManager.find_video_entry(project_data, path="/data/a.mp4")
    assert entry is not None
    assert entry["path"] == "/data/A.MP4"


def test_find_video_entry_by_experiment_id():
    project_data = {"batches": [{"videos": [{"path": "/data/exp1.mp4"}]}]}

    entry = VideoManager.find_video_entry(project_data, experiment_id="exp1")
    assert entry is not None
    assert entry["path"] == "/data/exp1.mp4"


def test_get_next_video():
    project_data = {
        "batches": [
            {"videos": [
                {"path": "one.mp4", "status": "processed"},
                {"path": "two.mp4", "status": "pending"},
            ]}
        ]
    }

    assert VideoManager.get_next_video(project_data) == "two.mp4"


def test_remove_video_entry(tmp_path):
    target = str(tmp_path / "video.mp4")
    project_data = {
        "batches": [
            {"videos": [{"path": target}, {"path": "other.mp4"}]},
            {"videos": [{"path": target}]},
        ]
    }

    cleared = []

    def _clear(path: str) -> None:
        cleared.append(path)

    changed = VideoManager.remove_video_entry(
        project_data,
        video_path=Path(target),
        video_entry={"path": target},
        clear_zones_callback=_clear,
    )

    assert changed is True
    assert cleared == [target]
    assert all(target != v.get("path") for b in project_data["batches"] for v in b["videos"])


def test_scan_input_paths_detects_parquet(tmp_path):
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"x")

    arena = tmp_path / "1_ProcessingArea_sample.parquet"
    rois = tmp_path / "2_AreasOfInterest_sample.parquet"
    trajectory = tmp_path / "3_CoordMovimento_sample.parquet"
    arena.write_text("arena")
    rois.write_text("rois")
    trajectory.write_text("traj")

    results = VideoManager.scan_input_paths([str(tmp_path)])

    assert len(results) == 1
    info = results[0]
    assert info["has_arena"] is True
    assert info["has_rois"] is True
    assert info["has_trajectory"] is True
    assert info["has_complete_data"] is True
    assert info["has_data"] is True


def test_scan_input_paths_missing_path(tmp_path):
    missing = tmp_path / "does_not_exist"
    results = VideoManager.scan_input_paths([str(missing)])
    assert results == []
